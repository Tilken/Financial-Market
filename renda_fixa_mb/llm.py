"""Acesso ao Claude: cliente, PDF como bloco de documento e extração estruturada."""
import base64
from pathlib import Path

import anthropic

MODELO = "claude-opus-5-5"
# Se o modelo recusar uma requisição, a API refaz no modelo de fallback recomendado
# (server-side fallback, modo "default").
BETAS = ["server-side-fallback-2026-07-01"]
FALLBACKS = "default"

_cliente = None


class RecusaDoModelo(Exception):
    pass


def cliente():
    global _cliente
    if _cliente is None:
        # Lê ANTHROPIC_API_KEY (ou o perfil do `ant auth login`) do ambiente.
        _cliente = anthropic.Anthropic(max_retries=4)
    return _cliente


def bloco_pdf(caminho):
    dados = base64.standard_b64encode(Path(caminho).read_bytes()).decode("utf-8")
    return {
        "type": "document",
        "source": {"type": "base64", "media_type": "application/pdf", "data": dados},
        "title": Path(caminho).name,
    }


def verificar_resposta(resposta):
    if resposta.stop_reason == "refusal":
        detalhe = resposta.stop_details.explanation if resposta.stop_details else ""
        raise RecusaDoModelo(f"O modelo recusou a requisição. {detalhe}".strip())
    if resposta.stop_reason == "max_tokens":
        raise RuntimeError("Resposta cortada por max_tokens.")


def estruturar(conteudo, formato, sistema, esforco="medium"):
    """Uma chamada ao Claude cuja resposta é validada contra o modelo Pydantic `formato`."""
    resposta = cliente().beta.messages.parse(
        model=MODELO,
        max_tokens=16000,
        betas=BETAS,
        fallbacks=FALLBACKS,
        system=sistema,
        output_config={"effort": esforco},
        output_format=formato,
        messages=[{"role": "user", "content": conteudo}],
    )
    verificar_resposta(resposta)
    if resposta.parsed_output is None:
        raise RuntimeError("O Claude não devolveu uma saída estruturada válida.")
    return resposta.parsed_output
