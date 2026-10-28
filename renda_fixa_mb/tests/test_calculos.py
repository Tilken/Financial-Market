import math
import unittest
from unittest import mock

from renda_fixa_mb import coletor
from renda_fixa_mb.extrator import DadosLamina
from renda_fixa_mb.mercado import Mercado, curva_prefixada, volatilidade_anual
from renda_fixa_mb.risco_retorno import Premissas, calcular_metricas, duration, gerar_fluxo, tir


def dados_lamina(**campos):
    base = dict(
        codigo="RFDTESTE01", nome_produto="Teste", tipo_lastro="nota comercial", estrutura=None,
        devedor="Empresa X", cnpj_devedor=None, setor_devedor=None, indexador="prefixado",
        taxa_anual_pct=17.0, rentabilidade_texto="17% a.a.", rentabilidade_liquida_de_taxas=None,
        data_emissao=None, data_vencimento=None, prazo_meses=24, periodicidade_pagamento="mensal",
        amortizacao="price", carencia_meses=0, valor_emissao_brl=None, aporte_minimo_brl=None,
        garantias=[], reforcos_de_credito=[], rating=None, cashback_pct=None, condicoes_cashback=None,
        liquidez=None, tributacao=None, taxas_e_custos=None, cenarios_da_lamina=[], riscos_listados=[],
        observacoes=None,
    )
    base.update(campos)
    return DadosLamina(**base)


class TestFluxo(unittest.TestCase):
    def test_tir_reproduz_a_taxa_em_todos_os_formatos(self):
        for periodicidade, amortizacao, carencia in [
            ("no_vencimento", "bullet", 0), ("mensal", "bullet", 0), ("mensal", "price", 0),
            ("mensal", "sac", 6), ("trimestral", "price", 3), ("semestral", "bullet", 0),
        ]:
            fluxos = gerar_fluxo(0.17, 36, periodicidade, amortizacao, carencia)
            self.assertAlmostEqual(tir(fluxos), 0.17, places=8, msg=(periodicidade, amortizacao, carencia))

    def test_price_tem_parcelas_iguais_depois_da_carencia(self):
        fluxos = gerar_fluxo(0.15, 24, "mensal", "price", 6)
        self.assertEqual(len(fluxos), 18)
        self.assertTrue(all(math.isclose(v, fluxos[0][1]) for _, v in fluxos))

    def test_duration_do_bullet_e_o_prazo(self):
        macaulay, _ = duration(gerar_fluxo(0.17, 30), 0.17)
        self.assertAlmostEqual(macaulay, 2.5)


class TestMercado(unittest.TestCase):
    CSV = (
        "Tipo Titulo;Data Vencimento;Data Base;Taxa Compra Manha;Taxa Venda Manha;PU Compra Manha;PU Venda Manha;PU Base Manha\n"
        "Tesouro Prefixado;01/01/2028;24/10/2026;13,50;13,62;850,00;849,00;849,00\n"
        "Tesouro Prefixado;01/01/2028;27/10/2026;13,40;13,52;851,00;850,00;850,00\n"
        "Tesouro Prefixado;01/01/2032;27/10/2026;0,00;13,80;500,00;499,00;499,00\n"
        "Tesouro Prefixado com Juros Semestrais;01/01/2035;27/10/2026;13,90;14,00;900,00;899,00;899,00\n"
        "Tesouro IPCA+;15/05/2035;27/10/2026;7,10;7,20;3000,00;2990,00;2990,00\n"
    )

    def test_curva_usa_a_data_mais_recente_e_so_ltn(self):
        data, pontos = curva_prefixada(self.CSV)
        self.assertEqual(data, "2026-10-27")
        self.assertEqual([round(t, 4) for _, t, _ in pontos], [0.134, 0.138])  # sem compra -> taxa de venda

    def test_interpolacao(self):
        mercado = Mercado(data_referencia="2026-10-28", curva_pre=[(1.0, 0.13, "a"), (3.0, 0.15, "b")])
        self.assertAlmostEqual(mercado.taxa_pre(2.0), 0.14)
        self.assertAlmostEqual(mercado.taxa_pre(0.5), 0.13)
        self.assertAlmostEqual(mercado.taxa_pre(5.0), 0.15)

    def test_volatilidade_de_serie_constante_e_zero(self):
        self.assertAlmostEqual(volatilidade_anual([100 * 1.001 ** i for i in range(100)]), 0.0)


