import pandas as pd
import pandas_ta as ta
import utils as f
import math

from kite_trade import *
from datetime import datetime, timedelta


class SwingRSIOversoldStrategy:
    def __init__(self, *args, broker:KiteApp=None, **kwargs):
        self.broker = broker
        self.tick_received = False
        super().__init__(*args, **kwargs)

    def on_ws_ticks(self, ws, ticks):
        # print(ticks)
        for t in ticks:
            inst_token = t['instrument_token'] 
            if inst_token in self.symbol_token_dict.keys():
                self.symbol_token_dict[inst_token]['ltp'] = t['last_price']
                self.symbol_token_dict[inst_token]['buy'] = t['depth']['buy']
                self.symbol_token_dict[inst_token]['sell'] = t['depth']['sell']
        
        self.tick_received = True


    def on_trading_iteration(self):
        wks_name = "RSIOversold"
        instruments = f.get_all_records_from_sheet(worksheet_name=wks_name)
        self.symbol_token_dict = {v['symbol_token']: {'ltp': -1, 'buy': [], 'sell': []} for v in instruments}
        self.symbol_tokens = list(self.symbol_token_dict.keys())
        self.broker.start_stream(self.on_ws_ticks, self.symbol_tokens)

        count = 0
        while not self.tick_received:
            count += 1
            # print(f'Count: {count}')
            if count < 5: time.sleep(1)  
            else: break    

        if self.tick_received:
            to_date = datetime.now()
            from_date = to_date - timedelta(days=180)

            for asset in instruments:
                index_symbol = asset['index_symbol']
                print('- - - - - - - - - - - - - - - - - - -')
                skip_job = asset['skip_job'] == 1
                if skip_job:
                    print(f'{f.bcolors.WARNING}Skipping run for {index_symbol} as skip_job is set..{f.bcolors.ENDC}')
                    continue

                index_symbol_token = asset['index_symbol_token']
                symbol = asset['symbol']
                symbol_token = asset['symbol_token']
                buy_amount = int(asset['buy_amount'])
                buy_count = int(asset['buy_count'])

                userId = self.broker.user_id
                print(f'{f.bcolors.HEADER}- - {userId} Checking {index_symbol} - -{f.bcolors.ENDC}')
                
                data = self.broker.historical_data(index_symbol_token, from_date, to_date, 'day')

                df = pd.DataFrame(data)
                df.ta.rsi(append=True, length=13)

                #print(df)

                signal = 0
                #max_buys = int(asset['max_buys'])
                buy_count = int(asset['buy_count'])
                df_last = df.tail(1)
                df_latest_rsi = df_last['RSI_13'].iloc[-1]

                print(f'{f.bcolors.OKBLUE}RSI: {df_latest_rsi}{f.bcolors.ENDC}')

                # BUY SIGNALS
                if df_latest_rsi > 40 and df_latest_rsi < 45 and buy_count < 1:
                    signal = 1
                if df_latest_rsi > 35 and df_latest_rsi < 40 and buy_count < 2:
                    signal = 1
                if df_latest_rsi > 30 and df_latest_rsi < 35 and buy_count < 4:
                    signal = 1
                if df_latest_rsi < 30 and buy_count < 5:
                    signal = 1

                ltp = self.symbol_token_dict[symbol_token]['ltp']

                # BUY
                if signal == 1:
                    buy_count += 1
                    factor = ((buy_count / 2) + 0.5) if buy_count > 1 else buy_count
                    amount = buy_amount * factor
                    o_price = self.symbol_token_dict[symbol_token]['buy'][0]['price']
                    o_price = ltp if o_price == 0 else o_price
                    target_price = o_price * 1.055
                    order_qty = math.floor(amount / o_price)

                    print(f'{f.bcolors.OKGREEN}{symbol} - Placing BUY order for {order_qty} quantity at {o_price} price amounting to {amount} with Target price of {target_price}{f.bcolors.ENDC}')

                    order_id = self.broker.place_order(variety=self.broker.VARIETY_REGULAR,
                            exchange=self.broker.EXCHANGE_NSE,
                            tradingsymbol=symbol,
                            transaction_type=self.broker.TRANSACTION_TYPE_BUY,
                            quantity=order_qty,
                            product=self.broker.PRODUCT_CNC,
                            order_type=self.broker.ORDER_TYPE_LIMIT,
                            price=o_price,
                            validity=None,
                            disclosed_quantity=None,
                            trigger_price=None,
                            squareoff=None,
                            stoploss=None,
                            trailing_stoploss=None,
                            tag="TradingPython")
                    
                    if order_id is not None:
                        try:
                            # PLACE GTT ORDER FOR TARGET
                            gtt_order_id = self.broker.place_gtt(trigger_type=self.broker.GTT_TYPE_SINGLE, 
                                tradingsymbol=symbol[4:],
                                exchange=self.broker.EXCHANGE_NSE,
                                trigger_values=[target_price],
                                last_price=o_price,
                                orders=[
                                    {
                                        'exchange': self.broker.EXCHANGE_NSE,
                                        'transaction_type': self.broker.TRANSACTION_TYPE_SELL,
                                        'quantity': order_qty,
                                        'order_type': self.broker.ORDER_TYPE_LIMIT,
                                        'product': self.broker.PRODUCT_CNC,
                                        'price': target_price
                                    }
                                ])
                            
                            order_data = {
                                'buy_count': buy_count,
                                'last_order_id': order_id,
                                'last_order_qty': order_qty,
                                'last_order_price': o_price,
                                'gtt_id': gtt_order_id
                            }
                            
                            # UPDATE SHEET
                            f.update_values_by_row_key_in_worksheet(symbol, order_data, worksheet_name=wks_name)

                        except Exception as ex:
                            print('error with save order')
                            print(ex)
        else:
            print(f'{f.bcolors.WARNING}Skipping run as no tick received.{f.bcolors.ENDC}')

        # time.sleep(15)
        self.broker.end_stream(self.symbol_tokens)


if __name__ == "__main__":
    # config = {
    #     'USER_ID': 'SJ0281',
    #     'PASSWORD': '',
    #     'TOTP_KEY': '',
    #     'ACCESS_TOKEN': 'EFmypalwkfU/igrlrUAwjfwjitY/e0xzR327GxVtI+pJTBb6hGEzvuNhdRdxYUOUzE6Re91lYbviTzUDf9Kr+4t5BmBFEyKQ14eytCx2LI7gacSugBBcNg==',
    # }
    user_id = 'SJ0281'
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

    if broker is not None:
        strategy = SwingRSIOversoldStrategy(broker=broker)
        strategy.on_trading_iteration()
