"""Dados de mercado usados como referência: juros (BCB e Tesouro Direto), inflação e bitcoin."""
import csv
import io
import math
import time
from dataclasses import dataclass, field
from datetime import date, datetime

import requests

URL_SGS = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados/ultimos/1?formato=json"
URL_FOCUS_12M = "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/ExpectativasMercadoInflacao12Meses"
URL_TESOURO = (
    "https://www.tesourotransparente.gov.br/ckan/dataset/df56aa42-484a-4a59-8184-7676580c81e3/"
    "resource/796d2059-14e9-44e3-80c9-2d9e30b405c1/download/PrecoTaxaTesouroDireto.csv"
)
URL_CANDLES_MB = "https://api.mercadobitcoin.net/api/v4/candles"
URL_COINGECKO = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"

SGS_SELIC_META = 432
SGS_CDI = 4389
SGS_IPCA_12M = 13522

VOL_BTC_PADRAO = 0.55  # usada só se não der para calcular a volatilidade histórica


@dataclass
class Mercado:
    data_referencia: str
    selic_meta: float | None = None   # todas as taxas em fração ao ano (0.15 = 15% a.a.)
    cdi: float | None = None
    ipca_12m: float | None = None
    ipca_esperado_12m: float | None = None
    curva_pre: list = field(default_factory=list)  # [(anos, taxa, vencimento)] do Tesouro Prefixado
    data_curva: str | None = None
    btc_preco: float | None = None
    btc_vol: float = VOL_BTC_PADRAO
    fonte_btc: str = "premissa padrão"
    avisos: list = field(default_factory=list)

    def taxa_pre(self, anos):
        """Taxa do Tesouro Prefixado interpolada linearmente no prazo (constante fora da curva)."""
        if not self.curva_pre:
            return None
        pontos = sorted(self.curva_pre)
        if anos <= pontos[0][0]:
            return pontos[0][1]
        for (a0, t0, _), (a1, t1, _) in zip(pontos, pontos[1:]):
            if a0 <= anos <= a1:
                return t0 + (t1 - t0) * (anos - a0) / (a1 - a0)
        return pontos[-1][1]

    def resumo(self):
        def pct(x):
            return "n/d" if x is None else f"{x * 100:.2f}%"
        linhas = [
            f"Data de referência: {self.data_referencia}",
            f"Selic meta: {pct(self.selic_meta)} | CDI: {pct(self.cdi)} | IPCA 12m: {pct(self.ipca_12m)} "
            f"| IPCA esperado 12m (Focus): {pct(self.ipca_esperado_12m)}",
        ]
        if self.data_curva == "manual":
            linhas.append(f"Taxa prefixada livre de risco (informada pelo usuário): {pct(self.curva_pre[0][1])}")
        elif self.curva_pre:
            pontos = ", ".join(f"{venc} ({anos:.1f}a): {pct(taxa)}" for anos, taxa, venc in sorted(self.curva_pre))
            linhas.append(f"Curva Tesouro Prefixado em {self.data_curva}: {pontos}")
        preco = f"R$ {self.btc_preco:,.0f}" if self.btc_preco else "n/d"
        linhas.append(f"BTC: preço {preco} | volatilidade anual {self.btc_vol * 100:.0f}% ({self.fonte_btc})")
        return "\n".join(linhas)


def _erro(e):
    return str(e).split("(Caused by")[0].strip()[:200] or type(e).__name__


def _numero_br(texto):
    return float(texto.strip().replace(".", "").replace(",", ".")) if texto and texto.strip() else None


def _sgs(codigo):
    resposta = requests.get(URL_SGS.format(codigo=codigo), timeout=30)
    resposta.raise_for_status()
    return float(resposta.json()[-1]["valor"]) / 100


def _ipca_esperado_12m():
    params = {
        "$filter": "Indicador eq 'IPCA' and Suavizada eq 'S' and baseCalculo eq 0",
        "$orderby": "Data desc",
        "$top": "1",
        "$format": "json",
    }
    resposta = requests.get(URL_FOCUS_12M, params=params, timeout=30)
    resposta.raise_for_status()
    return float(resposta.json()["value"][0]["Mediana"]) / 100


