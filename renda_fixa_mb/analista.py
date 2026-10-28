"""Análise de cada título pelo Claude: pesquisa na web sobre a companhia, o mercado e a emissão."""
import json
from datetime import date
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from . import llm
from .risco_retorno import tabela_markdown

MAX_CONTINUACOES = 6

FERRAMENTAS_WEB = [
    {
        "type": "web_search_20260209",
        "name": "web_search",
        "max_uses": 15,
        "user_location": {"type": "approximate", "country": "BR", "city": "São Paulo", "timezone": "America/Sao_Paulo"},
    },
    {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 10, "max_content_tokens": 30000},
]

SISTEMA = """Você é um analista sênior de crédito privado no Brasil, avaliando ofertas de renda fixa \
tokenizada ("Renda Fixa Digital") distribuídas pelo Mercado Bitcoin (MB). O investidor quer saber \
se vale a pena aplicar num título prefixado que paga cashback em bitcoin.

Você recebe a lâmina da oferta (PDF), os termos já extraídos, métricas de risco x retorno \
calculadas por código e um retrato do mercado. Pesquise na web o que a lâmina não responde: quem \
é a companhia/devedor (CNPJ, tempo de existência, sócios, porte, demonstrações financeiras, \
endividamento, processos, recuperação judicial, protestos, notícias, reputação), o setor em que \
ela atua, a estrutura da oferta (securitizadora, plataforma, regulação CVM, histórico de ofertas \
parecidas do MB e se houve atrasos ou defaults), a tributação atual desses tokens e as condições \
da campanha de cashback.

Escreva o relatório em português, em Markdown, com estas seções:
1. Resumo executivo (veredito em uma frase + 3 a 5 pontos)
2. A emissão (estrutura, lastro, fluxo, garantias e reforços, liquidez, custos, regulação)
3. A companhia (quem paga a dívida e qual a capacidade de pagamento)
4. O mercado (setor do devedor e cenário de juros para um prefixado deste prazo)
5. Risco x retorno (interprete as métricas: prêmio sobre o Tesouro, PD implícita vs. a sua \
estimativa de PD, efeito real do cashback em BTC, risco de marcação a mercado e de liquidez, \
comparação com alternativas como Tesouro Prefixado e CDBs com FGC)
6. Principais riscos e mitigantes
7. Veredito (nota de 0 a 10 para emissão, companhia, mercado e risco x retorno; nota final; \
recomendação; tamanho máximo de posição sugerido em % da carteira)
8. Fontes (links usados)

Separe fato de inferência. Quando não encontrar uma informação, diga que não encontrou em vez de \
supor; falta de informação sobre o devedor é, por si, um risco. As métricas foram calculadas por \
código a partir das premissas indicadas: use-as, aponte se alguma premissa parecer errada para \
este título e não refaça as contas de cabeça. Isto é uma análise para apoiar a decisão do \
investidor, não uma recomendação formal de investimento."""


class Parecer(BaseModel):
    nota_emissao: int = Field(description="0 a 10")
    nota_companhia: int = Field(description="0 a 10")
    nota_mercado: int = Field(description="0 a 10")
    nota_risco_retorno: int = Field(description="0 a 10")
    nota_final: float = Field(description="0 a 10")
    recomendacao: Literal["investir", "investir_com_cautela", "evitar"]
    alocacao_maxima_pct_carteira: float
    pd_anual_estimada_pct: Optional[float] = Field(description="Probabilidade de default anual estimada pelo analista, em %.")
    resumo: str = Field(description="Uma ou duas frases.")
    principais_riscos: List[str]
    pontos_positivos: List[str]


def _texto_e_fontes(respostas):
    textos, fontes = [], {}
    for resposta in respostas:
        for bloco in resposta.content:
            if bloco.type != "text":
                continue
            textos.append(bloco.text)
            for citacao in bloco.citations or []:
                url = getattr(citacao, "url", None)
                if url:
                    fontes.setdefault(url, getattr(citacao, "title", None) or url)
    return "".join(textos).strip(), fontes


def analisar(codigo, caminho_pdf, dados, metricas, avisos, mercado, premissas, esforco="high", pesquisar_web=True):
    """Devolve (relatorio_markdown, {url: titulo} das fontes citadas)."""
    if metricas:
        bloco_metricas = tabela_markdown(metricas) + "\n\nValores completos:\n" + json.dumps(metricas, ensure_ascii=False, indent=2)
    else:
        bloco_metricas = "Não calculadas."
    texto = f"""Data de hoje: {date.today().isoformat()}
Título: {codigo}

## Termos extraídos da lâmina
{dados.model_dump_json(indent=2)}

## Métricas calculadas
{bloco_metricas}

Avisos do cálculo: {"; ".join(avisos) or "nenhum"}

## Premissas do investidor
- Cashback: {premissas.cashback * 100:.1f}% em BTC (a lâmina prevalece se informar outro valor)
- Alíquota de IR sobre o ganho do token: {premissas.aliquota_ir_token * 100:.1f}% (verifique a regra atual)
- Recuperação em caso de default: {premissas.recuperacao * 100:.0f}% do capital

## Mercado
{mercado.resumo()}

Analise este título."""
    if not pesquisar_web:
        texto += "\n\nNão há acesso à web nesta análise: trabalhe só com a lâmina e os dados acima."

    mensagens = [{"role": "user", "content": [llm.bloco_pdf(caminho_pdf), {"type": "text", "text": texto}]}]
    parametros = dict(
        model=llm.MODELO,
        max_tokens=64000,
        betas=llm.BETAS,
        fallbacks=llm.FALLBACKS,
        system=SISTEMA,
        output_config={"effort": esforco},
        cache_control={"type": "ephemeral"},
    )
    if pesquisar_web:
        parametros["tools"] = FERRAMENTAS_WEB
    respostas = []
    for _ in range(MAX_CONTINUACOES):
        with llm.cliente().beta.messages.stream(messages=mensagens, **parametros) as stream:
            resposta = stream.get_final_message()
        llm.verificar_resposta(resposta)
        respostas.append(resposta)
        if resposta.stop_reason != "pause_turn":
            break
        # Pesquisa longa: devolve o turno pausado e o servidor continua de onde parou.
        mensagens.append({"role": "assistant", "content": resposta.content})
    else:
        raise RuntimeError(f"A análise de {codigo} não terminou após {MAX_CONTINUACOES} continuações.")

    relatorio, fontes = _texto_e_fontes(respostas)
    return relatorio, fontes


def emitir_parecer(codigo, relatorio):
    """Converte o relatório em notas e recomendação estruturadas, para o ranking."""
    conteudo = f"Relatório de análise do título {codigo}:\n\n{relatorio}\n\nExtraia o parecer do relatório."
    sistema = "Você converte relatórios de análise de crédito em um parecer estruturado, fiel ao que o relatório conclui."
    return llm.estruturar(conteudo, Parecer, sistema, esforco="low")
