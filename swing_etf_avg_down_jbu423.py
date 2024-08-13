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

        avg_down_percent = float(sip_data['avg_down_per']) / 100
        price = last_order['avg_down_price']
        avg_down_price = price * (1 - avg_down_percent)
        percent_away = 0 if avg_down_price == 0 else ((ltp / avg_down_price) - 1) * 100

        print('Price    : ' + f.bcolors.BOLD + f.bcolors.OKBLUE + str(ltp) + f.bcolors.ENDC)
        print('LOP      : ' + str(price))
        print('ADP      : ' + str(avg_down_price))
        print('% Away   : ' + f.bcolors.BOLD + f.bcolors.OKGREEN + str(round(percent_away, 1)) + '%' + f.bcolors.ENDC)
        
        return ltp <= avg_down_price
    
    def create_or_update_gtt(self, trigger_type, tradingsymbol, exchange, trigger_values, last_price, orders, gtt_order_id=None):
        if gtt_order_id is None:
            return self.broker.place_gtt(
                trigger_type, 
                tradingsymbol,
                exchange,
                trigger_values,
                last_price,
                orders
            )
        
        gtt_order = self.broker.gtt_order(gtt_order_id)
        if gtt_order:
            return self.broker.modify_gtt(
                gtt_order_id,
                trigger_type,
                tradingsymbol,
                exchange,
                trigger_values,
                last_price,
                orders
            )
    
    def on_ws_ticks(self, ws, ticks):
        # print(ticks)
        for t in ticks:
            inst_token = t['instrument_token'] 
            if inst_token in self.instrument_token_dict.keys():
                self.instrument_token_dict[inst_token]['ltp'] = t['last_price']
                self.instrument_token_dict[inst_token]['buy'] = t['depth']['buy']
                self.instrument_token_dict[inst_token]['sell'] = t['depth']['sell']
        
        self.tick_received = True
        
    def on_trading_iteration(self):
        # self.load_data()
        wks_name = "ETF_JBU423"
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
            print(self.instrument_token_dict)

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
                    "avg_down_price": float(asset_data['last_order_price'])
                }

                # print(last_order)
                ltp = self.instrument_token_dict[inst_token]['ltp']
                
                # if last_order is not None:
                is_avg_down = SwingETFAvgDown.is_avg_down_order(ltp, last_order, asset_data)

                if is_avg_down:
                    buy_count += 1
                    amount = buy_amount * buy_count
                    o_price = self.instrument_token_dict[inst_token]['buy'][0]['price']
                    o_price = ltp if o_price == 0 else o_price
                    order_qty = math.floor(amount / o_price)

                    print(f'{f.bcolors.OKGREEN}Placing BUY order for {order_qty} quantity at {o_price} price amounting to {amount}{f.bcolors.ENDC}')

                    order_id = self.broker.place_order(variety=self.broker.VARIETY_REGULAR,
                            exchange=self.broker.EXCHANGE_NSE,
                            tradingsymbol=symbol,
                            transaction_type=self.broker.TRANSACTION_TYPE_BUY,
                            quantity=qty,
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

                    # order_id = '-1'
                    order_h = [{
                        'status': 'COMPLETE',
                        'average_price': o_price,
                        'filled_quantity': order_qty
                    }]

                    if order_id is not None:
                        order_status = None
                        order_status_count = 0
                        while not order_status == 'COMPLETE':
                            order_history = order_h if order_id == '-1' else self.broker.order_history(order_id)
                            order_status = order_history[-1].get('status')
                            order_status_count += 1
                            # print(f'Count: {count}')
                            if order_status_count < 30: time.sleep(1)
                            else: break
                        
                        if order_status == 'COMPLETE':
                            order_price = order_history[-1].get('average_price')
                            order_qty = order_history[-1].get('filled_quantity')
                            order_cost = round(order_qty * order_price, 2)
                            try:
                                qty = int(asset_data['qty']) + order_qty
                                cost = float(asset_data['cost']) + order_cost
                                price = cost / qty
                                target_per = float(asset_data['target_per']) / 100
                                target_price = round(price * (1 + target_per), 2)
                                avg_down_per = float(asset_data['avg_down_per']) / 100
                                avg_down_price = price * (1 - avg_down_per)

                                gtt_order_id = asset_data['gtt_id'] if asset_data['gtt_id'] else None

                                gtt_order_id = self.create_or_update_gtt(
                                    trigger_type=self.broker.GTT_TYPE_SINGLE,
                                    tradingsymbol=symbol,
                                    exchange=self.broker.EXCHANGE_NSE,
                                    trigger_values=[target_price],
                                    last_price=order_price,
                                    orders=[{
                                        'exchange': self.broker.EXCHANGE_NSE,
                                        'transaction_type': self.broker.TRANSACTION_TYPE_SELL,
                                        'quantity': qty,
                                        'order_type': self.broker.ORDER_TYPE_LIMIT,
                                        'product': self.broker.PRODUCT_CNC,
                                        'price': target_price
                                    }],
                                    gtt_order_id=gtt_order_id
                                )

                                order_data = {
                                    'buy_count': buy_count,
                                    'qty': qty,
                                    'price': price,
                                    'cost': cost,
                                    'avg_down_price': avg_down_price,
                                    'target_price': target_price,
                                    'last_order_id': order_id,
                                    'last_order_qty': order_qty,
                                    'last_order_price': order_price,
                                    'gtt_id': gtt_order_id
                                }
                                
                                f.update_values_by_row_key_in_worksheet(key, order_data, worksheet_name=wks_name)
                                # f.notification(f'Bought {exchange_symbol}, Buy Price {str(order_price)} - Quantity {str(order_qty)}', config['NOTIFICATION_KEY'])
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
    user_id = 'JBU423'
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
        else: print(f'login error: {str(ex)}')

    if broker is not None
        strategy = SwingETFAvgDown(broker=broker)
        # strategy._set_logger()
        strategy.on_trading_iteration()
