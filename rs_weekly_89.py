import pandas as pd
import utils as f
import argparse
import sys
import math
import numpy as np
import talib

from kite_trade import *
from datetime import datetime, timedelta

# -------------------------------
# Config
# -------------------------------
initial_capital = 100000
risk_per_trade = 0.02    # risk 2% per trade
stop_mode = "percent"    # options: "percent", "atr"
stop_value = 12.0         # % or ATR multiple
## Dynamic max trades based on fixed risk per trade
#max_trades = int(1 / risk_per_trade)
max_trades = 5

# COMMAND LINE ARGS
parser = argparse.ArgumentParser()
parser.add_argument("--uid", help="enter user id", default="SJ0281")
parser.add_argument("--wks", help="enter worksheet name", default="RS_Weekly")
args = parser.parse_args()


def on_ws_ticks(ws, ticks):
    global tick_received, symbol_token_dict
    print(ticks)
    for t in ticks:
        inst_token = t['instrument_token'] 
        if inst_token in symbol_token_dict.keys():
            symbol_token_dict[inst_token]['ltp'] = t['last_price']
            symbol_token_dict[inst_token]['ohlc'] = t['ohlc']
            symbol_token_dict[inst_token]['buy'] = t['depth']['buy']
            symbol_token_dict[inst_token]['sell'] = t['depth']['sell']
    
    tick_received = True


def get_historical_df(symbol, symbol_token, from_date, to_date, interval='day') -> pd.DataFrame:
    try:
        data = broker.historical_data(symbol_token, from_date, to_date, interval)
        df = pd.DataFrame(data)
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.set_index('Date')
        
        df.insert(0, 'Symbol', symbol)
        df.insert(1, 'SymbolToken', symbol_token)

        return df
    except Exception as ex:
        print(f"Symbol->{symbol_token}")
        print(f'Error: {str(ex)}')


# def apply_strategy(df: pd.DataFrame, rsi_length=13, rsi_min=50, rsi_max=65):
    # df['RS'] = (df['Close'] / df['iClose']).fillna(0)
    # # df['RS_MA'] = df['RS'].rolling(89).mean().fillna(0)
    # df['RS_MA'] = talib.EMA(df['RS'], timeperiod=89).fillna(0)
    # df['RS_ABV_SMA'] = (df["RS"] >= df["RS_MA"]).astype(int)
    # df['RS_CROSS'] = df['RS_ABV_SMA'].diff().astype('Int64')

    # # df['RSI'] = ta.rsi(df['Close'], length=rsi_length).fillna(0)
    # df['RSI'] = talib.RSI(df['Close'], timeperiod=rsi_length).fillna(0)
    
    # df['BUY'] = np.where((df['RS_CROSS'] == 1) & (df['RSI'] > rsi_min) & (df['RSI'] < rsi_max), True, False)
    # df['SELL'] = df['RS_CROSS'] == -1

    # return df

