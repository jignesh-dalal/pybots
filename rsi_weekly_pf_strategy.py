import pandas as pd
import pandas_ta as ta
import utils as f
import argparse

from kite_trade import *
from datetime import datetime, timedelta

# COMMAND LINE ARGS
parser = argparse.ArgumentParser()
parser.add_argument("--uid", help="enter user id", default="SJ0281")
parser.add_argument("--wks", help="enter worksheet name", default="RSIOversoldWeekly")
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
    # print(ticks)
    for t in ticks:
        inst_token = t['instrument_token'] 
        if inst_token in symbol_token_dict.keys():
            symbol_token_dict[inst_token]['ltp'] = t['last_price']
            symbol_token_dict[inst_token]['buy'] = t['depth']['buy']
            symbol_token_dict[inst_token]['sell'] = t['depth']['sell']
    
    tick_received = True

wks_name = args.wks
assets = f.get_all_records_from_sheet(worksheet_name=wks_name)
symbol_token_dict = {v['symbol_token']: {'ltp': -1, 'buy': [], 'sell': [], 'qty': v['qty'], 'avg_price': v['avg_price']} for v in assets}
symbol_tokens = list(symbol_token_dict.keys())

# print(assets)
# print(symbol_token_dict)

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
    from_date = to_date - timedelta(days=700)
    logic = {   'iOpen'  : 'first',
                'iHigh'  : 'max',
                'iLow'   : 'min',
                'iClose' : 'last',
                'iVolume': 'sum',
                'Open'  : 'first',
                'High'  : 'max',
                'Low'   : 'min',
                'Close' : 'last',
                'Volume': 'sum' }
    
    portfolio_value = sum([v['qty']*v['ltp'] for k,v in symbol_token_dict.items()])
    margins = broker.margins() 
    cash_balance = margins.get('equity', {}).get('available', {}).get('cash', 0)

    print(f"Portfolio value: {portfolio_value}, Cash balance: {cash_balance}")

    # asset = assets[0]

    cash_asset = next(x for x in assets if x['index_symbol_token'] == '')
    cash_symbol = cash_asset['symbol']
    cash_symbol_token = cash_asset['symbol_token']
    cash_symbol_ltp = symbol_token_dict[cash_symbol_token]['ltp']
    cash_symbol_qty = symbol_token_dict[cash_symbol_token]['qty']
    cash_symbol_balance = cash_symbol_qty * cash_symbol_ltp

    for asset in assets:

        index = asset['index_symbol']
        index_token = asset['index_symbol_token']
        symbol = asset['symbol']
        symbol_token = asset['symbol_token']

        if index == '' or index_token == '': continue

        index_data = broker.historical_data(index_token, from_date, to_date, 'day')
        df_index = pd.DataFrame(index_data)
        df_index['Date'] = pd.to_datetime(df_index['Date'])
        df_index = df_index.set_index('Date')

        # Rename columns for clarity if necessary
        df_index.rename(columns={
            'Open': 'iOpen', 'High': 'iHigh', 'Low': 'iLow', 'Close': 'iClose', 'Volume': 'iVolume'
        }, inplace=True)

        # print(df_index)

        symbol_data = broker.historical_data(symbol_token, from_date, to_date, 'day')
        df_symbol = pd.DataFrame(symbol_data)
        df_symbol['Date'] = pd.to_datetime(df_symbol['Date'])
        df_symbol = df_symbol.set_index('Date')

        # print(df_symbol)

        df = pd.concat([df_index,df_symbol], axis=1)
        df = df.resample('W').apply(logic)
        # set the index to the beginning of the week
        df.index = df.index - pd.tseries.frequencies.to_offset("6D")

        df.ta.rsi(append=True, length=13)

        # print(df.tail(22))

        signal = 0
        # #max_buys = int(asset['max_buys'])
        buy_count = int(asset['buy_count'])
        sell_count = int(asset['sell_count'])
        min_weight = asset['min_pc']
        max_weight = asset['max_pc']
        buy_pc_diff = asset['buy_pc_diff']
        sell_pc_diff = asset['sell_pc_diff']

        df_latest_rsi = df['RSI_13'].iloc[-1]
        # # SIMULATION
        # df_latest_rsi = 84
        
        # BUY SIGNALS
        if df_latest_rsi > 45 and df_latest_rsi < 50 and buy_count == 4:
            signal = 1
        if df_latest_rsi > 40 and df_latest_rsi < 45 and buy_count == 3:
            signal = 1
        if df_latest_rsi > 35 and df_latest_rsi < 40 and buy_count == 2:
            signal = 1
        if df_latest_rsi < 30 and buy_count == 1:
            signal = 1


        # SELL SIGNALS
        if df_latest_rsi > 70 and df_latest_rsi < 75 and sell_count == 3:
            signal = -1
        if df_latest_rsi > 75 and df_latest_rsi < 80 and sell_count == 2:
            signal = -1
        if df_latest_rsi > 80 and sell_count == 1:
            signal = -1

        message = f"Symbol: {symbol} | RSI: {df_latest_rsi:.2f} | Signal: {signal}"
        print(message)

        ltp = symbol_token_dict[symbol_token]['ltp']
        quantity = symbol_token_dict[symbol_token]['qty']
        cur_weight = (quantity * ltp) / portfolio_value
        
        weight = 0
        if signal == 1:
            weight_diff = max_weight - cur_weight
            adj_weight = abs(weight_diff) / buy_count 
            weight = cur_weight + adj_weight if weight_diff > 0 else cur_weight - adj_weight
            buy_count -= 1
        
        elif signal == -1:
            weight_diff = min_weight - cur_weight
            adj_weight = abs(weight_diff) / sell_count 
            weight = cur_weight + adj_weight if weight_diff > 0 else cur_weight - adj_weight
            sell_count -= 1
        
        else:
            weight = cur_weight
        
        # Calculate how many shares we need to buy or sell
        shares_value = portfolio_value * weight
        print(f"The current portfolio value is {portfolio_value} and the weight needed is {weight:.2f} compared to current weight {cur_weight:.2f}, so we should buy {shares_value}")

        new_quantity = shares_value // ltp
        quantity_difference = new_quantity - quantity
        quantity_pct_difference = abs(quantity_difference / quantity)

        print(f"Currently own {quantity} shares of {symbol} at {ltp} but need {new_quantity}, so the difference is {quantity_difference} and percent difference is {quantity_pct_difference:.2f}")
        message += f"\nQty. Expected: {new_quantity} | Actual: {quantity} | % Diff: {quantity_pct_difference:.2f}" 
        try:
            order_id = ''
            # If quantity is positive then buy, if it's negative then sell
            if quantity_difference > 0 and quantity_pct_difference > buy_pc_diff:
                
                if cash_balance < shares_value and cash_symbol_balance >= shares_value:
                    cash_shares_value = shares_value - cash_balance
                    cash_order_price = symbol_token_dict[cash_symbol_token]['sell'][0]['price']
                    cash_order_price = cash_symbol_ltp if cash_order_price == 0 else cash_order_price
                    cash_new_quantity = cash_shares_value // cash_order_price
                    cash_quantity_difference = cash_new_quantity - cash_symbol_qty
                    cash_order_qty = abs(cash_quantity_difference)

                    print(f"Currently own {quantity} shares of {cash_symbol} at {cash_symbol_ltp} but need {cash_new_quantity}, so the difference is {cash_quantity_difference}")

                    # broker.place_order(variety=broker.VARIETY_REGULAR,
                    #                             exchange=broker.EXCHANGE_NSE,
                    #                             tradingsymbol=cash_symbol,
                    #                             transaction_type=broker.TRANSACTION_TYPE_SELL,
                    #                             quantity=cash_order_qty,
                    #                             product=broker.PRODUCT_CNC,
                    #                             order_type=broker.ORDER_TYPE_LIMIT,
                    #                             price=cash_order_price,
                    #                             validity=None,
                    #                             disclosed_quantity=None,
                    #                             trigger_price=None,
                    #                             squareoff=None,
                    #                             stoploss=None,
                    #                             trailing_stoploss=None,
                    #                             tag="TradingPython")
                    
                    # UPDATE SHEET
                    f.update_values_by_row_key_in_worksheet(cash_symbol, {'qty': cash_new_quantity}, worksheet_name=wks_name)
                
                order_qty = abs(quantity_difference) 
                order_price = symbol_token_dict[symbol_token]['buy'][0]['price']
                order_price = ltp if order_price == 0 else order_price

                print(f"Placing BUY order for {symbol} with {order_qty} quantity at {order_price} price")
                message += f"\nBUY Qty.: {order_qty} | Price: {order_price}"

                # order_id = broker.place_order(variety=broker.VARIETY_REGULAR,
                #                     exchange=broker.EXCHANGE_NSE,
                #                     tradingsymbol=symbol,
                #                     transaction_type=broker.TRANSACTION_TYPE_BUY,
                #                     quantity=order_qty,
                #                     product=broker.PRODUCT_CNC,
                #                     order_type=broker.ORDER_TYPE_LIMIT,
                #                     price=order_price,
                #                     validity=None,
                #                     disclosed_quantity=None,
                #                     trigger_price=None,
                #                     squareoff=None,
                #                     stoploss=None,
                #                     trailing_stoploss=None,
                #                     tag="TradingPython")

            elif quantity_difference < 0 and quantity_pct_difference > sell_pc_diff:

                order_qty = abs(quantity_difference) 
                order_price = symbol_token_dict[symbol_token]['sell'][0]['price']
                order_price = ltp if order_price == 0 else order_price

                print(f"Placing SELL order for {symbol} with {order_qty} quantity at {order_price} price")
                message += f"\nSELL Qty.: {order_qty} | Price: {order_price}"

                # order_id = broker.place_order(variety=broker.VARIETY_REGULAR,
                #                     exchange=broker.EXCHANGE_NSE,
                #                     tradingsymbol=symbol,
                #                     transaction_type=broker.TRANSACTION_TYPE_SELL,
                #                     quantity=order_qty,
                #                     product=broker.PRODUCT_CNC,
                #                     order_type=broker.ORDER_TYPE_LIMIT,
                #                     price=order_price,
                #                     validity=None,
                #                     disclosed_quantity=None,
                #                     trigger_price=None,
                #                     squareoff=None,
                #                     stoploss=None,
                #                     trailing_stoploss=None,
                #                     tag="TradingPython")

            print(f"TELEMSG: {message}")
            f.send_telegram_message(message)
            if order_id:
                order_data = {
                    'qty': new_quantity,
                    'buy_count': buy_count,
                    'sell_count': sell_count,
                }
        
                # UPDATE SHEET
                f.update_values_by_row_key_in_worksheet(symbol, order_data, worksheet_name=wks_name)
        
        except Exception as ex:
            print('error with save order')
            print(ex)
    
broker.end_stream(symbol_tokens)
