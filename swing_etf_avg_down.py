import time
import utils as f
import math

from datetime import datetime, date, timezone
from kite_trade import *

class SwingETFAvgDown:
    
    def __init__(self, *args, broker:KiteApp=None, **kwargs):
        self.broker = broker
        self.tick_received = False
        super().__init__(*args, **kwargs)
    
    [staticmethod]
    def is_avg_down_order(ltp, last_order, sip_data):

        if last_order is None:
            last_order = {}
            last_order['avg_down_price'] = 0

        avg_down_percent = float(sip_data['avg_down_percent']) / 100
        price = last_order['avg_down_price']
        avg_down_price = price * (1 - avg_down_percent)
        percent_away = 0 if avg_down_price == 0 else ((ltp / avg_down_price) - 1) * 100

        print('Price    : ' + f.bcolors.BOLD + f.bcolors.OKBLUE + str(ltp) + f.bcolors.ENDC)
        print('LOP      : ' + str(price))
        print('ADP      : ' + str(avg_down_price))
        print('% Away   : ' + f.bcolors.BOLD + f.bcolors.OKGREEN + str(round(percent_away, 1)) + '%' + f.bcolors.ENDC)
        
        return ltp <= avg_down_price
    
    def on_ws_ticks(self, ws, ticks):
        # print(ticks)
        for t in ticks:
            inst_token = t['instrument_token'] 
            if inst_token in self.instrument_token_dict.keys():
                self.instrument_token_dict[inst_token]['ltp'] = t['last_price']
                self.instrument_token_dict[inst_token]['buy'] = t['depth']['buy']
                self.instrument_token_dict[inst_token]['sell'] = t['depth']['sell']
        
        self.tick_received = True
        print(self.instrument_token_dict)
        
    def on_trading_iteration(self):
        # self.load_data()
        wks_name = "ETF"
        asset_dict = f.get_values_from_worksheet(worksheet_name=wks_name)
        self.instrument_token_dict = {eval(v['instrument_token']): {'ltp': -1, 'buy': [], 'sell': []} for v in asset_dict.values()}
        self.instrument_tokens = list(self.instrument_token_dict.keys())
        print(self.instrument_tokens)
        self.broker.start_stream(self.on_ws_ticks, self.instrument_tokens)

        count = 0
        while not self.tick_received:
            count += 1
            # print(f'Count: {count}')
            if count < 5: time.sleep(1)  
            else: break
        
        if self.tick_received:
            for key in asset_dict.keys():
                print('- - - - - - - - - - - - - - - - - - -')
                skip_job = asset_dict[key]['skip_job'].lower() in ['true', '1', 't', 'y', 'yes']
                if skip_job:
                    print(f'{f.bcolors.WARNING}Skipping run for {key} as skip_job is set..{f.bcolors.ENDC}')
                    continue

                asset_data = asset_dict[key]
                max_buys = int(asset_data['max_buys'])
                buy_count = int(asset_data['buy_count'])

                if buy_count == max_buys:
                    print(f'{f.bcolors.WARNING}Skipping run for {key} as max buy count reached..{f.bcolors.ENDC}')
                    continue

                exchange_symbol = asset_data['symbol']
                exchange = exchange_symbol[:3]
                symbol = exchange_symbol[4:]
                buy_amount = int(asset_data['buy_amount'])
                inst_token = eval(asset_data['instrument_token'])
                
                userId = self.broker.user_id
                print(f'{f.bcolors.HEADER}- - {userId} Checking {exchange_symbol} - -{f.bcolors.ENDC}')

                is_avg_down = False
                last_order = {
                    "id": asset_data['last_order_id'],
                    "qty": int(asset_data['last_order_qty']),
                    "avg_down_price": float(asset_data['last_avg_down_price'])
                }

                # print(last_order)
                ltp = self.instrument_token_dict[inst_token]['ltp']
                
                # if last_order is not None:
                is_avg_down = SwingETFAvgDown.is_avg_down_order(ltp, last_order, asset_data)

                if is_avg_down:
                    price = self.instrument_token_dict[inst_token]['buy'][0]['price']
                    price = ltp if price == 0 else price
                    qty = math.floor(buy_amount / price)

                    print(f'{f.bcolors.OKGREEN}Placing BUY order for {qty} quantity at {price} price..{f.bcolors.ENDC}')

                    order_id = self.broker.place_order(variety=self.broker.VARIETY_REGULAR,
                            exchange=self.broker.EXCHANGE_NSE,
                            tradingsymbol=symbol,
                            transaction_type=self.broker.TRANSACTION_TYPE_BUY,
                            quantity=qty,
                            product=self.broker.PRODUCT_CNC,
                            order_type=self.broker.ORDER_TYPE_LIMIT,
                            price=price,
                            validity=None,
                            disclosed_quantity=None,
                            trigger_price=None,
                            squareoff=None,
                            stoploss=None,
                            trailing_stoploss=None,
                            tag="TradingPython")

                    if order_id is not None:
                        order_status = None
                        order_status_count = 0
                        while not order_status == 'COMPLETE':
                            order_history = self.broker.order_history(order_id)
                            order_status = order_history[-1].get('status')
                            order_status_count += 1
                            # print(f'Count: {count}')
                            if order_status_count < 5: time.sleep(1)
                            else: break
                        
                        if order_status == 'COMPLETE':
                            order_price = order_history[-1].get('average_price')
                            price = order_price
                            qty = order_history[-1].get('filled_quantity')
                            avg_down_price = order_price if is_avg_down else 0
                            buy_count += 1
                            try:
                                order_data = {
                                    'buy_count': buy_count,
                                    'last_order_id': order_id,
                                    'last_order_qty': qty,
                                    'last_avg_down_price': avg_down_price
                                }
                                
                                f.update_values_by_row_key_in_worksheet(key, order_data, worksheet_name=wks_name)
                                f.notification(f'Bought {exchange_symbol}, Buy Price {str(order_price)} - Quantity {str(qty)}', config['NOTIFICATION_KEY'])
                            except Exception as ex:
                                print('error with save order')
                                print(ex)
        else:
            print(f'{f.bcolors.WARNING}Skipping run as no tick received.{f.bcolors.ENDC}')

        # time.sleep(15)
        self.broker.end_stream(self.instrument_tokens)

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
    try:
        broker = KiteApp(enctoken, user_id)
        broker.profile()['user_id']
    except Exception as ex:
        if 'NoneType' in str(ex):
            pwd = config["PASSWORD"]
            totp_key = config["TOTP_KEY"]
            totp = get_totp(totp_key)
            enctoken = get_enctoken(user_id, pwd, totp)
            broker = KiteApp(enctoken)
        else: print(f'login error: {str(ex)}')

    strategy = SwingETFAvgDown(broker=broker)
    # strategy._set_logger()
    strategy.on_trading_iteration()