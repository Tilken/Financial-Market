"""Encontra as ofertas e baixa as lâminas (PDF)."""
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import List, Optional
from urllib.parse import unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel

from . import llm
from .analista import FERRAMENTAS_WEB

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
DOMINIO_MB = "mercadobitcoin.com.br"


@dataclass
class Titulo:
    codigo: str
    url_lamina: str | None = None
    caminho_pdf: Path | None = None
    nome: str | None = None
    cashback_pct: float | None = None
    fonte: str | None = None


def inferir_codigo(nome):
    """'Lamina-tecnica-RFDCS06.pdf' -> 'RFDCS06'."""
    base = Path(unquote(urlparse(nome).path if "://" in nome else nome)).stem
    candidatos = re.findall(r"[A-Z]{2,}[A-Z0-9]*\d{2,}", base.upper())
    return candidatos[-1] if candidatos else re.sub(r"[^A-Za-z0-9_-]+", "-", base)[:60]


def _html(url, renderizar):
    if not renderizar:
        resposta = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=60)
        resposta.raise_for_status()
        return resposta.text
    from playwright.sync_api import sync_playwright  # opcional: só para páginas montadas via JavaScript

    with sync_playwright() as p:
        navegador = p.chromium.launch()
        pagina = navegador.new_page(user_agent=USER_AGENT)
        pagina.goto(url, wait_until="networkidle", timeout=90000)
        html = pagina.content()
        navegador.close()
    return html


def laminas_na_pagina(url, renderizar=False):
    """Links para PDFs de lâmina numa página de ofertas."""
    soup = BeautifulSoup(_html(url, renderizar), "html.parser")
    titulos = {}
    for a in soup.find_all("a", href=True):
        href = urljoin(url, a["href"])
        texto = a.get_text(" ", strip=True).lower()
        if href.lower().split("?")[0].endswith(".pdf") and ("lamina" in href.lower() or "lâmina" in texto or "lamina" in texto):
            codigo = inferir_codigo(href)
            titulos.setdefault(codigo, Titulo(codigo=codigo, url_lamina=href, fonte=url))
    return list(titulos.values())


class OfertaEncontrada(BaseModel):
    codigo: Optional[str]
    nome: str
    url_lamina: Optional[str]
    taxa_aa_pct: Optional[float]
    cashback_pct: Optional[float]
    situacao: Optional[str]
    fonte: Optional[str]


class Ofertas(BaseModel):
    ofertas: List[OfertaEncontrada]


def descobrir_com_claude(criterio):
    """Pede ao Claude para achar, na web, as ofertas abertas e as URLs das lâminas."""
    pedido = (
        f"Data de hoje: {date.today().isoformat()}. Encontre as ofertas de Renda Fixa Digital do Mercado "
        f"Bitcoin (MB) abertas agora que atendam a: {criterio}. Para cada uma, ache a URL do PDF da lâmina "
        f"(costuma ficar em {DOMINIO_MB}/wp-content/uploads/...), a taxa, o cashback e a situação da oferta. "
        "Descarte ofertas encerradas. Liste o que encontrou com as URLs exatas."
    )
    mensagens = [{"role": "user", "content": pedido}]
    for _ in range(6):
        with llm.cliente().beta.messages.stream(
            model=llm.MODELO,
            max_tokens=32000,
            betas=llm.BETAS,
            fallbacks=llm.FALLBACKS,
            tools=FERRAMENTAS_WEB,
            output_config={"effort": "medium"},
            messages=mensagens,
        ) as stream:
            resposta = stream.get_final_message()
        llm.verificar_resposta(resposta)
        mensagens.append({"role": "assistant", "content": resposta.content})
        if resposta.stop_reason != "pause_turn":
            break
    texto = "".join(b.text for m in mensagens[1:] for b in m["content"] if b.type == "text")
    ofertas = llm.estruturar(
        f"Resultado da busca:\n\n{texto}\n\nListe as ofertas encontradas.",
        Ofertas,
        "Você converte o resultado de uma busca de ofertas em uma lista estruturada, sem acrescentar nada.",
        esforco="low",
    ).ofertas

    titulos = []
    for oferta in ofertas:
        # Só baixa PDFs hospedados pelo próprio MB: a URL veio de uma busca na web.
        host = urlparse(oferta.url_lamina or "").hostname or ""
        if not (host == DOMINIO_MB or host.endswith("." + DOMINIO_MB)):
            print(f"  [descoberta] {oferta.nome}: sem lâmina no domínio do MB, ignorada ({oferta.url_lamina})")
            continue
        codigo = oferta.codigo or inferir_codigo(oferta.url_lamina)
        titulos.append(Titulo(codigo=codigo, url_lamina=oferta.url_lamina, nome=oferta.nome,
                              cashback_pct=oferta.cashback_pct, fonte=oferta.fonte))
    return titulos


def baixar_lamina(titulo, pasta):
    if titulo.caminho_pdf:
        return titulo.caminho_pdf
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"{titulo.codigo}.pdf"
    if not destino.exists():
        resposta = requests.get(titulo.url_lamina, headers={"User-Agent": USER_AGENT}, timeout=120)
        resposta.raise_for_status()
        if not resposta.content.startswith(b"%PDF"):
            raise ValueError(f"{titulo.url_lamina} não devolveu um PDF.")
        destino.write_bytes(resposta.content)
    titulo.caminho_pdf = destino
    return destino
