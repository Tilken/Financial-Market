"""Métricas determinísticas de risco x retorno de um título prefixado com cashback em BTC.

Tudo é calculado por R$ 1 investido; taxas em fração ao ano (0.17 = 17% a.a.).
"""
import math
from dataclasses import dataclass
from datetime import date

MESES_POR_PERIODO = {"mensal": 1, "trimestral": 3, "semestral": 6, "anual": 12}
Z_P5_P95 = 1.6449
CUSTODIA_B3_TESOURO = 0.002  # 0,20% a.a. sobre o Tesouro Prefixado


@dataclass
class Premissas:
    cashback: float = 0.03          # fração do valor aplicado, paga em BTC
    aliquota_ir_token: float = 0.0  # 0 = isento (vendas de cripto até R$ 35 mil/mês); ajuste ao seu caso
    recuperacao: float = 0.30       # fração do capital recuperada em caso de default


def gerar_fluxo(taxa, prazo_meses, periodicidade="no_vencimento", amortizacao="bullet", carencia_meses=0):
    """Fluxo de pagamentos [(anos, valor)] por R$ 1 aplicado.

    Na carência os juros são capitalizados (premissa conservadora: alonga a duration).
    """
    if periodicidade not in MESES_POR_PERIODO:
        return [(prazo_meses / 12, (1 + taxa) ** (prazo_meses / 12))]

    meses = MESES_POR_PERIODO[periodicidade]
    periodos = max(1, math.ceil(prazo_meses / meses))
    carencia = min(round((carencia_meses or 0) / meses), periodos - 1)
    juros_periodo = (1 + taxa) ** (meses / 12) - 1
    saldo, fluxos = 1.0, []
    for k in range(1, periodos + 1):
        anos = min(k * meses, prazo_meses) / 12
        juros = saldo * juros_periodo
        if k <= carencia:
            saldo += juros
            continue
        restantes = periodos - k + 1
        if amortizacao == "sac":
            amortiza = saldo / restantes
        elif amortizacao == "price":
            parcela = saldo * juros_periodo / (1 - (1 + juros_periodo) ** -restantes)
            amortiza = parcela - juros
        else:  # bullet: só juros até o último período
            amortiza = saldo if k == periodos else 0.0
        saldo -= amortiza
        fluxos.append((anos, juros + amortiza))
    return fluxos


def valor_presente(fluxos, taxa):
    return sum(valor / (1 + taxa) ** anos for anos, valor in fluxos)


def tir(fluxos, preco=1.0):
    """Taxa anual que iguala o valor presente dos fluxos ao preço pago (bisseção)."""
    baixo, alto = -0.99, 10.0
    for _ in range(200):
        meio = (baixo + alto) / 2
        if valor_presente(fluxos, meio) > preco:
            baixo = meio
        else:
            alto = meio
    return (baixo + alto) / 2


def duration(fluxos, taxa):
    vp = valor_presente(fluxos, taxa)
    macaulay = sum(anos * valor / (1 + taxa) ** anos for anos, valor in fluxos) / vp
    return macaulay, macaulay / (1 + taxa)


def fluxo_liquido_de_ir(fluxos, aliquota, preco=1.0):
    """Aproximação: cada pagamento carrega ganho e principal na mesma proporção do total."""
    total = sum(valor for _, valor in fluxos)
    fracao_ganho = max(total - preco, 0) / total
    return [(anos, valor * (1 - aliquota * fracao_ganho)) for anos, valor in fluxos]


def aliquota_ir_regressivo(dias):
    if dias <= 180:
        return 0.225
    if dias <= 360:
        return 0.20
    if dias <= 720:
        return 0.175
    return 0.15


def taxa_liquida_tesouro(taxa, anos):
    """Tesouro Prefixado levado ao vencimento: IR regressivo sobre o ganho e custódia da B3."""
    ganho = (1 + taxa) ** anos - 1
    liquido = ganho * (1 - aliquota_ir_regressivo(anos * 365))
    return (1 + liquido) ** (1 / anos) - 1 - CUSTODIA_B3_TESOURO


