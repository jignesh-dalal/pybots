import pandas as pd
import pandas_ta as ta
import utils as f
import math
import argparse

from kite_trade import *
from datetime import datetime, timedelta


# COMMAND LINE ARGS
parser = argparse.ArgumentParser()
parser.add_argument("--uid", help="enter user id", default="SJ0281")
parser.add_argument("--wks", help="enter worksheet name", default="RSIOversold")
args = vars(parser.parse_args())


# config = {
#     'USER_ID': 'SJ0281',
#     'PASSWORD': '',
#     'TOTP_KEY': '',
#     'ACCESS_TOKEN': 'EFmypalwkfU/igrlrUAwjfwjitY/e0xzR327GxVtI+pJTBb6hGEzvuNhdRdxYUOUzE6Re91lYbviTzUDf9Kr+4t5BmBFEyKQ14eytCx2LI7gacSugBBcNg==',
# }
user_id = args["uid"]
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


def on_ws_ticks(ws, ticks):
    global tick_received, symbol_token_dict
    # print(ticks)
    for t in ticks:
        inst_token = t['instrument_token'] 
        if inst_token in symbol_token_dict.keys():
            symbol_token_dict[inst_token]['ltp'] = t['last_price']
            symbol_token_dict[inst_token]['buy'] = t['depth']['buy']
            symbol_token_dict[inst_token]['sell'] = t['depth']['sell']
    
    tick_received = True

wks_name = args["wks"]
instruments = f.get_all_records_from_sheet(worksheet_name=wks_name)
symbol_token_dict = {v['symbol_token']: {'ltp': -1, 'buy': [], 'sell': []} for v in instruments}
symbol_tokens = list(symbol_token_dict.keys())

# Create a custom time grouper for 3-hour periods starting at 9:15 AM
# Define the 3-hour bins: 9:15 AM–12:15 PM, 12:15 PM–3:15 PM
def custom_3hr_grouper(timestamp):
    hour = timestamp.hour
    minute = timestamp.minute
    if hour < 12 or (hour == 12 and minute < 15):
        return timestamp.floor('D') + pd.Timedelta(hours=9, minutes=15)
    elif hour < 15 or (hour == 14 and minute <= 15):
        return timestamp.floor('D') + pd.Timedelta(hours=12, minutes=15)
    else:
        return timestamp.floor('D') + pd.Timedelta(hours=15, minutes=15)


tick_received = False
broker.start_stream(on_ws_ticks, symbol_tokens)

count = 0
while not tick_received:
    count += 1
    # print(f'Count: {count}')
    if count < 5: time.sleep(1)  
    else: break    

