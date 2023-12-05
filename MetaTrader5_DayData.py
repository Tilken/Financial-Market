import pandas as pd
import numpy as np
import time
import MetaTrader5 as mt5 
import asyncio
from datetime import datetime
import pytz


#------------------------------------------------- Inicialização MT5
if mt5.initialize():
    print("MT5 Inicializou com sucesso")
else:
    print("Falha ao inicializar MT5")

#------------------------------------------------ Parâmetros 
ativo = "WINZ23"
time_frame = mt5.TIMEFRAME_M1
#------------------------------------------------- Definição de indicadores


def media_movel_simples(df,periodo):
    return df['open'].rolling().mean(periodo)  # Exemplo

#------------------------------------------------ Definição de funções principais
def buscar_ativo(ativo, timeframe, tempo, numero_candles):
    try:
        rates = mt5.copy_rates_from(ativo, timeframe, tempo, numero_candles)
        if rates is None or len(rates) == 0:
            print("Nenhum dado foi retornado pela função copy_rates_from.")
            return None
        ativo_df = pd.DataFrame(rates)
        ativo_df['time'] = pd.to_datetime(ativo_df['time'], unit='s')
        ativo_df.set_index('time', inplace=True)
        return ativo_df
    except Exception as e:
        print(f"Erro ao buscar os dados do ativo: {e}")
        return None

def numero_de_candles():
    agora = datetime.now()
    inicio_do_dia = agora.replace(hour=9, minute=0, second=0, microsecond=0)
    final = inicio_do_dia.replace(hour=18,minute=30,second=0,microsecond=0)
    
    # Se ainda não chegou às 9 da manhã, o mercado ainda não abriu
    if agora < inicio_do_dia:
        return 0
    if agora >= final :
        diferenca_em_minutos = int((agora - inicio_do_dia).total_seconds() / 60)
        return diferenca_em_minutos
    
    # Se for depois das 9 da manhã, calcule a diferença em minutos desde as 9 até agora
    diferenca_em_minutos = int((agora - inicio_do_dia).total_seconds() / 60)
    return diferenca_em_minutos

async def processamento_dados(ativo, timeframe, inicio_do_dia):
    while True:
        numero_candles_atual = numero_de_candles()
        if numero_candles_atual > 0:
            # Certifique-se de que 'inicio_do_dia' esteja definido corretamente como o início do dia de negociação
            cotacao = buscar_ativo(ativo, timeframe, inicio_do_dia, numero_candles_atual)
            cotacao = pd.DataFrame(cotacao)
            if cotacao is not None:
                print(cotacao)  # Imprime as últimas 5 linhas para verificar
            else:
                print("Não foi possível obter a cotação atual.")
        else:
            print("Mercado ainda não abriu.")
        
        
        # Código principal com os "PARAMETROS, luke"


        await asyncio.sleep(15)


# -------------------------------------------------- Código Principal

async def main():
    # Defina o fuso horário do mercado
    fuso_horario_do_mercado = pytz.timezone('America/Sao_Paulo')
    
    # Defina 'inicio_do_dia' com o fuso horário correto
    inicio_do_dia = datetime.now()
    print(inicio_do_dia)
    # Inicie o processamento de dados
    await processamento_dados(ativo, time_frame, inicio_do_dia)

# Execute o main
asyncio.run(main())
