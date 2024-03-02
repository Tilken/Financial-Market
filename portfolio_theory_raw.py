import yfinance as yf
import pandas as pd
import numpy as np
from scipy.optimize import minimize
import matplotlib.pyplot as plt
import requests
from bs4 import BeautifulSoup


def coletar_dados_yahoo(ativos, data_inicio, data_fim):
    dados = {}
    for ativo in ativos:
        try:
            df = yf.download(ativo, start=data_inicio, end=data_fim)
            if df.empty:
                print(f"Erro ao coletar dados para o ativo {ativo}. DataFrame vazio.")
                continue
            dados[ativo] = df
        except Exception as e:
            print(f"Erro ao coletar dados para o ativo {ativo}. Erro: {e}")
            continue
    return dados


def calcular_matriz_correlacao(dados):
    df_retornos = pd.DataFrame()
    for ativo, df in dados.items():
        df_retornos[ativo] = df['Adj Close'].pct_change().fillna(0)
    return df_retornos.corr()

def calcular_fronteira_eficiente(dados,retornos_dividendos):
    retornos = {}
    for ativo, df in dados.items():
        retornos[ativo] = df['Adj Close'].pct_change().dropna()
    df_retornos = pd.DataFrame(retornos)
    
    media_retornos = pd.Series(retornos_dividendos)
    matriz_cov = df_retornos.cov()
    
    num_portfolios = 100000  # Reduzindo para 100.000 portfólios
    resultados = np.zeros((4, num_portfolios))
    pesos_array = []
    
    num_ativos = len(media_retornos)  # Usando o número correto de ativos
    # Usando o número correto de ativos
    
    # Incluindo a renda fixa na matriz de covariância
    if "Selic" in retornos_dividendos:
        df_retornos["Selic"] = [retornos_dividendos["Selic"]] * len(df_retornos)
        matriz_cov = df_retornos.cov()
        matriz_cov["Selic"] = 0
        matriz_cov.loc["Selic"] = 0
        
        
    for i in range(num_portfolios):
        pesos = np.random.random(num_ativos)  # Gerando pesos com base no número correto de ativos
        pesos /= np.sum(pesos)
        retorno_portfolio = np.sum(media_retornos * pesos)
        volatilidade_portfolio = np.sqrt(np.dot(pesos.T, np.dot(matriz_cov, pesos)))
        resultados[0,i] = retorno_portfolio
        resultados[1,i] = volatilidade_portfolio
        resultados[2,i] = resultados[0,i] / resultados[1,i]
        pesos_array.append(pesos)
        
        # Exibindo a progressão
        if (i+1) % 100 == 0:
            print(f"{i+1} portfólios gerados...")
    
    retornos_esperados = resultados[0]
    volatilidades = resultados[1]
    pesos = pesos_array
    
    return retornos_esperados, volatilidades, pesos

def plotar_fronteira_eficiente(retornos_esperados, volatilidades):
    plt.figure(figsize=(10, 6))
    plt.scatter(volatilidades, retornos_esperados, c=retornos_esperados / volatilidades, marker='o')
    plt.title('Fronteira Eficiente')
    plt.xlabel('Volatilidade Esperada')
    plt.ylabel('Retorno Esperado')
    plt.colorbar(label='Índice de Sharpe')
    plt.show()

def rebalancear_portfolio(dados, pesos_otimizados, ativos, quantidades, precos_medios):
    # Calcula o valor atual do portfólio
    valor_atual = sum([q * p for q, p in zip(quantidades, precos_medios)])

    # Calcula o valor recomendado para cada ativo
    valores_recomendados = [valor_atual * peso for peso in pesos_otimizados]

    # Calcula a diferença entre o valor atual e o valor recomendado
    diferenca = [valor_recomendado - (q * p) for valor_recomendado, q, p in zip(valores_recomendados, quantidades, precos_medios)]

    recomendacoes = {}
    for ativo, dif in zip(ativos, diferenca):
        if dif > 0:
            recomendacoes[ativo] = f"Comprar aproximadamente R${dif:.2f}"
        elif dif < 0:
            recomendacoes[ativo] = f"Vender aproximadamente R${-dif:.2f}"
        else:
            recomendacoes[ativo] = "Manter"

    return recomendacoes

