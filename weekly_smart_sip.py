import time
import tradetools.utils as f

from datetime import datetime, date, timezone
# from tradetools.utils import get_creds_by_user_id, get_values_from_worksheet, update_values_by_row_key_in_worksheet, notification, bcolors
from tradetools.brokers import Kite

class WeeklySmartSIP:
    
    def __init__(self, *args, broker:Kite=None, **kwargs):
        self.broker = broker
        super().__init__(*args, **kwargs)
    
    [staticmethod]
    def time_in_range(start, end, current):
        """Returns whether current is in the range [start, end]"""
        return start <= current <= end
    
    [staticmethod]
    def is_sip_day():
        tdate = date.today()
        is_tue_thu = tdate.isoweekday() in [2,4]
        start = datetime.now(timezone.utc).replace(hour=9, minute=44, second=0).time()
        end = datetime.now(timezone.utc).replace(hour=9, minute=58, second=0).time()
        current = datetime.now(timezone.utc).time()

        print(f"Weekday  : {tdate.strftime('%A')}")

        return is_tue_thu and WeeklySmartSIP.time_in_range(start, end, current)
    
    [staticmethod]
    def is_avg_down_order(ltp, last_order, sip_data):

        if last_order is None:
            last_order = {}
            last_order['sip_price'] = 0
            last_order['avg_down_price'] = 0

        avg_down_percent = float(sip_data['avg_down_percent']) / 100
        price = last_order['sip_price'] if (last_order['avg_down_price'] == 0) else last_order['avg_down_price'] 
        avg_down_price = price * (1 - avg_down_percent)
        percent_away = 0 if avg_down_price == 0 else ((ltp / avg_down_price) - 1) * 100

        print('Price    : ' + f.bcolors.BOLD + f.bcolors.OKBLUE + str(ltp) + f.bcolors.ENDC)
        print('LOP      : ' + str(price))
        print('ADP      : ' + str(avg_down_price))
        print('% Away   : ' + f.bcolors.BOLD + f.bcolors.OKGREEN + str(round(percent_away, 1)) + '%' + f.bcolors.ENDC)
        
        return ltp <= avg_down_price
        
    def on_trading_iteration(self):
        # self.load_data()
        wks_name = "SIP"
        sip_dict = f.get_values_from_worksheet(worksheet_name=wks_name)
        for key in sip_dict.keys():
            print('- - - - - - - - - - - - - - - - - - -')
            skip_job = sip_dict[key]['skip_job'].lower() in ['true', '1', 't', 'y', 'yes']
            if skip_job:
                print(f'{f.bcolors.WARNING}Skipping run for {key} as skip_job is set..{f.bcolors.ENDC}')
                continue

            broker.create_session()

            sip_data = sip_dict[key]
            exchange_symbol = sip_data['symbol']
            exchange = exchange_symbol[:3]
            symbol = exchange_symbol[4:]
            sip_amount = int(sip_data['sip_amount'])
            
            userId = self.broker.user_id
            print(f'{f.bcolors.HEADER}- - {userId} Checking {exchange_symbol} - -{f.bcolors.ENDC}')

            is_sip = WeeklySmartSIP.is_sip_day()
        
            is_avg_down = False
            last_order = {
                "id": sip_data['last_order_id'],
                "qty": int(sip_data['last_order_qty']),
                "sip_price": float(sip_data['last_sip_price']),
                "avg_down_price": float(sip_data['last_avg_down_price'])
            }

            # print(last_order)
            asset = self.broker.create_asset(symbol, exchange=exchange)
            ltp_dict = self.broker.ltp(asset)
            ltp = ltp_dict[asset.exchange_symbol]['last_price']
            
            # if last_order is not None:
            is_avg_down = WeeklySmartSIP.is_avg_down_order(ltp, last_order, sip_data)

            if is_sip or is_avg_down:
                ask_bid_dict = self.broker.get_ask_bid(asset)
                price = ask_bid_dict[exchange_symbol]['bids'][0]['price']
                price = ltp if price == 0 else price
                qty = round(sip_amount / price)

                print(f'{f.bcolors.OKGREEN}Placing BUY order for {qty} quantity at {price} price..{f.bcolors.ENDC}')

                order_id = self.broker.place_order(asset, 'BUY', qty, price=price)

                if order_id is not None:
                    time.sleep(10)
                    order_history = self.broker.order_history(order_id)
                    
                    if order_history[-1].get('status') == 'COMPLETE':
                        order_price = order_history[-1].get('average_price')
                        price = order_price if is_sip else last_order['sip_price']
                        qty = order_history[-1].get('filled_quantity')
                        avg_down_price = order_price if is_avg_down else 0
                        try:
                            order_data = {
                                'last_order_id': order_id,
                                'last_order_qty': qty,
                                'last_sip_price': price,
                                'last_avg_down_price': avg_down_price
                            }
                            f.update_values_by_row_key_in_worksheet(key, order_data, worksheet_name=wks_name)
                            
                            f.notification(f'Bought {exchange_symbol}, Buy Price {str(order_price)} - Quantity {str(qty)}', config['NOTIFICATION_KEY'])
                        except Exception as ex:
                            print('error with save order')
                            print(ex)

if __name__ == "__main__":
    # config = {
    #     'USER_ID': 'SJ0281',
    #     'PASSWORD': '',
    #     'TOTP_KEY': '',
    #     'ACCESS_TOKEN': 'EFmypalwkfU/igrlrUAwjfwjitY/e0xzR327GxVtI+pJTBb6hGEzvuNhdRdxYUOUzE6Re91lYbviTzUDf9Kr+4t5BmBFEyKQ14eytCx2LI7gacSugBBcNg==',
    # }
    config = f.get_creds_by_user_id('SJ0281')
    broker = Kite(config)
    strategy = WeeklySmartSIP(broker=broker)
    # strategy._set_logger()
    strategy.on_trading_iteration()