class TestMetricas(unittest.TestCase):
    mercado = Mercado(data_referencia="2026-10-28", curva_pre=[(0.5, 0.14, "a"), (3.0, 0.135, "b")],
                      ipca_esperado_12m=0.045, btc_vol=0.5)

    def test_cashback_eleva_a_tir_e_premio_gera_pd(self):
        metricas, avisos = calcular_metricas(dados_lamina(), self.mercado, Premissas(cashback=0.03))
        self.assertEqual(avisos, [])
        self.assertAlmostEqual(metricas["tir_sem_cashback"], 0.17, places=6)
        self.assertGreater(metricas["tir_cashback_btc_vendido"], 0.19)
        btc = metricas["tir_cashback_btc_mantido"]
        self.assertLess(btc["p5"]["tir"], btc["mediana"]["tir"])
        self.assertLess(btc["mediana"]["tir"], btc["p95"]["tir"])
        self.assertGreater(metricas["premio_bruto_sobre_tesouro"], 0)
        self.assertAlmostEqual(metricas["pd_implicita_anual"], metricas["premio_bruto_sobre_tesouro"] / 0.7)

    def test_ir_reduz_a_tir_liquida(self):
        isento, _ = calcular_metricas(dados_lamina(), self.mercado, Premissas(aliquota_ir_token=0.0))
        tributado, _ = calcular_metricas(dados_lamina(), self.mercado, Premissas(aliquota_ir_token=0.15))
        self.assertAlmostEqual(isento["tir_liquida_cashback_vendido"], isento["tir_cashback_btc_vendido"])
        self.assertLess(tributado["tir_liquida_cashback_vendido"], isento["tir_liquida_cashback_vendido"])

    def test_cashback_da_lamina_prevalece(self):
        metricas, _ = calcular_metricas(dados_lamina(cashback_pct=5.0), self.mercado, Premissas(cashback=0.03))
        self.assertAlmostEqual(metricas["cashback"], 0.05)

    def test_pos_fixado_nao_tem_metricas(self):
        metricas, avisos = calcular_metricas(dados_lamina(indexador="cdi"), self.mercado, Premissas())
        self.assertIsNone(metricas)
        self.assertTrue(avisos)

    def test_prazo_pelo_vencimento(self):
        dados = dados_lamina(prazo_meses=None, data_emissao="2026-01-15", data_vencimento="2028-01-15",
                             periodicidade_pagamento="no_vencimento", amortizacao="bullet")
        metricas, _ = calcular_metricas(dados, self.mercado, Premissas())
        self.assertEqual(metricas["prazo_meses"], 24)


class TestColetor(unittest.TestCase):
    def test_inferir_codigo(self):
        self.assertEqual(coletor.inferir_codigo("https://x/wp-content/uploads/2023/03/Lamina-tecnica-RFDCS06.pdf"), "RFDCS06")
        self.assertEqual(coletor.inferir_codigo("Lamina-MBCCSH22-tecnica.pdf"), "MBCCSH22")

    def test_links_de_lamina_na_pagina(self):
        html = """<a href="/wp-content/uploads/2026/10/Lamina-RFDPRE01.pdf">Ver lâmina</a>
                  <a href="https://www.mercadobitcoin.com.br/x/Regulamento.pdf">Regulamento</a>
                  <a href="/docs/RFDPRE02.pdf">Lâmina técnica</a>"""
        resposta = mock.Mock(text=html, raise_for_status=lambda: None)
        with mock.patch.object(coletor.requests, "get", return_value=resposta):
            titulos = coletor.laminas_na_pagina("https://www.mercadobitcoin.com.br/renda-fixa")
        self.assertEqual([t.codigo for t in titulos], ["RFDPRE01", "RFDPRE02"])
        self.assertEqual(titulos[0].url_lamina, "https://www.mercadobitcoin.com.br/wp-content/uploads/2026/10/Lamina-RFDPRE01.pdf")


if __name__ == "__main__":
    unittest.main()