def calcular_valor_portfolio(quantidades, precos):
    return sum([q * p for q, p in zip(quantidades, precos)])

def recomendar_alocacao(pesos_otimizados, ativos, dados, quantidades, risco_desejado, retorno_desejado):
    # Calcula o valor atual do portfólio
    precos_recentes = [dados[ativo]['Adj Close'].iloc[-1] if ativo != "Selic" else 1 for ativo in ativos]
    valor_atual = sum([q * p for q, p in zip(quantidades, precos_recentes)])

    # Calcula o valor recomendado para cada ativo com base nos pesos otimizados
    valores_recomendados = [valor_atual * peso for peso in pesos_otimizados]
    
    # Calcula a diferença entre o valor atual e o valor recomendado
    diferenca = [valor_recomendado - (q * p) for valor_recomendado, q, p in zip(valores_recomendados, quantidades, precos_recentes)]
    
    recomendacoes = {}
    posicoes_zeradas = []  # Lista para armazenar as ações que estão sendo zeradas
    dinheiro_na_carteira = 0  # Valor que ficará na carteira
    
  
        
    for ativo, dif, preco_recente in zip(ativos, diferenca, precos_recentes):
        if dif > 0:
            # Se a recomendação de compra for menor que o preço de uma ação, o dinheiro ficará na carteira
            if dif < preco_recente:
                dinheiro_na_carteira += dif
                recomendacoes[ativo] = "Manter"
            else:
                recomendacoes[ativo] = f"Comprar aproximadamente R${dif:.2f}"
        elif dif < 0:
            if abs(dif) >= quantidades[ativos.index(ativo)] * precos_recentes[ativos.index(ativo)]:
                posicoes_zeradas.append(ativo)
            recomendacoes[ativo] = f"Vender aproximadamente R${-dif:.2f}"
        else:
            recomendacoes[ativo] = "Manter"


    if "Selic" in ativos:
        index_selic = ativos.index("Selic")
        if index_selic < len(pesos_otimizados):  # Verificando se a Selic está nos pesos otimizados
            valor_recomendado_selic = valor_atual * pesos_otimizados[index_selic]
            diferenca_selic = valor_recomendado_selic - quantidades[index_selic] * 1  # Multiplicando por 1 pois o preço médio da Selic é 1
            if diferenca_selic > 0:
                recomendacoes["Selic"] = f"Comprar aproximadamente R${diferenca_selic:.2f} em Selic"
            elif diferenca_selic < 0:
                recomendacoes["Selic"] = f"Vender aproximadamente R${-diferenca_selic:.2f} em Selic"
            else:
                recomendacoes["Selic"] = "Manter investimento em Selic"
    
    if posicoes_zeradas:
        print("\nAções com posição sendo zerada:")
        for ativo in posicoes_zeradas:
            print(ativo)
    
    if dinheiro_na_carteira > 0:
        print(f"\nDinheiro que ficará na carteira: R${dinheiro_na_carteira:.2f}")
    
    return recomendacoes






