#include  <Trade/Trade.mqh>
CTrade trade;


//Declaração de variaveis input 

input int horario_hora_zeragem = 16;
input int horario_minuto_zeragem = 10;
input int horario_hora_inicio = 09;
input int horario_minuto_inicio = 05;
input double dl = 3;
input double p_band1 = 8000;
input double p_band2 = 15000;
input double p_band3 = 28600;
input double entrada_1 = 5;
input double entrada_2 = 5;
input double entrada_3 = 5;
input double gain_1 = 300;
input double gain_2 = 300;
input double gain_3 = 300;
input double stop_1 = 55;
input double stop_2 = 55;
input double stop_3 = 55;
input double parcial = 55;


// Variaveis inteiras
int k,posicao;
int lote = 2;
int op_vwap_compra1 = 0;
int op_vwap_compra2 = 0;
int op_vwap_compra3 = 0;
int op_vwap_venda1 = 0;
int op_vwap_venda2 = 0;
int op_vwap_venda3 = 0;
int contador_protecao;
int contador_operacao;
int cont_parcial;
// Variaveis Float


//Variaveis Double
double preco1,volume1,volume_total1,soma_vol_prec,precoPosicao;
double vwap_real, vwap_compra1,vwap_compra2,vwap_compra3,gain_parcial;
double vwap_venda1,vwap_venda2,vwap_venda3;
double variavel1,variavel2,variavel3;
double entrada,stop,gain,preco_entrada,preco2,volumeTotalAberto;


//Variaveis Booleanas
bool comprado,vendido;
bool ativar_inversao;
bool ativar_inversao_compra1 ;
bool ativar_inversao_compra2 ;

//Variaveis String

string horario,horario2,horario3;



//------------------------------------------------------- Calculo VWAP -----------------------------------------------------------------------//
double VwapBand () {
   double vwapf1;
   
   horario =TimeToString(TimeCurrent(),TIME_MINUTES);
   horario2 = TimeCurrent();
   horario3 = TimeTradeServer();
   Print(horario3);
   
   int horario_hora;
   int horario_minuto;  
   
   horario_hora = (int) StringToInteger(StringSubstr(horario,0,2));
   horario_minuto = (int) StringToInteger(StringSubstr(horario,3,2));
   
   if(horario_hora == horario_hora_inicio && horario_minuto < horario_minuto_inicio){
   volume1 = 0;
   volume_total1 = 0;
   soma_vol_prec = 0;
   }
   
   
   
   
   //preco1 = iClose(Symbol(), Period(), 0); 
   preco1 = SymbolInfoDouble(_Symbol,SYMBOL_LAST);
   volume1 = SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_REAL);
   volume_total1 = volume_total1 + volume1;
   soma_vol_prec = soma_vol_prec + (preco1*volume1);
   if(volume_total1 >0) {
      vwapf1 = soma_vol_prec/volume_total1;
   }
   

   
 
   return vwapf1;
}


//--------------------------------------- Calculo se é novo candle --------------------------------------------------------------------------//


bool isNewBar()
  {
//--- memorize the time of opening of the last bar in the static variable
   static datetime last_time=0;
//--- current time
   datetime lastbar_time=SeriesInfoInteger(Symbol(),Period(),SERIES_LASTBAR_DATE);

//--- if it is the first call of the function
   if(last_time==0)
     {
      //--- set the time and exit
      last_time=lastbar_time;
      return(false);
     }

//--- if the time differs
   if(last_time!=lastbar_time)
     {
      //--- memorize the time and return true
      last_time=lastbar_time;
      return(true);
     }
//--- if we passed to this line, then the bar is not new; return false
   return(false);
  }

//-------------------------------------------------- Verifica se tem posição em aberto ------------------------------------------//
bool ExistPendingOrder()
{
  for(int i = OrdersTotal() - 1; i >= 0; i--)
  {
    ulong ticket = OrderGetTicket(i);
    if(ticket > 0)
    {
      ENUM_ORDER_TYPE orderType = (ENUM_ORDER_TYPE)OrderGetInteger(ORDER_TYPE);
      if(orderType == ORDER_TYPE_BUY_LIMIT || orderType == ORDER_TYPE_SELL_LIMIT || orderType == ORDER_TYPE_BUY_STOP || orderType == ORDER_TYPE_SELL_STOP)
      {
        Print("Ordem pendente encontrada com o ticket: ", ticket);
        return true;
      }
    }
  }
  return false;
}


void OnInit() {
   Print("O robo iniciou");
   
    op_vwap_compra1 = 0;
    op_vwap_compra2 = 0;
    op_vwap_compra3 = 0;
    op_vwap_venda1 = 0;
    op_vwap_venda2 = 0;
    op_vwap_venda3 = 0;

}

