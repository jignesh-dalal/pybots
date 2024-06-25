import pandas as pd
import pandas_ta as ta
import utils as f
import math

from kite_trade import *
from datetime import datetime, timedelta


user_id = 'SJ0281'
config = f.get_creds_by_user_id(user_id)

enctoken = config["ACCESS_TOKEN"]
try:
    kite = KiteApp(enctoken, user_id)
    kite.profile()['user_id']
except Exception as ex:
    if 'NoneType' in str(ex):
        pwd = config["PASSWORD"]
        totp_key = config["TOTP_KEY"]
        totp = get_totp(totp_key)
        enctoken = get_enctoken(user_id, pwd, totp)
        kite = KiteApp(enctoken)
    else: print(f'login error: {str(ex)}')


def apply_total_signal(df, rsi_threshold_low=30, rsi_threshold_high=70, bb_width_threshold = 0.0015):
    # Initialize the 'TotalSignal' column
    df['TotalSignal'] = 0

    for i in range(1, len(df)):
        # Previous candle conditions
        prev_candle_closes_below_bb = df['Close'].iloc[i-1] < df['bbl'].iloc[i-1]
        prev_rsi_below_thr = df['rsi'].iloc[i-1] < rsi_threshold_low
        # Current candle conditions
        closes_above_prev_high = df['Close'].iloc[i] > df['High'].iloc[i-1]
        closes_above_bbl = df['Close'].iloc[i] > df['bbl'].iloc[i]
        bb_width_greater_threshold = df['bb_width'].iloc[i] > bb_width_threshold

        # Combine conditions
        if (prev_candle_closes_below_bb and
            prev_rsi_below_thr and
            # closes_above_prev_high and
            closes_above_bbl and
            bb_width_greater_threshold):
            df.at[i, 'TotalSignal'] = 2  # Set the buy signal for the current candle

        # Previous candle conditions
        prev_candle_closes_above_bb = df['Close'].iloc[i-1] > df['bbh'].iloc[i-1]
        prev_rsi_above_thr = df['rsi'].iloc[i-1] > rsi_threshold_high
        # Current candle conditions
        closes_below_prev_low = df['Close'].iloc[i] < df['Low'].iloc[i-1]
        bb_width_greater_threshold = df['bb_width'].iloc[i] > bb_width_threshold

        # Combine conditions
        if (prev_candle_closes_above_bb and
            prev_rsi_above_thr and
            closes_below_prev_low and
            bb_width_greater_threshold):
            df.at[i, 'TotalSignal'] = 1  # Set the sell signal for the current candle


    return df


nifty750 = f.get_all_records_from_sheet(worksheet_name='Nifty750')
nifty750 = [x for x in nifty750 if x['IToken'] != -1]


to_date = datetime.now()
from_date = to_date - timedelta(days=90)
#inst_token = 701185
# from_date = '2024-04-19'
# to_date = '2024-04-22'

buy_symbols = []
total_signals = 0
slcoef = 2
TPcoef = 2.5

df_s = pd.DataFrame()

for stock in nifty750:
    symbol = stock['Symbol']
    inst_token = stock['IToken']
    benchmark_index = stock['Index']
    data = kite.historical_data(inst_token, from_date, to_date, 'day')
    df = pd.DataFrame(data)
    #df['date']=pd.to_datetime(df['date'],format='%d.%m.%Y %H:%M:%S')

    # Calculate Bollinger Bands and RSI using pandas_ta
    df.ta.bbands(append=True, length=20, std=2)
    df.ta.rsi(append=True, length=14)
    df["atr"] = ta.atr(low = df.Low, close = df.Close, high = df.High, length=14)

    # Rename columns for clarity if necessary
    df.rename(columns={
        'BBL_20_2.0': 'bbl', 'BBM_20_2.0': 'bbm', 'BBU_20_2.0': 'bbh', 'RSI_14': 'rsi'
    }, inplace=True)

    # Calculate Bollinger Bands Width
    df['bb_width'] = (df['bbh'] - df['bbl']) / df['bbm']

    apply_total_signal(df=df, rsi_threshold_low=30, rsi_threshold_high=70, bb_width_threshold=0.001)

    # df_last = df.iloc[-1]
    df_last = df.tail(1)
    
    # latest_signal = df_last['TotalSignal']
    if df_last['Close'].iloc[-1] < 10000 and df_last['TotalSignal'].iloc[-1] == 2:
        df_last.insert(1, 'Symbol', symbol)
        df_last.insert(2, 'IToken', inst_token)
        df_last.insert(3, 'BIndex', benchmark_index)
        
        slatr = slcoef * df_last['atr'].iloc[-1]
        tpatr = TPcoef * df_last['atr'].iloc[-1]
        sl = df_last['Close'].iloc[-1] - slatr
        tp = df_last['Close'].iloc[-1] + tpatr

        df_last.insert(4, 'SL', sl)
        df_last.insert(5, 'TP', tp)

        df_s = pd.concat([df_s, df_last], ignore_index=True)
    

    # df_signals = df[df.TotalSignal == 2]
    # total_signals += len(df_signals)
    # print(f"{symbol} - {inst_token} - {df_signals['Date'].dt.strftime('%m/%d/%Y').to_list()} - {df_last['TotalSignal'].iloc[-1]}")
    # print(f"{s} - {df_last['TotalSignal']} - {df_last['bb_width']} - {df_last['rsi']}")

    time.sleep(0.1)
    

