import time
import utils as f

from datetime import datetime, date, timezone
from kite_trade import *

class Strategy:
    
    def __init__(self, *args, broker:KiteApp=None, **kwargs):
        self.broker = broker
        self.tick_received = False
        super().__init__(*args, **kwargs)
    
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
        self.instrument_tokens = []
        self.broker.start_stream(self.on_ws_ticks, self.instrument_tokens)

        count = 0
        while not self.tick_received:
            count += 1
            # print(f'Count: {count}')
            if count < 5: time.sleep(1)  
            else: break
        
        if self.tick_received:
            pass
        else:
            print(f'{f.bcolors.WARNING}Skipping run as no tick received.{f.bcolors.ENDC}')

        # time.sleep(15)
        self.broker.end_stream(self.instrument_tokens)

if __name__ == "__main__":
    
    user_id = 'SJ0281'
    config = f.get_creds_by_user_id(user_id)

    # config = {
    #     'USER_ID': 'SJ0281',
    #     'PASSWORD': '',
    #     'TOTP_KEY': '',
    #     'ACCESS_TOKEN': 'EFmypalwkfU/igrlrUAwjfwjitY/e0xzR327GxVtI+pJTBb6hGEzvuNhdRdxYUOUzE6Re91lYbviTzUDf9Kr+4t5BmBFEyKQ14eytCx2LI7gacSugBBcNg==',
    # }
    
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

    strategy = Strategy(broker=broker)
    # strategy._set_logger()
    strategy.on_trading_iteration()