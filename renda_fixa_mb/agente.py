"""Agente de análise de títulos de Renda Fixa Digital do Mercado Bitcoin.

Fluxo por título: baixa a lâmina -> extrai os termos (Claude) -> calcula risco x retorno
(código) -> pesquisa companhia, mercado e emissão na web e escreve o relatório (Claude)
-> parecer estruturado -> ranking consolidado.
"""
import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import anthropic

from . import coletor, relatorio
from .analista import analisar, emitir_parecer
from .extrator import DadosLamina, extrair_dados
from .mercado import carregar_mercado
from .risco_retorno import Premissas, calcular_metricas


def coletar_titulos(args):
    titulos = []
    for caminho in args.pdf or []:
        caminho = Path(caminho)
        titulos.append(coletor.Titulo(codigo=coletor.inferir_codigo(caminho.name), caminho_pdf=caminho))
    for url in args.lamina or []:
        titulos.append(coletor.Titulo(codigo=coletor.inferir_codigo(url), url_lamina=url))
    if args.pagina:
        encontrados = coletor.laminas_na_pagina(args.pagina, renderizar=args.renderizar)
        print(f"{len(encontrados)} lâmina(s) encontrada(s) em {args.pagina}")
        titulos += encontrados
    if args.descobrir:
        print(f"Procurando ofertas na web: {args.descobrir}")
        encontrados = coletor.descobrir_com_claude(args.descobrir)
        print(f"{len(encontrados)} oferta(s) com lâmina encontrada(s)")
        titulos += encontrados

    unicos = {}
    for titulo in titulos:
        unicos.setdefault(titulo.codigo, titulo)
    return list(unicos.values())[: args.max_titulos]


def processar(titulo, args, mercado):
    codigo, pasta = titulo.codigo, args.saida
    arquivo_final = pasta / f"{codigo}.json"
    if arquivo_final.exists() and not args.refazer:
        print(f"[{codigo}] já analisado (use --refazer para refazer)")
        return json.loads(arquivo_final.read_text(encoding="utf-8"))

    print(f"[{codigo}] baixando a lâmina")
    pdf = coletor.baixar_lamina(titulo, pasta / "laminas")

    cache_dados = pasta / "cache" / f"{codigo}.dados.json"
    if cache_dados.exists() and not args.refazer:
        dados = DadosLamina.model_validate_json(cache_dados.read_text(encoding="utf-8"))
    else:
        print(f"[{codigo}] extraindo os termos da lâmina")
        dados = extrair_dados(pdf)
        cache_dados.parent.mkdir(parents=True, exist_ok=True)
        cache_dados.write_text(dados.model_dump_json(indent=2), encoding="utf-8")

    if dados.indexador != "prefixado" and not args.incluir_outros:
        return {"codigo": codigo, "ignorado": f"indexador {dados.indexador} (use --incluir-outros para analisar)"}

    cashback = titulo.cashback_pct if titulo.cashback_pct is not None else args.cashback
    premissas = Premissas(cashback=cashback / 100, aliquota_ir_token=args.ir_token / 100,
                          recuperacao=args.recuperacao / 100)
    metricas, avisos = calcular_metricas(dados, mercado, premissas)

    print(f"[{codigo}] analisando emissão, companhia, mercado e risco x retorno")
    texto, fontes = analisar(codigo, pdf, dados, metricas, avisos, mercado, premissas,
                             esforco=args.esforco, pesquisar_web=not args.sem_web)
    parecer = emitir_parecer(codigo, texto)

    resultado = {
        "codigo": codigo,
        "url_lamina": titulo.url_lamina,
        "dados": dados.model_dump(),
        "metricas": metricas,
        "avisos": avisos,
        "relatorio": texto,
        "fontes": fontes,
        "parecer": parecer.model_dump(),
    }
    relatorio.salvar_analise(pasta, resultado)
    print(f"[{codigo}] nota {parecer.nota_final:.1f} - {parecer.recomendacao} -> {pasta / (codigo + '.md')}")
    return resultado


def processar_com_seguranca(titulo, args, mercado):
    try:
        return processar(titulo, args, mercado)
    except anthropic.AuthenticationError:
        raise
    except Exception as e:
        erro = str(e).split("(Caused by")[0].strip() or type(e).__name__
        print(f"[{titulo.codigo}] ERRO: {erro}")
        return {"codigo": titulo.codigo, "erro": erro}


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m renda_fixa_mb", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    fontes = p.add_argument_group("de onde vêm os títulos (combine à vontade)")
    fontes.add_argument("--pdf", nargs="+", help="lâminas já baixadas")
    fontes.add_argument("--lamina", nargs="+", help="URLs de PDFs de lâmina")
    fontes.add_argument("--pagina", help="página de ofertas onde procurar links para lâminas")
    fontes.add_argument("--renderizar", action="store_true", help="abre --pagina num navegador (Playwright) para páginas em JavaScript")
    fontes.add_argument("--descobrir", nargs="?", const="rentabilidade prefixada e cashback em bitcoin",
                        help="o Claude procura as ofertas abertas e as lâminas na web (critério opcional)")

    premissas = p.add_argument_group("premissas")
    premissas.add_argument("--cashback", type=float, default=3.0, help="cashback em %% do aplicado, pago em BTC (padrão 3)")
    premissas.add_argument("--ir-token", type=float, default=0.0, help="alíquota de IR sobre o ganho do token, em %% (padrão 0)")
    premissas.add_argument("--recuperacao", type=float, default=30.0, help="%% do capital recuperado num default (padrão 30)")
    premissas.add_argument("--taxa-tesouro", type=float, help="usa esta taxa (%% a.a.) em vez da curva do Tesouro Prefixado")
    premissas.add_argument("--vol-btc", type=float, help="volatilidade anual do BTC em %% (padrão: histórica de 12 meses)")

    execucao = p.add_argument_group("execução")
    execucao.add_argument("--esforco", default="high", choices=["low", "medium", "high", "xhigh", "max"],
                          help="esforço do Claude na análise (padrão high)")
    execucao.add_argument("--sem-web", action="store_true", help="analisa só com a lâmina, sem pesquisa na web")
    execucao.add_argument("--incluir-outros", action="store_true", help="analisa também títulos não prefixados")
    execucao.add_argument("--saida", type=Path, default=Path("saida_renda_fixa"))
    execucao.add_argument("--refazer", action="store_true", help="ignora resultados já salvos")
    execucao.add_argument("--paralelo", type=int, default=1, help="títulos analisados ao mesmo tempo")
    execucao.add_argument("--max-titulos", type=int, default=None)
    args = p.parse_args(argv)

    titulos = coletar_titulos(args)
    if not titulos:
        p.error("nenhum título: informe --pdf, --lamina, --pagina ou --descobrir")
    args.saida.mkdir(parents=True, exist_ok=True)

    print("Carregando dados de mercado...")
    mercado = carregar_mercado(args.saida / "cache",
                               taxa_pre_manual=None if args.taxa_tesouro is None else args.taxa_tesouro / 100,
                               vol_btc_manual=None if args.vol_btc is None else args.vol_btc / 100)
    for aviso in mercado.avisos:
        print(f"  aviso: {aviso}")
    print(mercado.resumo())

    with ThreadPoolExecutor(max_workers=max(1, args.paralelo)) as executor:
        resultados = list(executor.map(lambda t: processar_com_seguranca(t, args, mercado), titulos))

    relatorio.salvar_ranking(args.saida, resultados)
    print(f"\nRanking: {args.saida / 'ranking.md'}")


if __name__ == "__main__":
    main()
