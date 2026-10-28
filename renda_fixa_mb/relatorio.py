"""Gravação dos relatórios por título e do ranking consolidado."""
import csv
import json
from datetime import date

from .risco_retorno import tabela_markdown

AVISO = "_Análise automatizada para apoio à decisão; não é recomendação de investimento. Confira a lâmina e as fontes._"


def salvar_analise(pasta, resultado):
    codigo, dados = resultado["codigo"], resultado["dados"]
    linhas = [f"# {codigo} - {dados['nome_produto']}", "", f"Gerado em {date.today().isoformat()}. {AVISO}", ""]
    if resultado["metricas"]:
        linhas += ["## Métricas calculadas", "", tabela_markdown(resultado["metricas"]), ""]
    if resultado["avisos"]:
        linhas += ["> Avisos do cálculo: " + "; ".join(resultado["avisos"]), ""]
    linhas.append(resultado["relatorio"])
    if resultado["fontes"]:
        linhas += ["", "## Fontes citadas na pesquisa", ""]
        linhas += [f"- [{titulo}]({url})" for url, titulo in resultado["fontes"].items()]
    (pasta / f"{codigo}.md").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    (pasta / f"{codigo}.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")


def _pct(x):
    return "" if x is None else f"{x * 100:.2f}%"


def salvar_ranking(pasta, resultados):
    analisados = [r for r in resultados if r.get("parecer")]
    analisados.sort(key=lambda r: r["parecer"]["nota_final"], reverse=True)
    colunas = ["codigo", "devedor", "lastro", "taxa_aa", "prazo_meses", "tir_cashback_btc_vendido",
               "premio_sobre_tesouro", "pd_implicita_anual", "pd_estimada_analista", "nota_final",
               "recomendacao", "alocacao_maxima", "resumo"]
    linhas = []
    for r in analisados:
        m, p, d = r["metricas"] or {}, r["parecer"], r["dados"]
        linhas.append({
            "codigo": r["codigo"],
            "devedor": d["devedor"] or "",
            "lastro": d["tipo_lastro"],
            "taxa_aa": _pct(m.get("taxa_lamina")),
            "prazo_meses": m.get("prazo_meses", ""),
            "tir_cashback_btc_vendido": _pct(m.get("tir_cashback_btc_vendido")),
            "premio_sobre_tesouro": _pct(m.get("premio_bruto_sobre_tesouro")),
            "pd_implicita_anual": _pct(m.get("pd_implicita_anual")),
            "pd_estimada_analista": "" if p["pd_anual_estimada_pct"] is None else f"{p['pd_anual_estimada_pct']:.2f}%",
            "nota_final": f"{p['nota_final']:.1f}",
            "recomendacao": p["recomendacao"].replace("_", " "),
            "alocacao_maxima": f"{p['alocacao_maxima_pct_carteira']:.1f}%",
            "resumo": p["resumo"],
        })

    with open(pasta / "ranking.csv", "w", newline="", encoding="utf-8") as f:
        escritor = csv.DictWriter(f, fieldnames=colunas, delimiter=";")
        escritor.writeheader()
        escritor.writerows(linhas)

    md = [f"# Ranking - Renda Fixa Digital MB ({date.today().isoformat()})", "", AVISO, ""]
    if linhas:
        md.append("| " + " | ".join(colunas) + " |")
        md.append("|" + "---|" * len(colunas))
        md += ["| " + " | ".join(str(l[c]).replace("|", "/") for c in colunas) + " |" for l in linhas]
    fora = [r for r in resultados if not r.get("parecer")]
    if fora:
        md += ["", "## Não analisados", ""]
        md += [f"- {r['codigo']}: {r.get('ignorado') or r.get('erro')}" for r in fora]
    (pasta / "ranking.md").write_text("\n".join(md) + "\n", encoding="utf-8")