MAX_TRADES = 5
df_t = pd.DataFrame()
if len(df_s) > MAX_TRADES:
    tsymbols = []
    while(len(df_t) < MAX_TRADES):
        df_s_f = df_s[~df_s['Symbol'].isin(tsymbols)]
        n50 = df_s_f[df_s_f['BIndex'] == 'NIFTY'] 
        nn50 = df_s_f[df_s_f['BIndex'] == 'NIFTYJR'] 
        mid150 = df_s_f[df_s_f['BIndex'] == 'NIFTYMIDCAP150'] 
        small250 = df_s_f[df_s_f['BIndex'] == 'NIFTYSMLCAP250'] 
        micro250 = df_s_f[df_s_f['BIndex'] == 'NIFTY_MICROCAP250']

        if (len(n50) > 0):
            n50_h = n50.head(1)
            tsymbols.append(n50_h['Symbol'].iloc[-1])
            df_t = pd.concat([df_t, n50_h], ignore_index=True)
        
        if (len(nn50) > 0 and len(df_t) < MAX_TRADES):
            nn50_h = nn50.head(1)
            tsymbols.append(nn50_h['Symbol'].iloc[-1])
            df_t = pd.concat([df_t, nn50_h], ignore_index=True)

        if (len(mid150) > 0 and len(df_t) < MAX_TRADES):
            mid150_h = mid150.head(1)
            tsymbols.append(mid150_h['Symbol'].iloc[-1])
            df_t = pd.concat([df_t, mid150_h], ignore_index=True)

        if (len(small250) > 0 and len(df_t) < MAX_TRADES):
            small250_h = small250.head(1)
            tsymbols.append(small250_h['Symbol'].iloc[-1])
            df_t = pd.concat([df_t, small250_h], ignore_index=True)

        if (len(micro250) > 0 and len(df_t) < MAX_TRADES):
            micro250_h = micro250.head(1)
            tsymbols.append(micro250_h['Symbol'].iloc[-1])
            df_t = pd.concat([df_t, micro250_h], ignore_index=True)
            
else:
    df_t = df_s

df_t
        

MAX_AMT_PER_TRADE = 10000

for index, row in df_t.iterrows():
    price = row['Close']
    qty = math.floor(MAX_AMT_PER_TRADE / price)

    try:
        order_id = kite.place_order(variety=kite.VARIETY_REGULAR,
                            exchange=kite.EXCHANGE_NSE,
                            tradingsymbol=row['Symbol'],
                            transaction_type=kite.TRANSACTION_TYPE_BUY,
                            quantity=qty,
                            product=kite.PRODUCT_CNC,
                            order_type=kite.ORDER_TYPE_LIMIT,
                            price=price,
                            validity=None,
                            disclosed_quantity=None,
                            trigger_price=None,
                            squareoff=None,
                            stoploss=None,
                            trailing_stoploss=None,
                            tag='BB20 + RSI')
    
        # if order_id is not None:
        #     count = 0
        #     order_history = []
        #     order_status = ''
        #     while order_status != 'COMPLETE':
        #         order_history = kite.order_history(order_id)
        #         order_status = order_history[-1].get('status')
        #         count += 1
        #         # print(f'Count: {count}')
        #         if count < 5: time.sleep(1)  
        #         else: break
            
        #     if order_status == 'COMPLETE':

        kite.place_gtt(trigger_type=kite.GTT_TYPE_OCO, 
                tradingsymbol=row['Symbol'],
                exchange=kite.EXCHANGE_NSE,
                trigger_values=[row['SL'], row['TP']],
                last_price=price,
                orders=[
                    {
                        'exchange': kite.EXCHANGE_NSE,
                        'transaction_type': kite.TRANSACTION_TYPE_SELL,
                        'quantity': qty,
                        'order_type': kite.ORDER_TYPE_LIMIT,
                        'product': kite.PRODUCT_CNC,
                        'price': row['SL']
                    },
                    {
                        'exchange': kite.EXCHANGE_NSE,
                        'transaction_type': kite.TRANSACTION_TYPE_SELL,
                        'quantity': qty,
                        'order_type': kite.ORDER_TYPE_LIMIT,
                        'product': kite.PRODUCT_CNC,
                        'price': row['TP']
                    }
                ])
    except Exception as ex:
        print(f'Error: {str(ex)}')