def prazo_em_meses(dados):
    if dados.prazo_meses:
        return dados.prazo_meses
    try:
        inicio = date.fromisoformat(dados.data_emissao) if dados.data_emissao else date.today()
        dias = (date.fromisoformat(dados.data_vencimento) - inicio).days
    except (TypeError, ValueError):  # vencimento ausente ou fora do formato AAAA-MM-DD
        return None
    return max(1, round(dias / 30.4375))


def calcular_metricas(dados, mercado, premissas):
    """Retorna (metricas, avisos). `dados` é um DadosLamina; `mercado` um Mercado."""
    avisos = []
    if dados.indexador != "prefixado" or dados.taxa_anual_pct is None:
        return None, [f"Métricas só são calculadas para títulos prefixados com taxa conhecida (indexador: {dados.indexador})."]
    prazo = prazo_em_meses(dados)
    if prazo is None:
        return None, ["A lâmina não informa prazo nem vencimento."]

    periodicidade, amortizacao = dados.periodicidade_pagamento, dados.amortizacao
    if amortizacao in ("personalizada", "desconhecida"):
        avisos.append(f"Amortização '{amortizacao}': fluxo modelado como bullet.")
        amortizacao = "bullet"
    if periodicidade not in MESES_POR_PERIODO and periodicidade != "no_vencimento":
        avisos.append(f"Periodicidade '{periodicidade}': fluxo modelado com pagamento único no vencimento.")

    taxa = dados.taxa_anual_pct / 100
    fluxos = gerar_fluxo(taxa, prazo, periodicidade, amortizacao, dados.carencia_meses or 0)
    anos_vencimento = fluxos[-1][0]
    macaulay, modificada = duration(fluxos, taxa)
    cashback = premissas.cashback if dados.cashback_pct is None else dados.cashback_pct / 100

    # Cashback em BTC: (a) vendido assim que creditado; (b) mantido até o vencimento,
    # com o BTC seguindo um passeio lognormal sem tendência (P5 / mediana / P95).
    tir_bruta = tir(fluxos)
    tir_cashback_vendido = tir(fluxos, preco=1 - cashback)
    sigma, raiz_t = mercado.btc_vol, math.sqrt(anos_vencimento)
    cenarios_btc = {}
    for nome, z in [("p5", -Z_P5_P95), ("mediana", 0.0), ("p95", Z_P5_P95)]:
        multiplicador = math.exp(-0.5 * sigma ** 2 * anos_vencimento + sigma * raiz_t * z)
        fluxos_btc = fluxos + [(anos_vencimento, cashback * multiplicador)]
        cenarios_btc[nome] = {"multiplicador_btc": multiplicador, "tir": tir(fluxos_btc)}

    # O IR incide sobre o ganho do token (base R$ 1); o cashback entra só no preço efetivo.
    liquida_token = tir(fluxo_liquido_de_ir(fluxos, premissas.aliquota_ir_token), preco=1 - cashback)

    metricas = {
        "taxa_lamina": taxa,
        "prazo_meses": prazo,
        "anos_ate_vencimento": anos_vencimento,
        "duration_macaulay_anos": macaulay,
        "duration_modificada": modificada,
        "variacao_preco_alta_1pp": valor_presente(fluxos, taxa + 0.01) - 1,
        "fluxo_modelado": {"periodicidade": periodicidade, "amortizacao": amortizacao,
                           "carencia_meses": dados.carencia_meses or 0, "pagamentos": len(fluxos)},
        "cashback": cashback,
        "tir_sem_cashback": tir_bruta,
        "tir_cashback_btc_vendido": tir_cashback_vendido,
        "tir_cashback_btc_mantido": cenarios_btc,
        "aliquota_ir_token": premissas.aliquota_ir_token,
        "tir_liquida_cashback_vendido": liquida_token,
        "recuperacao_premissa": premissas.recuperacao,
    }

    referencia = mercado.taxa_pre(macaulay)
    if referencia is None:
        avisos.append("Sem curva do Tesouro Prefixado: prêmio de crédito e PD implícita não calculados.")
    else:
        premio = (1 + tir_bruta) / (1 + referencia) - 1
        pd_anual = min(1.0, max(0.0, premio / (1 - premissas.recuperacao)))
        tesouro_liquido = taxa_liquida_tesouro(referencia, anos_vencimento)
        metricas.update({
            "tesouro_prefixado_mesma_duration": referencia,
            "tesouro_prefixado_liquido": tesouro_liquido,
            "premio_bruto_sobre_tesouro": premio,
            "premio_liquido_sobre_tesouro": (1 + liquida_token) / (1 + tesouro_liquido) - 1,
            "pd_implicita_anual": pd_anual,
            "pd_implicita_acumulada": 1 - (1 - pd_anual) ** anos_vencimento,
            "retorno_esperado_por_pd": {
                f"{pd:.0%}": (1 + tir_bruta) * (1 - pd * (1 - premissas.recuperacao)) - 1
                for pd in (0.01, 0.03, 0.05, 0.10)
            },
        })
    if mercado.ipca_esperado_12m is not None:
        metricas["taxa_real_esperada"] = (1 + tir_bruta) / (1 + mercado.ipca_esperado_12m) - 1
    return metricas, avisos


