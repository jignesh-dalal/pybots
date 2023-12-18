import json
import pyotp
import time
import requests
import gspread
import pandas as pd
import calendar
import os
import sys
import json

from datetime import datetime, date, timezone, timedelta
# from nsepy.derivatives import get_expiry_date
from kiteext import KiteExt

# from configparser import ConfigParser

# # Grab configuration values.
# config = ConfigParser()
# config.read('config/config.ini')

# USER_ID = config.get('main', 'USER_ID')
# USER_PWD = config.get('main', 'USER_PWD')
# TOTP_KEY = config.get('main', 'TOTP_KEY')
# ACCESS_TOKEN = config.get('main', 'ACCESS_TOKEN')
# NOTIFICATION_KEY = config.get('main', 'NOTIFICATION_KEY')




class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def notification(title, description):
    global data_dict
    notification_key = data_dict['notification_key']
    url = 'https://maker.ifttt.com/trigger/droid_notification/with/key/{}'.format(notification_key)
    myobj = {'value1': title, 'value2': description }

    requests.post(url, data=myobj)

def time_in_range(start, end, current):
    """Returns whether current is in the range [start, end]"""
    return start <= current <= end

def read_file(file):
    try:
        with open(file, "r") as f:
            data = f.read().strip()
        return data
    except FileNotFoundError:
        return None

def load_data():
    global wks
    global data_dict

    credentials = json.loads(GOOGLE_JSON)
    # print(type(credentials))
    gc = gspread.service_account_from_dict(credentials)
    # gc = gspread.service_account(filename='config/creds.json')
    wks = gc.open("trading_python").sheet1
    wks_data = wks.get_values()
    data_dict = {item[0]: item[1] for item in wks_data}

def kite_login(kite_client, user_id, password, totp_key):
    global wks
    global data_dict
    
    pin = pyotp.TOTP(totp_key).now()
    twoFA = f"{int(pin):06d}" if len(pin) <=5 else pin
    enctoken, public_token = kite_client.login_with_credentials(userid=user_id, password=password, twofa=twoFA)

    # print(enctoken)

    data_dict['access_token'] = enctoken
    wks.update_acell('B4', enctoken)

def create_session():
    global wks
    global data_dict

    kc = KiteExt()
    
    try:
        user_id = data_dict['user_id']
        password = data_dict['user_pwd'] 
        totp_key = data_dict['totp_key']
        access_token = data_dict['access_token']
        
        if access_token:
            # token = read_file('kite_token.txt')
            kc.login_using_enctoken(userid=user_id, enctoken=access_token, public_token=None)
            kc.profile()
        else:
            kite_login(kite_client=kc, user_id=user_id, password=password, totp_key=totp_key)
    
    except Exception as ex:
        if 'access_token' in str(ex):
            kite_login(kite_client=kc, user_id=user_id, password=password, totp_key=totp_key)
        else: print('login error: {}'.format(str(ex)))
    
    return kc

def weekly_expiry():
    today = date.today()
    expiry = today + timedelta(days=(10 - today.weekday()) % 7)

    while is_holiday(expiry):
        expiry = expiry - timedelta(days=1)

    print('Weekly: ' + expiry)
    return expiry

def monthly_expiry():
    today = date.today()
    expiry = calendar.monthrange(today.year, today.month)[1]
    expiry = today.replace(day=expiry)
    
    while expiry.weekday() != 3:
        expiry = expiry - timedelta(days=1)

    while is_holiday(expiry):
        expiry = expiry - timedelta(days=1)

    # print(expiry)
    return expiry


def is_holiday(expiry):
    holidays = pd.read_csv('./config/nse_holidays.csv')
    dates_list = [datetime.strptime(holiday, '%d/%m/%Y').date() for holiday in holidays['date']]

    return expiry in dates_list

def is_monthly_sip_order():
    # Get the current date
    today = datetime.today()
    expiry_date = monthly_expiry()
    is_expiry = today.date() == expiry_date
    start = datetime.now(timezone.utc).replace(hour=9, minute=44, second=0).time()
    end = datetime.now(timezone.utc).replace(hour=9, minute=58, second=0).time()
    current = datetime.now(timezone.utc).time()
    
    print('Today    : ' + today.strftime("%Y-%m-%d %H:%M:%S"))
    print('Expiry   : ' + expiry_date.strftime("%Y-%m-%d"))

    return is_expiry and time_in_range(start, end, current)
    # print(today.date())
    # expiry_set = get_expiry_date(year=today.year, month=today.month)
    # is_expiry = today.date() in expiry_set

    # print(expiry_date)

    # print(is_expiry)
    # fake = datetime.today().replace(day=28, hour=0, minute=0, second=0).date()
    # print('Date check:  ' + fake.strftime("%Y-%m-%d %H:%M:%S") + str(fake in expiry_set) + str(is_expiry))

    # print(start)
    # print(end)
    # local_datetime = datetime.now()
    # utc_datetime = datetime.now(timezone.utc)

    # utc_to_local_datetime = utc_datetime.astimezone()
    # utc_2_local_iso_str = datetime.strftime(utc_to_local_datetime, "%Y-%m-%dT%H:%M:%S.%f")[:-3]
    # print(local_datetime)
    # print(utc_2_local_iso_str)
    # print(end.astimezone().strftime("%Y-%m-%d %H:%M:%S"))
    # print(current)