def _baixar_csv_tesouro(pasta_cache):
    """O CSV tem todo o histórico desde 2002 (dezenas de MB): baixa no máximo uma vez por dia."""
    pasta_cache.mkdir(parents=True, exist_ok=True)
    arquivo = pasta_cache / "PrecoTaxaTesouroDireto.csv"
    if not arquivo.exists() or time.time() - arquivo.stat().st_mtime > 20 * 3600:
        with requests.get(URL_TESOURO, timeout=180, stream=True) as resposta:
            resposta.raise_for_status()
            with open(arquivo, "wb") as f:
                for pedaco in resposta.iter_content(1 << 20):
                    f.write(pedaco)
    return arquivo


def curva_prefixada(texto_csv):
    """Taxas do Tesouro Prefixado (LTN, sem cupom) na data base mais recente do CSV."""
    por_data = {}
    for linha in csv.DictReader(io.StringIO(texto_csv), delimiter=";"):
        if linha.get("Tipo Titulo", "").strip() != "Tesouro Prefixado":
            continue
        base = datetime.strptime(linha["Data Base"].strip(), "%d/%m/%Y").date()
        vencimento = datetime.strptime(linha["Data Vencimento"].strip(), "%d/%m/%Y").date()
        taxa = _numero_br(linha.get("Taxa Compra Manha")) or _numero_br(linha.get("Taxa Venda Manha"))
        if taxa and vencimento > base:
            por_data.setdefault(base, []).append((vencimento, taxa / 100))
    if not por_data:
        return None, []
    base = max(por_data)
    pontos = [((venc - base).days / 365, taxa, venc.isoformat()) for venc, taxa in por_data[base]]
    return base.isoformat(), sorted(pontos)


def _closes_btc():
    agora = int(time.time())
    try:
        params = {"symbol": "BTC-BRL", "resolution": "1d", "from": agora - 400 * 86400, "to": agora}
        resposta = requests.get(URL_CANDLES_MB, params=params, timeout=30)
        resposta.raise_for_status()
        closes = [float(c) for c in resposta.json()["c"]]
        if len(closes) > 30:
            return closes, "candles diários BTC-BRL do Mercado Bitcoin"
    except (requests.RequestException, KeyError, ValueError, TypeError):
        pass
    params = {"vs_currency": "brl", "days": 365, "interval": "daily"}
    resposta = requests.get(URL_COINGECKO, params=params, timeout=30)
    resposta.raise_for_status()
    return [p[1] for p in resposta.json()["prices"]], "preços diários BTC/BRL do CoinGecko"


def volatilidade_anual(precos):
    retornos = [math.log(b / a) for a, b in zip(precos, precos[1:]) if a > 0 and b > 0]
    media = sum(retornos) / len(retornos)
    variancia = sum((r - media) ** 2 for r in retornos) / (len(retornos) - 1)
    return math.sqrt(variancia * 365)  # cripto negocia todos os dias


def carregar_mercado(pasta_cache, taxa_pre_manual=None, vol_btc_manual=None):
    mercado = Mercado(data_referencia=date.today().isoformat())

    for nome, funcao in [
        ("selic_meta", lambda: _sgs(SGS_SELIC_META)),
        ("cdi", lambda: _sgs(SGS_CDI)),
        ("ipca_12m", lambda: _sgs(SGS_IPCA_12M)),
        ("ipca_esperado_12m", _ipca_esperado_12m),
    ]:
        try:
            setattr(mercado, nome, funcao())
        except Exception as e:
            mercado.avisos.append(f"Não consegui obter {nome}: {_erro(e)}")

    if taxa_pre_manual is not None:
        mercado.curva_pre = [(0.0, taxa_pre_manual, "manual")]
        mercado.data_curva = "manual"
    else:
        try:
            arquivo = _baixar_csv_tesouro(pasta_cache)
            texto = arquivo.read_text(encoding="utf-8-sig", errors="replace")
            mercado.data_curva, mercado.curva_pre = curva_prefixada(texto)
        except Exception as e:
            mercado.avisos.append(f"Não consegui obter a curva do Tesouro Prefixado: {_erro(e)}")

    if vol_btc_manual is not None:
        mercado.btc_vol, mercado.fonte_btc = vol_btc_manual, "informada pelo usuário"
    else:
        try:
            closes, fonte = _closes_btc()
            mercado.btc_preco = closes[-1]
            mercado.btc_vol = volatilidade_anual(closes[-366:])
            mercado.fonte_btc = f"histórica 12m, {fonte}"
        except Exception as e:
            mercado.avisos.append(f"Não consegui obter o histórico do BTC (usando vol. {VOL_BTC_PADRAO:.0%}): {_erro(e)}")

    return mercado
