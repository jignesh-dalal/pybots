import time
import utils as f
import pandas as pd 

from datetime import datetime, date, timezone
from kite_trade import *

class NiftyIndices:
    
    def __init__(self, *args, broker:KiteApp=None, **kwargs):
        self.broker = broker

        self.broad_indices = {
                'NIFTY 50' : 'NIFTY',
                'NIFTY NEXT 50' : 'NIFTYJR',
                # 'NIFTY 100',
                # 'NIFTY 200',
                # 'NIFTY 500',
                'NIFTY MIDCAP 150' : 'NIFTYMIDCAP150',
                # 'NIFTY MIDCAP 50',
                # 'NIFTY MIDCAP 100',
                'NIFTY SMALLCAP 250' : 'NIFTYSMLCAP250',
                # 'NIFTY SMALLCAP 50',
                # 'NIFTY SMALLCAP 100',
                # 'NIFTY LARGEMIDCAP 250',
                #'NIFTY MIDSMALLCAP 400',
                'NIFTY MICROCAP 250_': 'NIFTY_MICROCAP250'
        }

        self.nse = []

        super().__init__(*args, **kwargs)

    def get_itoken(self, row):
        itoken = next((x['instrument_token'] for x in self.nse if x['tradingsymbol'] == row['Symbol']), -1)
        return itoken
        
    def on_trading_iteration(self):
       
        self.nse = self.broker.instruments('NSE')

        df = pd.DataFrame()
        for index, index_symbol in self.broad_indices.items():
            df_index = f.get_nse_index_stocklist(index)
            df_index['Index'] = index_symbol
            df_index['IToken'] = df_index.apply(self.get_itoken, axis=1)
            
            df = pd.concat([df, df_index], ignore_index=True)
            time.sleep(0.5)

        f.write_df_to_excel_sheet(df, worksheet_name='Nifty750')



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

    strategy = NiftyIndices(broker=broker)
    # strategy._set_logger()
    strategy.on_trading_iteration()