//------------------------------------------------ Código Principal --------------------------------------------------------------------------//
void OnTick() {

   preco1 = SymbolInfoDouble(_Symbol,SYMBOL_LAST);
   
   
   // Calculo da Vwap//
      vwap_real = VwapBand();
   
      variavel1 = preco1*dl/100000*p_band1/1000;
      variavel2 = preco1*dl/100000*p_band2/1000;
      variavel3 = preco1*dl/100000*p_band3/1000; 
      
      vwap_compra1 = vwap_real - variavel1;
      vwap_compra2 = vwap_real - variavel2;
      vwap_compra3 = vwap_real - variavel3;
      vwap_venda1 = vwap_real + variavel1;
      vwap_venda2 = vwap_real + variavel2;
      vwap_venda3 = vwap_real + variavel3;
     
      
      if(PositionSelect(_Symbol)==true) {
         posicao = PositionGetDouble(POSITION_VOLUME);
      } else
          {
           posicao = 0;
          }
      
      
      int horario_hora;
      int horario_minuto;  
      
      horario_hora = (int) StringToInteger(StringSubstr(horario,0,2));
      horario_minuto = (int) StringToInteger(StringSubstr(horario,3,2));

      if(posicao == 0) {
         contador_operacao = 0;
         cont_parcial = 0;
         comprado = false;
         vendido = false;
      }
      
      if(posicao == 0 && horario_hora>=horario_hora_inicio && horario_minuto >= horario_minuto_inicio && horario_hora <= horario_hora_zeragem && horario_minuto < horario_minuto_zeragem && contador_operacao == 0){
         
         //---------------------------------------------------- Operações Compra ------------------------------------------------//
         
         if(preco1 >= vwap_compra3 - entrada_3 && preco1 <= vwap_compra3 + entrada_3 && contador_operacao == 0 && op_vwap_compra3 == 0) {
            stop = preco1 - stop_3;
            gain = preco1 + gain_3;
            gain_parcial = preco1  + parcial;
            preco2 = preco1;
            trade.Buy(lote,_Symbol,preco2,stop,gain,"Compra Vwap 3");
            contador_operacao = 1;
            op_vwap_compra3 = 1;
            comprado = true;
            vendido = false;
         
         } else if (preco1 >= vwap_compra2 - entrada_2 && preco1 <= vwap_compra2 + entrada_2 && contador_operacao == 0 && op_vwap_compra2 ==0) {
                  stop = preco1 - stop_2;
                  gain = preco1 + gain_2;
                  gain_parcial = preco1  + parcial;
                  preco2 = preco1;
                  trade.Buy(lote,_Symbol,preco2,stop,gain,"Compra Vwap 2");
                  contador_operacao = 1;
                  op_vwap_compra2 =1;
                  comprado = true;
                  vendido = false;
            
         } else if (preco1 >= vwap_compra1 - entrada_1 && preco1 <= vwap_compra1 + entrada_1 && contador_operacao == 0 && op_vwap_compra1 == 0) {
                  stop = preco1 - stop_1;
                  gain = preco1 + gain_1;
                  gain_parcial = preco1  + parcial;
                  preco2 = preco1;
                  trade.Buy(lote,_Symbol,preco2,stop,gain,"Compra Vwap 1");
                  contador_operacao = 1;
                  op_vwap_compra1 = 1;
                  comprado = true;
                  vendido = false;
         
         
         }
         
         //----------------------------------------- operações venda --------------------------------------------//
         
         if(preco1 <= vwap_venda3 + entrada_3 && preco1 >= vwap_venda3 - entrada_3 && contador_operacao == 0 && op_vwap_venda3 ==0) {
            stop = preco1 + stop_3;
            gain = preco1 - gain_3;
            gain_parcial = preco1 - parcial;
            preco2 = preco1;
            trade.Sell(lote,_Symbol,preco2,stop,gain,"Venda Vwap 3");
            contador_operacao = 1;
            op_vwap_venda3 = 1;
            comprado = false;
            vendido = true; 
         
         } else if (preco1 <= vwap_venda2 + entrada_2 && preco1 >= vwap_venda2 - entrada_2 && contador_operacao == 0 && op_vwap_venda2 == 0) {
                  stop = preco1 + stop_2;
                  gain = preco1 - gain_2;
                  gain_parcial = preco1 - parcial;
                  preco2 = preco1;
                  trade.Sell(lote,_Symbol,preco2,stop,gain,"Venda Vwap 2");
                  contador_operacao = 1;
                  op_vwap_venda2 = 1;
                  comprado = false;
                  vendido = true;
                     
         } else if (preco1 <= vwap_venda1 + entrada_1 && preco1 >= vwap_venda1 - entrada_1 && contador_operacao == 0 && op_vwap_venda1 == 0) {
                  stop = preco1 + stop_1;
                  gain = preco1 - gain_1;
                  gain_parcial = preco1 - parcial;
                  preco2 = preco1;
                  trade.Sell(lote,_Symbol,preco2,stop,gain,"Venda Vwap 1");
                  contador_operacao = 1;
                  op_vwap_venda1 = 1;
                  comprado = false;
                  vendido = true;
                  
         
         
         }
      
      }
     
      //------------------------------------------------------ Verificação das Parciais ------------------------------------------------//
      
      precoPosicao = PositionGetDouble(POSITION_PRICE_OPEN);
      double intermedio_compra = preco2 + parcial;
      double intermedio_venda = preco2 - parcial;

      if(comprado == true && preco1 >= intermedio_compra && cont_parcial == 0) {
         trade.PositionClosePartial(_Symbol,lote/2,10);
         cont_parcial = 1;
      }
      
      if(vendido == true && preco1 <= intermedio_venda && cont_parcial == 0) {
         trade.PositionClosePartial(_Symbol,lote/2,10);
         cont_parcial = 1;
      }

      
      
    
      
      //------------------------------------------------------ Operações de Zeragem -----------------------------------------------------//
 
 
       
      // Checa se é hora de zerar
      if (horario_hora == horario_hora_zeragem && horario_minuto == horario_minuto_zeragem && contador_operacao == 1 && posicao !=0 ) {
          trade.PositionClose(_Symbol,10);
             op_vwap_compra1 = 0;
             op_vwap_compra2 = 0;
             op_vwap_compra3 = 0;
             op_vwap_venda1 = 0;
             op_vwap_venda2 = 0;
             op_vwap_venda3 = 0;
      } 







   

}