def apply_strategy(df: pd.DataFrame, rsi_length=13, rsi_min=50, rsi_max=65):
    # df['RSI'] = talib.RSI(df['Close'], timeperiod=rsi_length).fillna(0)
    df['rs'] = (df['Close'] / df['iClose']).fillna(0)
    # df['rs_ma'] = df['rs'].rolling(89).mean().fillna(0)
    # df['rs_ma'] = ma(df['rs'], 89).fillna(0)
    df['rs_ma'] = talib.EMA(df['rs'], timeperiod=89).fillna(0)
    df['rs_gt_ma'] = np.where((df["rs_ma"] > 0) & (df["rs"] > df["rs_ma"]), 1, 0)
    df['rs_cr'] = df['rs_gt_ma'].diff().astype('Int64')
    # Identify potential crossover points (where ema_short crosses ema_long)
    # Bullish crossover: ema_short was below, now it's above
    df['bl_cr'] = (df['rs'].shift(1) < df['rs_ma'].shift(1)) & (df['rs'] > df['rs_ma'])
    df['br_cr'] = (df['rs'].shift(1) > df['rs_ma'].shift(1)) & (df['rs'] < df['rs_ma'])
    # --- Whipsaw filter implementation ---
    lookback_period = 13  # Check the past n periods

    # Condition for a confirmed bullish crossover:
    # The short EMA must have been below the long EMA for the entire lookback_period *just before* the crossover.
    # We check if 'ema_short' was consistently below 'ema_long' for the 'lookback_period' leading up to the current point.
    # df['bl_cf'] = (df['RS'].shift(1).rolling(window=lookback_period).apply(lambda x: (x < df['rs_ma'].shift(1).loc[x.index]).all(), raw=False))
    df['bl_cf'] = df['rs'].shift(1).rolling(window=lookback_period).apply(lambda x: (x < df['rs_ma'].shift(1).loc[x.index]).all(), raw=False).fillna(False).astype(bool)
    df['br_cf'] = df['rs'].shift(1).rolling(window=lookback_period).apply(lambda x: (x > df['rs_ma'].shift(1).loc[x.index]).all(), raw=False).fillna(False).astype(bool)

    # --- Nearing crossover signal implementation ---
    threshold = 0.003  # Defines how close the EMAs must be to trigger a signal
    slope_lookback = 5 # Defines the period to check EMA direction

    # Calculate the difference between the two EMAs
    df['ma_diff'] = df['rs_ma'] - df['rs']

    # # Bullish alert: Difference is small, and the short EMA is below the long EMA
    # df['nr_bl'] = ((df['ma_diff'] < threshold) & (df['ma_diff'] > 0)).astype(int)
    
    # # Bearish alert: Difference is small, and the short EMA is above the long EMA
    # df['nr_br'] = ((df['ma_diff'] > -threshold) & (df['ma_diff'] < 0)).astype(int) * -1

    # Bullish alert: Difference is small, and the short EMA is *below* the long EMA, AND the short EMA's trend is up
    df['nr_bl'] = np.where(
        (df['ma_diff'] < threshold) & (df['ma_diff'] > 0) & (df['rs'].diff(slope_lookback) > 0), 1, 0)

    # Bearish alert: Difference is small, and the short EMA is *above* the long EMA, AND the short EMA's trend is down
    df['nr_br'] = np.where(
        (df['ma_diff'] > -threshold) & (df['ma_diff'] < 0) & (df['rs'].diff(slope_lookback) < 0), -1, 0)


    # Combine the signals into a final filtered crossover and nearing column
    df['signal'] = 0.0

    # Confirmed crossovers (filtered)
    df.loc[df['bl_cr'] & df['bl_cf'], 'signal'] = 1.0
    df.loc[df['br_cr'], 'signal'] = -1.0

    # Nearing crossovers (as a distinct type of signal)
    df.loc[(df['nr_bl'] == 1) & (df['signal'] == 0.0), 'signal'] = 0.5
    df.loc[(df['nr_br'] == -1) & (df['signal'] == 0.0), 'signal'] = -0.5
    
    # Clean up intermediate columns (optional)
    df.drop(columns=['bl_cr', 'br_cr', 'bl_cf', 'br_cf', 'ma_diff', 'nr_bl', 'nr_br'], inplace=True)

    return df


if __name__ == "__main__":
# -------------------------------
# Broker login
# -------------------------------
    user_id = args.uid
    config = f.get_creds_by_user_id(user_id)

    enctoken = config["ACCESS_TOKEN"]
    broker = None
    try:
        broker = KiteApp(enctoken, user_id)
        broker.profile()['user_id']
    except Exception as ex:
        broker = None
        auto_login = config["AUTO_LOGIN"]      
        if 'NoneType' in str(ex) and auto_login.lower() in ['true', '1', 't', 'y', 'yes']:
            pwd = config["PASSWORD"]
            totp_key = config["TOTP_KEY"]
            totp = get_totp(totp_key)
            enctoken = get_enctoken(user_id, pwd, totp)
            broker = KiteApp(enctoken)
            f.update_values_by_row_key_in_worksheet(user_id, { 'ACCESS_TOKEN': enctoken })
        else: print(f'login error: {str(ex)}')

    if not broker:
        print("Broker not available")
        sys.exit(0)