if tick_received:

    to_date = datetime.now()
    from_date = to_date - timedelta(days=24)
    conversion = {   'iOpen'  : 'first', 'iHigh'  : 'max', 'iLow'   : 'min', 'iClose' : 'last', 'iVolume': 'sum', 'Open'  : 'first', 'High'  : 'max', 'Low'   : 'min', 'Close' : 'last', 'Volume': 'sum' }

    # # For Testing
    # instruments = [{'symbol': 'NSE:GOLDBEES',
    # 'symbol_token': 3693569,
    # 'index_symbol': 'NSE:GOLDBEES',
    # 'index_symbol_token': 3693569,
    # 'buy_amount': '10000',
    # 'target_per': '',
    # 'buy_count': '0',
    # 'last_order_id': '',
    # 'last_order_qty': '',
    # 'last_order_price': '',
    # 'gtt_id': '',
    # 'skip_job': ''}]

    for asset in instruments:

        index = asset['index_symbol']
        index_token = asset['index_symbol_token']
        symbol = asset['symbol']
        symbol_token = asset['symbol_token']
        buy_amount = int(asset['buy_amount'])
        buy_count = int(asset['buy_count'])
        gtt_id = asset['gtt_id']

        index_data = broker.historical_data(index_token, from_date, to_date, '60minute')
        df_index = pd.DataFrame(index_data)
        df_index['Date'] = pd.to_datetime(df_index['Date'])
        df_index = df_index.set_index('Date')

        # Rename columns for clarity if necessary
        df_index.rename(columns={
            'Open': 'iOpen', 'High': 'iHigh', 'Low': 'iLow', 'Close': 'iClose', 'Volume': 'iVolume'
        }, inplace=True)

        # df_index

        try:
            symbol_data = broker.historical_data(symbol_token, from_date, to_date, '60minute')
        except Exception as ex:
            print(f"Symbol->{symbol_token}")
            print(f'Error: {str(ex)}')
        df_symbol = pd.DataFrame(symbol_data)
        df_symbol['Date'] = pd.to_datetime(df_symbol['Date'])
        df_symbol = df_symbol.set_index('Date')

        #df_symbol

        df = pd.concat([df_index,df_symbol], axis=1)

        #df['hRSI'] = ta.rsi(df['iClose'], length=13)
        # df['hfRSI'] = calculate_rsi(df['iClose'], periods=13)

        # Apply the custom grouper
        df['TimeGroup'] = df.index.map(custom_3hr_grouper)

        # Resample to 3-hourly OHLC
        ohlc_dict = {
            'iOpen': 'first',
            'iHigh': 'max',
            'iLow': 'min',
            'iClose': 'last',
            'iVolume': 'sum',  # Include if Volume is present
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last',
            'Volume': 'sum',  # Include if Volume is present
            #'hRSI': 'mean'
        }
        df_3hr = df.groupby('TimeGroup').agg(ohlc_dict).ffill()

        # Drop the temporary TimeGroup column if it exists in the output
        df_3hr.index.name = None  # Reset index name for clarity

        # # Filter for valid 3-hour period start times using boolean indexing
        # valid_starts = [pd.to_datetime('09:15:00').time(), pd.to_datetime('12:15:00').time()]
        # df_3hr = df_3hr[[t in valid_starts for t in df_3hr.index.time]]

        # Add RSI column to df_3hr
        df_3hr['RSI'] = ta.rsi(df_3hr['iClose'], length=13)

        signal = 0
        
        rsi = df_3hr['RSI'].iloc[-1]

        message = f"{symbol}\nRSI: {rsi:.2f} | Signal: {signal}"
        print(f"Symbol: {symbol} | RSI: {rsi:.2f} | Signal: {signal}")

        if rsi >= 28:
            buy_count = 0 if buy_count > 2 else buy_count

            # UPDATE SHEET
            f.update_values_by_row_key_in_worksheet(symbol, {'buy_count': buy_count}, worksheet_name=wks_name)
            continue
        
        if rsi >= 24:
            target = 1
        elif rsi >= 20:
            target = 2
        elif rsi >= 16:
            target = 3
        else:
            target = 4

        # BUY SIGNALS
        if target > buy_count:
            signal = 1
            buy_count = target
    
        ltp = symbol_token_dict[symbol_token]['ltp']

        # BUY
        if signal == 1:
            try:
                factor = ((buy_count / 2) + 0.5) if buy_count > 1 else buy_count
                amount = buy_amount * factor
                o_price = symbol_token_dict[symbol_token]['buy'][0]['price']
                o_price = ltp if o_price == 0 else o_price
                target_price = o_price * 1.02
                order_qty = math.floor(amount / o_price)

                print(f'{f.bcolors.OKGREEN}{symbol} - Placing BUY order for {order_qty} quantity at {o_price} price amounting to {amount} with Target price of {target_price}{f.bcolors.ENDC}')
                message += f"\nBUY: {order_qty} | Price: {o_price}"


                order_id = broker.place_order(variety=broker.VARIETY_REGULAR,
                        exchange=broker.EXCHANGE_NSE,
                        tradingsymbol=symbol,
                        transaction_type=broker.TRANSACTION_TYPE_BUY,
                        quantity=order_qty,
                        product=broker.PRODUCT_CNC,
                        order_type=broker.ORDER_TYPE_LIMIT,
                        price=o_price,
                        validity=None,
                        disclosed_quantity=None,
                        trigger_price=None,
                        squareoff=None,
                        stoploss=None,
                        trailing_stoploss=None,
                        tag="TradingPython")
                
                if order_id: 
                    if not gtt_id:
                        # PLACE GTT ORDER FOR TARGET
                        gtt_id = broker.place_gtt(trigger_type=broker.GTT_TYPE_SINGLE, 
                            tradingsymbol=symbol,
                            exchange=broker.EXCHANGE_NSE,
                            trigger_values=[target_price],
                            last_price=o_price,
                            orders=[
                                {
                                    'exchange': broker.EXCHANGE_NSE,
                                    'transaction_type': broker.TRANSACTION_TYPE_SELL,
                                    'quantity': order_qty,
                                    'order_type': broker.ORDER_TYPE_LIMIT,
                                    'product': broker.PRODUCT_CNC,
                                    'price': target_price
                                }
                            ])
                        
                    order_data = {
                        'buy_count': buy_count,
                        'last_order_id': order_id,
                        'last_order_qty': order_qty,
                        'last_order_price': o_price,
                        'gtt_id': gtt_id
                    }
                    
                    # UPDATE SHEET
                    f.update_values_by_row_key_in_worksheet(symbol, order_data, worksheet_name=wks_name)
                    f.send_telegram_message(message)

            except Exception as ex:
                print('error with save order')
                print(ex)

broker.end_stream(symbol_tokens)