def gerenciar_portfolio_yahoo_passo2(ativos, precos_medios, quantidades, data_inicio, data_fim):
    # 1. Coleta de Dados
    dados = coletar_dados_yahoo(ativos, data_inicio, data_fim)
    if not dados:
        return "Erro ao coletar dados."
    
    # 2. Matriz de Correlação
    matriz_correlacao = calcular_matriz_correlacao(dados)
    print("Matriz de Correlação:")
    print(matriz_correlacao)
    print("\n")
    
    # 3. Fronteira Eficiente
    retornos_esperados, volatilidades, pesos = calcular_fronteira_eficiente(dados, retornos_dividendos)
    plotar_fronteira_eficiente(retornos_esperados, volatilidades)  # Removido temporariamente, pois a função não foi definida
    
    # 4. Recomendações de Alocação
    risco_desejado = float(input("Informe o risco desejado (volatilidade) como um valor entre 0 e 1 (ex: 0.2 para 20%): "))
    retorno_desejado = float(input("Informe o retorno desejado como um valor entre 0 e 1 (ex: 0.1 para 10%): "))
    
    
    # Aqui, vamos pegar os pesos otimizados que mais se aproximam do risco e retorno desejados
    index = np.argmin(np.sqrt(np.square(np.array(volatilidades) - risco_desejado) + np.square(np.array(retornos_esperados) - retorno_desejado)))
    pesos_otimizados = pesos[index]
   
    valor_atual_portfolio = calcular_valor_portfolio(quantidades, precos_medios)
    print(f"Valor atual do portfólio: R${valor_atual_portfolio:.2f}")

    recomendacoes = recomendar_alocacao(pesos_otimizados, ativos, dados, quantidades, risco_desejado, retorno_desejado)
    
    valor_novo_portfolio = calcular_valor_portfolio(quantidades, [dados[ativo]['Adj Close'].iloc[-1] if ativo != "Selic" else 1 for ativo in ativos])
    print(f"Valor do portfólio após reajuste: R${valor_novo_portfolio:.2f}")

    print("\nRecomendações de Alocação:")
    for ativo, rec in recomendacoes.items():
        print(f"{ativo}: {rec}")
    
    return "Processo concluído!"


def raspar_dividendos_fundamentus(ticker, tipo_ativo):
    # Determinando a URL baseado no tipo de ativo
    if tipo_ativo == 'FII':
        url = f'https://www.fundamentus.com.br/fii_proventos.php?papel={ticker}&tipo=2'
    elif tipo_ativo == 'acao':
        url = f'https://www.fundamentus.com.br/proventos.php?papel={ticker}'
    else:
        print(f"Tipo de ativo {tipo_ativo} não reconhecido.")
        return None

    # Headers para simular uma solicitação de navegador
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    # Fazendo a requisição
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f'Erro ao acessar a página para o ativo {ticker}.')
        return None

    # Usando BeautifulSoup para analisar o conteúdo
    soup = BeautifulSoup(response.content, 'html.parser')

    # Encontrando a tabela de dividendos pelo ID "resultado"
    table = soup.find('table', {'id': 'resultado'})

    # Verificando se a tabela foi encontrada
    if not table:
        print(f'Não foi possível encontrar a tabela de dividendos para o ativo {ticker}.')
        return None

    # Extraindo os cabeçalhos da tabela
    headers = [header.text for header in table.find_all('th')]

    # Extraindo as linhas da tabela
    rows = table.find_all('tr')
    data = []
    for row in rows[1:]:  # Ignorando a primeira linha (cabeçalhos)
        columns = row.find_all('td')
        data.append([column.text for column in columns])

    # Convertendo os dados em um DataFrame
    df = pd.DataFrame(data, columns=headers)

    # Retornando o DataFrame
    return df

def raspar_dividendos_todos_ativos(lista_ativos, tipo_ativo):
    dividendos = {}

    for ativo in lista_ativos:
        print(f"Coletando dividendos para o ativo {ativo}...")
        df = raspar_dividendos_fundamentus(ativo, tipo_ativo)
        if df is not None:
            dividendos[ativo] = df
        else:
            print(f"Não foi possível coletar dividendos para o ativo {ativo}.")

    return dividendos

def calcular_retorno_dividendos(dividendos, preco_medio_inicio):
    total_dividendos = sum([float(div.replace(',', '.').replace('R$ ', '')) for div in dividendos['Provento por ação']])
    return total_dividendos / preco_medio_inicio


def calcular_retorno_total(dados, div_acoes, div_fii, precos_medios):
    retornos_dividendos = {}
    for ativo, df in dados.items():
        if ativo in div_acoes:
            retorno_div = calcular_retorno_dividendos(div_acoes[ativo], precos_medios[ativos.index(ativo)])
        elif ativo in div_fii:
            retorno_div = calcular_retorno_dividendos(div_fii[ativo], precos_medios[ativos.index(ativo)])
        else:
            retorno_div = 0
        retorno_preco = (df['Adj Close'].iloc[-1] - df['Adj Close'].iloc[0]) / df['Adj Close'].iloc[0]
        retornos_dividendos[ativo] = retorno_preco + retorno_div
    return retornos_dividendos