# is_monthly_sip_order()

def is_avg_down_order(ltp, last_order):
    global data_dict

    if last_order is None:
        last_order = {}
        last_order['sip_price'] = 0
        last_order['avg_down_price'] = 0

    avg_down_percent = float(data_dict['avg_down_percent']) / 100
    price = last_order['sip_price'] if (last_order['avg_down_price'] == 0) else last_order['avg_down_price'] 
    avg_down_price = price * (1 - avg_down_percent)
    percent_away = 0 if avg_down_price == 0 else ((ltp / avg_down_price) - 1) * 100

    print('Price    : ' + bcolors.BOLD + bcolors.OKBLUE + str(ltp) + bcolors.ENDC)
    print('LOP      : ' + str(price))
    print('ADP      : ' + str(avg_down_price))
    print('% Away   : ' + bcolors.BOLD + bcolors.OKGREEN + str(round(percent_away, 1)) + '%' + bcolors.ENDC)
    
    return ltp <= avg_down_price

# is_avg_down_order(187.55)

def place_order(exchange, symbol, transaction_type, quantity, order_type = None, price = None, product = None):
    global kite
    order_id = None
    try:
        if order_type == 'MARKET':
            price = 0
            trigger_price = None
            product = kite.PRODUCT_CNC

        order_id = kite.place_order(tradingsymbol = symbol,
                                exchange = exchange,
                                transaction_type = transaction_type,
                                quantity = quantity,
                                price = price,
                                trigger_price=trigger_price,
                                variety = kite.VARIETY_REGULAR,
                                order_type = order_type,
                                product = product)
        
        print(f"Order id = {order_id}")
    except Exception as e:
        message = "Order rejected with error : " + str(e)
        print(message)
    
    return order_id
    

def get_order_data():
    global data_dict

    return {
        "id": data_dict['last_order_id'],
        "qty": int(data_dict['last_order_qty']),
        "sip_price": float(data_dict['last_sip_price']),
        "avg_down_price": float(data_dict['last_avg_down_price'])
    }


    # last_order = read_file('kite_order_data.txt')
    # if last_order is not None:
    #     last_order = json.loads(str(last_order))
    
    # return last_order

def save_order_data(order_id, sip_price, quantity, avg_down_price):
    global wks
    global data_dict

    data_dict['last_order_id'] = order_id
    data_dict['last_order_qty'] = quantity
    data_dict['last_sip_price'] = sip_price
    data_dict['last_avg_down_price'] = avg_down_price

    wks.update_acell('B9', order_id) 
    wks.update_acell('B10', quantity)
    wks.update_acell('B11', sip_price)
    wks.update_acell('B12', avg_down_price)
    
    # order = {
    #     "id": order_id,
    #     "sip_price": sip_price,
    #     "qty": quantity,
    #     "avg_down_price": avg_down_price
    # }
    # order_json = json.dumps(order)
    # with open("kite_order_data.txt", "w") as fs:
    #     fs.write(order_json)

def trading_job():
    global kite
    global scheduler
    global data_dict

    load_data()

    skip_job = data_dict['skip_job'].lower() in ['true', '1', 't', 'y', 'yes']
    if skip_job:
        print('Skipping run as skip_job is set..')
        return
    
    kite = create_session()
    
    exchange_symbol = data_dict['symbol']
    exchange = exchange_symbol[:3]
    symbol = exchange_symbol[4:]
    qty = int(data_dict['sip_quantity'])

    print('- - - - - - - - - - - - - - - -')
    print(bcolors.HEADER + '- - Checking ' + exchange_symbol + ' - -' + bcolors.ENDC)
    
    is_sip = is_monthly_sip_order()
    
    is_avg_down = False
    last_order = get_order_data()

    # print(last_order)
    ltp_data = kite.ltp(exchange_symbol)
    ltp = ltp_data[exchange_symbol]['last_price']
        
    # if last_order is not None:
    is_avg_down = is_avg_down_order(ltp, last_order)

    if is_sip or is_avg_down:
        order_id = place_order(exchange, symbol, 'BUY', qty, 'MARKET')

        if order_id is not None:
            time.sleep(10)
            order_history = kite.order_history(order_id = order_id)
            
            if order_history[-1].get('status') == 'COMPLETE':
                order_price = order_history[-1].get('average_price')
                price = order_price if is_sip else last_order['sip_price']
                qty = order_history[-1].get('filled_quantity')
                avg_down_price = order_price if is_avg_down else 0
                try:
                    save_order_data(order_id, price, qty, avg_down_price)
                    notification('Bought ' + exchange_symbol, 'Buy Price ' + str(order_price) + ' - Quantity ' + str(qty))
                except Exception as ex:
                    print('error with save order')
                    print(ex)
    # else:
    #     print('No order placed as criterias not met!!')


def exit_gracefully():
    print('shutdown scheduler gracefully')
    scheduler.shutdown(wait=False)


scheduler = None
wks = None
data_dict = None
kite = None

try:
    GOOGLE_JSON = os.environ["GOOGLE_JSON"]
except KeyError:
    GOOGLE_JSON = read_file('config/creds.json')

if __name__ == "__main__":
    try:
        trading_job()
    except Exception as ex:
        print('Error occurred! Terminating...')
        print(ex)