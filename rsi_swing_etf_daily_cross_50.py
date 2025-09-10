# %%
import pandas as pd
import utils as f
import argparse
import sys

from kite_trade import *
from datetime import datetime, timedelta

# COMMAND LINE ARGS
parser = argparse.ArgumentParser()
parser.add_argument("--uid", help="enter user id", default="SJ0281")
parser.add_argument("--wks", help="enter worksheet name", default="CI_ETF_Indices")
args = parser.parse_args()

# config = {
#     'USER_ID': 'SJ0281',
#     'PASSWORD': '',
#     'TOTP_KEY': '',
#     'ACCESS_TOKEN': 'EFmypalwkfU/igrlrUAwjfwjitY/e0xzR327GxVtI+pJTBb6hGEzvuNhdRdxYUOUzE6Re91lYbviTzUDf9Kr+4t5BmBFEyKQ14eytCx2LI7gacSugBBcNg==',
# }
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

# %%
ci_url = 'https://chartink.com/screener/all-indices-57'
ci_buy_data = {
    'scan_clause': '( {45603} ( latest rsi( 13 ) >= 50 and 1 day ago  rsi( 13 ) <= 50 ) )'
}
ci_sell_data = {
    'scan_clause': '( {45603} ( latest rsi( 13 ) < 50 and 1 day ago  rsi( 13 ) >= 50 ) )'
}

df_buy = f.get_chartink_data(ci_url, ci_buy_data)
df_sell = f.get_chartink_data(ci_url, ci_sell_data)

# %%
if df_buy.empty and df_sell.empty:
    print("No trades available")
    sys.exit(0)

wks_name = args.wks

instruments = f.get_all_records_from_sheet(worksheet_name=wks_name)
instruments = [x for x in instruments if x['AllowTrade'] == 1 and x['SymbolIToken'] != '']

buy_index_codes = df_buy['nsecode'].tolist() if 'nsecode' in df_buy.columns else []
sell_index_codes = df_sell['nsecode'].tolist() if 'nsecode' in df_sell.columns else []

index_codes = list(set(buy_index_codes + sell_index_codes))
symbol_token_dict = {v['SymbolIToken']: {'symbol':v['Symbol'], 'index_token': v['nsecode'], 'ltp': -1, 'buy': [], 'sell': [], 'in_position': v['InTrade'], 'buy_amount': v['BuyAmount']} for v in instruments if v['nsecode'] in index_codes}
symbol_tokens = list(symbol_token_dict.keys()) #[record['symbol_token'] for record in symbol_token_dict.values()] 

tick_received = False
broker.start_stream(on_ws_ticks, symbol_tokens)

count = 0
while not tick_received:
    count += 1
    # print(f'Count: {count}')
    if count < 5: time.sleep(1)  
    else: break    

broker.end_stream(symbol_tokens)

if not tick_received:
    print("No trades available")
    sys.exit(0)


#symbol_token_dict

# %%
STOP_LOSS_POINTS = 10
positions = []

message = ''

for scode in sell_index_codes:
    asset = next(r for r in symbol_token_dict.values() if r['index_token'] == scode)
    in_position = bool(asset['in_position'])
    
    if in_position:
        symbol = asset['symbol']
        order_price = asset['ltp']
        order_qty = asset['OrderQty']

        in_position = False
        message += f"{symbol}\nSELL: {order_qty} | Price: {order_price}"

        try:

            order_id = broker.place_order(variety=broker.VARIETY_REGULAR,
                                        exchange=broker.EXCHANGE_NSE,
                                        tradingsymbol=symbol,
                                        transaction_type=broker.TRANSACTION_TYPE_SELL,
                                        quantity=order_qty,
                                        product=broker.PRODUCT_CNC,
                                        order_type=broker.ORDER_TYPE_LIMIT,
                                        price=order_price,
                                        validity=None,
                                        disclosed_quantity=None,
                                        trigger_price=None,
                                        squareoff=None,
                                        stoploss=None,
                                        trailing_stoploss=None,
                                        tag="TradingPython")
            
            if order_id is not None:
                order_data = {
                    'InTrade': in_position,
                    'OrderId': order_id,
                    'OrderQty': order_qty,
                    'OrderPrice': order_price,
                    'SLOrderId': ''
                }
                
                # UPDATE SHEET
                f.update_values_by_row_key_in_worksheet(symbol, order_data, worksheet_name=wks_name)

        except Exception as ex:
            print('error with save order')
            print(ex)

if message:
    message = f"ETF SELL Daily RSI13 x 50\n{message}"
    f.send_telegram_message(message)

# %%

message = ''

for bcode in buy_index_codes:
    asset = next(r for r in symbol_token_dict.values() if r['index_token'] == bcode)
    in_position = bool(asset['in_position'])

    if not in_position:
        symbol = asset['symbol']
        order_price = asset['ltp']
        order_qty = abs(asset['buy_amount'] / order_price)
        stop_loss_price = asset['ohlc']['low'] - STOP_LOSS_POINTS
        
        in_position = True
        message += f"{symbol}\nBUY: {order_qty} | Price: {order_price}"

        try:

            order_id = broker.place_order(variety=broker.VARIETY_REGULAR,
                                exchange=broker.EXCHANGE_NSE,
                                tradingsymbol=symbol,
                                transaction_type=broker.TRANSACTION_TYPE_BUY,
                                quantity=order_qty,
                                product=broker.PRODUCT_CNC,
                                order_type=broker.ORDER_TYPE_LIMIT,
                                price=order_price,
                                validity=None,
                                disclosed_quantity=None,
                                trigger_price=None,
                                squareoff=None,
                                stoploss=None,
                                trailing_stoploss=None,
                                tag="TradingPython")
            
            if order_id is not None:
                # PLACE GTT ORDER FOR STOP LOSS
                gtt_order_id = broker.place_gtt(trigger_type=broker.GTT_TYPE_SINGLE, 
                    tradingsymbol=symbol,
                    exchange=broker.EXCHANGE_NSE,
                    trigger_values=[stop_loss_price+1],
                    last_price=order_price,
                    orders=[
                        {
                            'exchange': broker.EXCHANGE_NSE,
                            'transaction_type': broker.TRANSACTION_TYPE_SELL,
                            'quantity': order_qty,
                            'order_type': broker.ORDER_TYPE_LIMIT,
                            'product': broker.PRODUCT_CNC,
                            'price': stop_loss_price
                        }
                    ])
                
                order_data = {
                    'InTrade': in_position,
                    'OrderId': order_id,
                    'OrderQty': order_qty,
                    'OrderPrice': order_price,
                    'SLOrderId': gtt_order_id
                }

                # UPDATE SHEET
                f.update_values_by_row_key_in_worksheet(symbol, order_data, worksheet_name=wks_name)

        except Exception as ex:
            print('error with save order')
            print(ex)

if message:
    message = f"ETF BUY Daily RSI13 x 50\n{message}"
    f.send_telegram_message(message)