def tabela_markdown(metricas):
    def pct(x):
        return f"{x * 100:.2f}%"

    linhas = [
        ("Taxa da lâmina", pct(metricas["taxa_lamina"])),
        ("Prazo / duration (Macaulay)", f"{metricas['prazo_meses']} meses / {metricas['duration_macaulay_anos']:.2f} anos"),
        ("Perda de valor se os juros subirem 1 p.p.", pct(metricas["variacao_preco_alta_1pp"])),
        (f"TIR com cashback de {pct(metricas['cashback'])} (BTC vendido na hora)", pct(metricas["tir_cashback_btc_vendido"])),
    ]
    btc = metricas["tir_cashback_btc_mantido"]
    linhas.append(("TIR com BTC mantido até o vencimento (P5 / mediana / P95)",
                   " / ".join(pct(btc[k]["tir"]) for k in ("p5", "mediana", "p95"))))
    linhas.append((f"TIR líquida (IR do token {pct(metricas['aliquota_ir_token'])}, BTC vendido)",
                   pct(metricas["tir_liquida_cashback_vendido"])))
    if "tesouro_prefixado_mesma_duration" in metricas:
        linhas += [
            ("Tesouro Prefixado na mesma duration (bruto / líquido)",
             f"{pct(metricas['tesouro_prefixado_mesma_duration'])} / {pct(metricas['tesouro_prefixado_liquido'])}"),
            ("Prêmio sobre o Tesouro: bruto sem cashback / líquido de IR com cashback",
             f"{pct(metricas['premio_bruto_sobre_tesouro'])} / {pct(metricas['premio_liquido_sobre_tesouro'])}"),
            (f"PD implícita anual / acumulada (recuperação {pct(metricas['recuperacao_premissa'])})",
             f"{pct(metricas['pd_implicita_anual'])} / {pct(metricas['pd_implicita_acumulada'])}"),
        ]
        linhas += [(f"Retorno esperado a.a. sem cashback se PD anual = {pd}", pct(r))
                   for pd, r in metricas["retorno_esperado_por_pd"].items()]
    if "taxa_real_esperada" in metricas:
        linhas.append(("Taxa real esperada (vs. IPCA Focus 12m)", pct(metricas["taxa_real_esperada"])))
    return "| Métrica | Valor |\n|---|---|\n" + "\n".join(f"| {a} | {b} |" for a, b in linhas)
