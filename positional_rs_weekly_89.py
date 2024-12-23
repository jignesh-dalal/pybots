import pandas as pd
import pandas_ta as ta
import utils as f
import math

from kite_trade import *
from datetime import datetime, timedelta

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

    nifty750 = f.get_all_records_from_sheet(worksheet_name='Nifty750')
    nifty750 = [x for x in nifty750 if x['SymbolIToken'] != -1]

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

    # stock = nifty750[266]
    # print(stock)

    for stock in nifty750:

        index = stock['Index']
        index_token = stock['IToken']
        symbol = stock['Symbol']
        symbol_token = stock['SymbolIToken']

        index_data = broker.historical_data(index_token, from_date, to_date, 'day')
        df_index = pd.DataFrame(index_data)
        df_index['Date'] = pd.to_datetime(df_index['Date'])
        df_index = df_index.set_index('Date')

        # Rename columns for clarity if necessary
        df_index.rename(columns={
            'Open': 'iOpen', 'High': 'iHigh', 'Low': 'iLow', 'Close': 'iClose', 'Volume': 'iVolume'
        }, inplace=True)

        # df_index


        symbol_data = broker.historical_data(symbol_token, from_date, to_date, 'day')
        df_symbol = pd.DataFrame(symbol_data)
        df_symbol['Date'] = pd.to_datetime(df_symbol['Date'])
        df_symbol = df_symbol.set_index('Date')


        #df_symbol

        df = pd.concat([df_index,df_symbol], axis=1)
        df = df.resample('W').apply(logic)
        # set the index to the beginning of the week
        df.index = df.index - pd.tseries.frequencies.to_offset("6D")

        df['RS'] = df['Close'] / df['iClose']
        df['RS_SMA'] = df['RS'].rolling(89).mean()
        df['RS_ABV_SMA'] = (df["RS"] >= df["RS_SMA"]).astype(int)
        df['RS_CROSS'] = df['RS_ABV_SMA'].diff().astype('Int64')

        # df.tail(22)

        rs_cross_latest = df['RS_CROSS'].iloc[-1]

        if rs_cross_latest == 1:
            print(symbol, index, df['RS'].iloc[-3], df['RS_SMA'].iloc[-3], df['RS_CROSS'].iloc[-3], sep=" | ")
            print(symbol, index, df['RS'].iloc[-2], df['RS_SMA'].iloc[-2], df['RS_CROSS'].iloc[-2], sep=" | ")
            print(symbol, index, df['RS'].iloc[-1], df['RS_SMA'].iloc[-1], df['RS_CROSS'].iloc[-1], sep=" | ")
            print("-------------------------------------------------------------------------------------------")