def buscar_rendimento_selic_google():
    try:
        # Fazendo uma solicitação ao Google para buscar o rendimento da Selic
        url = "https://www.google.com/search?q=Valor+da+Selic"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.content, "html.parser")

        # Procurando o elemento que contém o rendimento da Selic
        rendimento_element = soup.find("div", class_="IZ6rdc")
        if rendimento_element:
            rendimento = rendimento_element.text.split("%")[0]
            return float(rendimento.replace(",", "."))
        else:
            print("Não foi possível encontrar o rendimento da Selic.")
            return None
    except Exception as e:
        print(f"Erro ao buscar o rendimento da Selic: {e}")
        return None

# Obtenha o rendimento da Selic
rendimento_selic = 12.25



RF = ["Selic"]
quantidade_rf = [11000]




ativos = ["AAPL34.SA", "GOGL34.SA", "EQTL3.SA", "MSFT34.SA", "VALE3.SA", "EGIE3.SA", "COCA34.SA", "ITSA4.SA", "BERK34.SA", "MSBR34.SA", "TAEE11.SA", "DISB34.SA", "N1DA34.SA", "TRPL4.SA", "JBSS3.SA",
          "HGLG11.SA", "KNRI11.SA", "HGRU11.SA", "MCCI11.SA", "BRCR11.SA", "XPCA11.SA", "RZTR11.SA","Selic"]

acoes = ["AAPL34", "GOGL34", "EQTL3", "MSFT34", "VALE3", "EGIE3", "COCA34", "ITSA4", "BERK34", "MSBR34", "TAEE11", "DISB34", "N1DA34", "TRPL4", "JBSS3"]

qtd_acoes = [200, 145, 225, 100, 100, 142, 117, 567, 50, 52, 100, 85, 18, 100, 53]

PM_acoes = [33.83, 48.87, 25.27, 55.06, 81.45, 44.10, 47.56, 10.04, 74.57, 106.78, 29.31, 73.24, 173.43, 24.98, 18.35]

FII = ["HGLG11", "KNRI11", "HGRU11", "MCCI11", "BRCR11", "XPCA11", "RZTR11"]

qtd_FII = [63, 38, 46, 57, 83, 251, 22]

PM_FII = [152.93, 155.27, 121.61, 100.94, 89.22, 9.96, 99.52]

precos_medios = [33.83, 48.87, 25.27, 55.06, 81.45, 44.10, 47.56, 10.04, 74.57, 106.78, 29.31, 73.24, 173.43, 24.98, 18.35,
                152.93, 155.27, 121.61, 100.94, 89.22, 9.96, 99.52]

quantidades = [200, 145, 225, 100, 100, 142, 117, 567, 50, 52, 100, 85, 18, 100, 53, 63, 38, 46, 57, 83, 251, 22]


data_inicio = "2022-01-01"
data_fim = "2023-10-30" 



if "Selic" in RF:
    ativos.append("Selic")
    quantidades.append(quantidade_rf[0])
    precos_medios.append(1)  # O preço médio da Selic é considerado 1 para simplificar os cálculos

div_acoes = raspar_dividendos_todos_ativos(acoes, "acao")
div_fii = raspar_dividendos_todos_ativos(FII, "FII")

dados = coletar_dados_yahoo(ativos, data_inicio, data_fim)
retornos_dividendos = calcular_retorno_total(dados, div_acoes, div_fii, precos_medios)

# Se o rendimento da Selic foi obtido com sucesso, adicione-o ao dicionário de retornos
if rendimento_selic is not None:
    retornos_dividendos["Selic"] = rendimento_selic / 100  # Convertendo a porcentagem em valor decimal

resultado = gerenciar_portfolio_yahoo_passo2(ativos, precos_medios, quantidades, data_inicio, data_fim)
print(resultado)