# -------------------------------
# Strategy
# -------------------------------
    to_date = datetime.now()
    from_date = to_date - timedelta(days=1260)
    ohlc_dict = { 
        'iSymbol': 'first',  
        'iSymbolToken': 'first',
        'iOpen'  : 'first',
        'iHigh'  : 'max',
        'iLow'   : 'min',
        'iClose' : 'last',
        'iVolume': 'sum',
        'Symbol': 'first',  
        'SymbolToken': 'first',  
        'Open'  : 'first',
        'High'  : 'max',
        'Low'   : 'min',
        'Close' : 'last',
        'Volume': 'sum' }
    
    wks_name = args.wks
    
    buy_symbol_itokens = []
    sell_symbol_itokens = []

    instruments = f.get_all_records_from_sheet(worksheet_name=wks_name)
    instruments = [x for x in instruments if (x['InTrade'].lower() in ['true', '1']) and (x['SymbolIToken'] != '')]

    symbol_token_dict = {v['SymbolIToken']: {'symbol':v['Symbol'], 'index': v['Index'], 'index_token': v['IToken'], 'in_trade': v['InTrade'], 'shares': v['Shares'], 'ltp': -1, 'buy': [], 'sell': []} for v in instruments}
  
    inst_itokens = [x['SymbolIToken'] for x in instruments]

    nifty750 = f.get_all_records_from_sheet(worksheet_name='Nifty750')
    nifty750 = [x for x in nifty750 if x['SymbolIToken'] != -1]
    #nifty750 = [x for x in nifty750 if (x['SymbolIToken'] != -1) and (x['Index'] in ["NIFTYMIDCAP150","NIFTYSMLCAP250"])]

    # nifty750 = [s for s in nifty750 if s['Symbol']=="AGI"]

    message = ''

    for stock in nifty750:

        index = stock['Index']
        index_token = stock['IToken']
        symbol = stock['Symbol']
        symbol_token = stock['SymbolIToken']

        df_index = get_historical_df(index, index_token, from_date, to_date)
        
        # Rename columns for clarity if necessary
        df_index.rename(columns={
            'Symbol': 'iSymbol', 'SymbolToken': 'iSymbolToken', 'Open': 'iOpen', 'High': 'iHigh', 'Low': 'iLow', 'Close': 'iClose', 'Volume': 'iVolume'
        }, inplace=True)

        # display(df_index.tail(5))

        df_symbol = get_historical_df(symbol, symbol_token, from_date, to_date, 'day')

        # display(df_symbol.tail(5))

        df = pd.concat([df_index,df_symbol], axis=1)

        # display(df.tail(5))
        
        df = df.resample('W').apply(ohlc_dict)
        # set the index to the beginning of the week
        df.index = df.index - pd.tseries.frequencies.to_offset("6D")

        df = apply_strategy(df)

        # display(df.tail(22))

        latest_signal = df['signal'].iloc[-1]  
        buy_signal = latest_signal in [1]
        if buy_signal:
            # print(df.tail(5))
            buy_symbol_itokens.append(symbol_token)
            symbol_obj = {'symbol':symbol, 'index': index, 'index_token': index_token, 'in_trade': False, 'shares': 0, 'ltp': -1, 'buy': [], 'sell': []}
            symbol_token_dict[symbol_token] = symbol_obj
            message += f"\nBUY: {symbol} | {index}"
    
        sell_signal = latest_signal == -1 and symbol_token in inst_itokens
        if sell_signal:
            sell_symbol_itokens.append(symbol_token)
            message += f"\nSELL: {symbol} | {index}"

    # END FOR LOOP
    if message:
        message = f"RPS Weekly EMA 89\n{message}"
        print(message)
        f.send_telegram_message(message)

    # symbol_tokens = list(symbol_token_dict.keys()) 
    # tick_received = False
    # broker.start_stream(on_ws_ticks, symbol_tokens)

    # count = 0
    # while not tick_received:
        # count += 1
        # # print(f'Count: {count}')
        # if count < 5: time.sleep(1)  
        # else: break    

    # broker.end_stream(symbol_tokens)

    # if not tick_received:
        # print("No trades available")
        # sys.exit(0)

    # # print(symbol_token_dict)

    # message = ''
    # capital = initial_capital
    # trades = [{'symbol_token': t['SymbolIToken'], 'entry': t['Entry'], 'stop': t['Stop'], 'shares': t['Shares'] } for t in instruments]  # list of open trades (dicts)

    # print("ACTIVE TRADES")
    # print(trades)

    # # # risk per trade (always based on initial capital)
    # # fixed_risk_amount = initial_capital * risk_per_trade

    # fixed_amount_per_trade = int(initial_capital / max_trades)
    # active_trades = len(trades) - len(sell_symbol_itokens)
    # if max_trades == active_trades:
        # print("Max trades active so skipping the run!!")
        # sys.exit(0)
    
    # max_trades = max_trades - active_trades

    # for key, asset in symbol_token_dict.items():
        # in_trade = bool(asset['in_trade'])
        # symbol = asset['symbol']
        # symbol_token = key
        # index = asset['index']
        # index_token = asset['index_token']
        
        # closed_trades = []
        # # ---------------- Exit & Stop-loss ----------------
        # if in_trade and symbol_token in sell_symbol_itokens:
            # #print("SELL Logic")
            # order_price = asset['ltp']
            # order_qty = asset['shares']

            # for trade in trades:
                # if symbol_token == trade['symbol_token']:
                    # capital += trade["shares"] * order_price
                    # closed_trades.append(trade)

            # # remove closed trades
            # for t in closed_trades:
                # trades.remove(t)

            # in_trade = False
            # message += f"\n{symbol}({index})->SELL: {order_qty} | Price: {order_price}"

            # try:
                # order_id = broker.place_order(variety=broker.VARIETY_REGULAR,
                                            # exchange=broker.EXCHANGE_NSE,
                                            # tradingsymbol=symbol,
                                            # transaction_type=broker.TRANSACTION_TYPE_SELL,
                                            # quantity=order_qty,
                                            # product=broker.PRODUCT_CNC,
                                            # order_type=broker.ORDER_TYPE_LIMIT,
                                            # price=order_price,
                                            # validity=None,
                                            # disclosed_quantity=None,
                                            # trigger_price=None,
                                            # squareoff=None,
                                            # stoploss=None,
                                            # trailing_stoploss=None,
                                            # tag="TradingPython")
                
                # if order_id is not None:
                    # order_data = {
                        # 'InTrade': in_trade,
                        # 'OrderId': order_id,
                        # 'Shares': order_qty,
                        # 'Entry': order_price,
                    # }
                    
                    # # UPDATE SHEET
                    # f.update_values_by_row_key_in_worksheet(symbol, order_data, worksheet_name=wks_name)
            # except Exception as ex:
                # print('error with SELL order')
                # print(ex)
        
        # elif not in_trade and len(trades) < max_trades and symbol_token in buy_symbol_itokens:

            # order_price = asset['ohlc']['high']
            # stop_price = order_price * (1 - stop_value / 100)

            # # per_share_risk = order_price - stop_price
            # # shares = fixed_risk_amount // per_share_risk if per_share_risk > 0 else 0

            # shares = fixed_amount_per_trade // order_price
            
            # # print(f"BUY Logic - Risk->{fixed_risk_amount} - Per Share Risk->{per_share_risk} - Shares->{shares} - Trades->{len(trades)}")
            # print(f"BUY Logic - Risk->{fixed_amount_per_trade} - Shares->{shares} - Trades->{len(trades)}")

            # if shares > 0:
                # # capital -= shares * order_price
                # trades.append({
                    # "symbol_token": symbol_token, 
                    # "entry": order_price,
                    # "stop": stop_price,
                    # "shares": shares
                # })
            
                # order_qty = math.floor(shares)
                
                # in_trade = True
                # message += f"\n{symbol}({index})->BUY: {order_qty} | Price: {order_price}"

                # try:
                    # # order_id="abc123"
                    # order_id = broker.place_gtt(trigger_type=broker.GTT_TYPE_SINGLE, 
                        # tradingsymbol=symbol,
                        # exchange=broker.EXCHANGE_NSE,
                        # trigger_values=[order_price],
                        # last_price=asset['ltp'],
                        # orders=[
                            # {
                                # 'exchange': broker.EXCHANGE_NSE,
                                # 'transaction_type': broker.TRANSACTION_TYPE_BUY,
                                # 'quantity': order_qty,
                                # 'order_type': broker.ORDER_TYPE_LIMIT,
                                # 'product': broker.PRODUCT_CNC,
                                # 'price': order_price
                            # }
                        # ])
                    
                    # if order_id is not None:
                        # order_data = [
                            # symbol,
                            # symbol_token,
                            # index,
                            # index_token,
                            # in_trade,
                            # order_id,
                            # order_qty,
                            # order_price
                        # ]

                        # # UPDATE SHEET
                        # f.update_or_append_row(key_column="A", key_value=symbol, row_data=order_data, sheet_name=wks_name)
                # except Exception as ex:
                    # print('error with BUY order')
                    # print(ex)

    # # print(trades)

    # if message:
        # message = f"RPS Weekly EMA 89\n{message}"
        # print(message)
        # f.send_telegram_message(message)




