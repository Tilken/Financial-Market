"""Leitura da lâmina (PDF) e extração dos termos da emissão em formato estruturado."""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from . import llm

# Sem valores padrão de propósito: todo campo é obrigatório na resposta,
# e o Claude usa null quando a informação não está na lâmina.


class DadosLamina(BaseModel):
    codigo: Optional[str] = Field(description="Código do token/oferta, ex.: RFDCS06, MBCCSH22.")
    nome_produto: str
    tipo_lastro: str = Field(description="Ex.: nota comercial, CCB, precatório, consórcio, recebíveis, debênture.")
    estrutura: Optional[str] = Field(description="Quem emite o token, securitizadora/plataforma, instrumento jurídico, regulação (ex.: CVM 88).")
    devedor: Optional[str] = Field(description="Companhia/devedor que paga a dívida que lastreia o token.")
    cnpj_devedor: Optional[str]
    setor_devedor: Optional[str]
    indexador: Literal["prefixado", "cdi", "ipca", "incc", "dolar", "outro"]
    taxa_anual_pct: Optional[float] = Field(description="Para prefixado: a taxa em % a.a. (ex.: 17.0). Para pós-fixado: o spread em % a.a.")
    rentabilidade_texto: str = Field(description="Como a lâmina descreve a rentabilidade, literal.")
    rentabilidade_liquida_de_taxas: Optional[bool] = Field(description="True se a lâmina diz que a taxa já é líquida de taxas/custos.")
    data_emissao: Optional[str] = Field(description="AAAA-MM-DD")
    data_vencimento: Optional[str] = Field(description="AAAA-MM-DD")
    prazo_meses: Optional[int]
    periodicidade_pagamento: Literal["mensal", "trimestral", "semestral", "anual", "no_vencimento", "irregular", "desconhecida"]
    amortizacao: Literal["bullet", "price", "sac", "personalizada", "desconhecida"] = Field(
        description="bullet = principal todo no vencimento; price = parcelas iguais; sac = amortização constante."
    )
    carencia_meses: Optional[int] = Field(description="Meses sem pagamento de principal (e/ou juros) no início.")
    valor_emissao_brl: Optional[float]
    aporte_minimo_brl: Optional[float]
    garantias: List[str]
    reforcos_de_credito: List[str] = Field(description="Subordinação, fundo de reserva, coobrigação, seguro etc.")
    rating: Optional[str]
    cashback_pct: Optional[float] = Field(description="Cashback em % do valor aplicado, se a lâmina mencionar (ex.: 3.0).")
    condicoes_cashback: Optional[str]
    liquidez: Optional[str] = Field(description="Possibilidade de venda antes do vencimento / mercado secundário.")
    tributacao: Optional[str]
    taxas_e_custos: Optional[str]
    cenarios_da_lamina: List[str] = Field(description="Cenários de retorno (base/pessimista/otimista) apresentados na lâmina.")
    riscos_listados: List[str]
    observacoes: Optional[str] = Field(description="Qualquer termo relevante que não coube nos campos acima.")


SISTEMA = (
    "Você é um analista de crédito privado brasileiro. Leia a lâmina de uma oferta de renda fixa "
    "tokenizada e preencha os campos com o que o documento diz. Não invente: quando a lâmina não "
    "trouxer um dado, use null (ou lista vazia). Datas em AAAA-MM-DD; percentuais como número em "
    "pontos percentuais (17% a.a. -> 17.0)."
)


def extrair_dados(caminho_pdf):
    conteudo = [
        llm.bloco_pdf(caminho_pdf),
        {"type": "text", "text": "Extraia os termos desta lâmina."},
    ]
    return llm.estruturar(conteudo, DadosLamina, SISTEMA, esforco="medium")
