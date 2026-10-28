# Agente de análise de Renda Fixa Digital (Mercado Bitcoin)

Analisa títulos de renda fixa tokenizada do MB, com foco nos **prefixados com cashback em bitcoin**.
Para cada título:

1. **Baixa a lâmina** (PDF).
2. **Extrai os termos da emissão** com o Claude: devedor, lastro, taxa, prazo, fluxo, garantias, riscos etc.
3. **Calcula risco x retorno em código**: TIR com e sem cashback, prêmio sobre o Tesouro Prefixado de
   mesma duration, PD (probabilidade de default) implícita, duration e sensibilidade a juros, retorno
   esperado para várias PDs e taxa real.
4. **Pesquisa na web e escreve o relatório** com o Claude (busca e leitura de páginas): a companhia (CNPJ,
   sócios, processos, recuperação judicial, notícias), o setor, a estrutura da oferta e a tributação.
   Termina com notas de 0 a 10, recomendação e tamanho máximo de posição.
5. **Monta um ranking** de todos os títulos analisados.

## Instalação

```bash
pip install -r renda_fixa_mb/requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...      # ou faça `ant auth login`
```

## Uso

Rode a partir da raiz do repositório. Você pode combinar as fontes de títulos.

```bash
# Lâminas que você já baixou do app/site do MB
python -m renda_fixa_mb --pdf ~/Downloads/Lamina-RFD*.pdf

# URLs das lâminas
python -m renda_fixa_mb --lamina https://www.mercadobitcoin.com.br/wp-content/uploads/AAAA/MM/Lamina-XXXX.pdf

# Uma página de ofertas: o agente procura links para lâminas
# (--renderizar abre a página num navegador headless, para páginas montadas via JavaScript;
#  requer `pip install playwright && playwright install chromium`)
python -m renda_fixa_mb --pagina https://www.mercadobitcoin.com.br/<pagina-de-ofertas> --renderizar

# O Claude procura na web as ofertas abertas e as lâminas (só baixa PDFs do domínio mercadobitcoin.com.br)
python -m renda_fixa_mb --descobrir
python -m renda_fixa_mb --descobrir "prefixado acima de 16% a.a. com cashback de 3% em bitcoin"
```

O app do MB normalmente exige login para listar as ofertas. Por isso a forma mais confiável é baixar
as lâminas pelo app e passá-las com `--pdf`.

### Premissas (ajuste ao seu caso)

| Opção | Padrão | O que é |
|---|---|---|
| `--cashback` | 3 | Cashback em % do aplicado, pago em BTC. Se a lâmina ou a descoberta informar outro valor, ele prevalece. |
| `--ir-token` | 0 | Alíquota de IR sobre o ganho do token. O padrão supõe a isenção de vendas de cripto até R$ 35 mil/mês; use 15 se você passa desse limite. **Confira a regra vigente.** |
| `--recuperacao` | 30 | % do capital recuperado se o devedor der default. Usado na PD implícita. |
| `--taxa-tesouro` | curva do dia | Taxa livre de risco fixa (% a.a.) em vez da curva do Tesouro Prefixado. |
| `--vol-btc` | histórica 12m | Volatilidade anual do BTC (%) para os cenários do cashback. |

Outras opções: `--esforco` (profundidade da análise, padrão `high`), `--sem-web`, `--incluir-outros`
(analisa também títulos pós-fixados, sem as métricas), `--paralelo N`, `--refazer`, `--saida PASTA`.

## Saída

Em `saida_renda_fixa/` (ou `--saida`):

- `<CODIGO>.md`: relatório completo do título, com a tabela de métricas e as fontes.
- `<CODIGO>.json`: termos extraídos, métricas, relatório e parecer estruturado.
- `ranking.md` / `ranking.csv`: todos os títulos ordenados pela nota final.
- `laminas/` e `cache/`: PDFs baixados, termos extraídos e o CSV do Tesouro. Rodar de novo reaproveita o
  que já foi feito; use `--refazer` para recalcular.

## Como ler as métricas

- **TIR com cashback (BTC vendido na hora)**: o cashback reduz o preço efetivo de entrada. Um cashback de 3%
  num título de 2 anos rende bem mais que 1,5 p.p. ao ano se o título amortiza (price/SAC), porque o
  capital volta antes.
- **TIR com BTC mantido (P5 / mediana / P95)**: se você segurar o BTC até o vencimento, o cashback vira um
  ativo volátil. Cenários de um passeio lognormal sem tendência com a volatilidade histórica.
- **Prêmio sobre o Tesouro**: quanto o título paga acima do Tesouro Prefixado de mesma duration. O bruto é
  sem cashback; o líquido desconta IR (regressivo + custódia B3 no Tesouro; `--ir-token` no token) e inclui
  o cashback.
- **PD implícita**: a probabilidade anual de default que zeraria o prêmio, dada a recuperação. Se você
  acha que o devedor tem chance de quebrar maior que isso, o título paga pouco pelo risco.
- **Perda se os juros subirem 1 p.p.**: risco de marcação a mercado se você precisar vender antes.

Simplificações: na carência os juros são capitalizados; cronogramas irregulares são tratados como bullet
(o relatório avisa); o IR é aproximado de forma proporcional em cada pagamento.

## Custos e modelo

Usa o Claude Opus 5.5 (`claude-opus-5-5`) pela API da Anthropic. A extração e o parecer são chamadas
curtas; a análise faz até 15 buscas e 10 leituras de páginas por título. Estimativa (ainda não medida):
algo na ordem de US$ 1 a US$ 3 por título, conforme o tamanho da pesquisa; `--esforco medium` e `--sem-web` reduzem o custo.
Se o modelo recusar uma requisição, a API refaz automaticamente no modelo de fallback recomendado
(`fallbacks: "default"`).

## Fontes de dados de mercado

BCB/SGS (Selic meta, CDI, IPCA 12m), Focus (IPCA esperado 12m), Tesouro Transparente (taxas do Tesouro
Prefixado) e candles BTC-BRL do MB (com CoinGecko como alternativa). Se alguma falhar, o agente avisa e
segue; use `--taxa-tesouro` e `--vol-btc` para informar os valores manualmente.

## Testes

```bash
python -m unittest discover -s renda_fixa_mb/tests -t .
```

Análise automatizada para apoiar a decisão; não é recomendação de investimento. Tokens de renda fixa
digital não têm FGC e podem ter pouca liquidez antes do vencimento.
