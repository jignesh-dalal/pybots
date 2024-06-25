import os
try:
    import requests
except ImportError:
    os.system('python -m pip install requests')
try:
    import dateutil
except ImportError:
    os.system('python -m pip install python-dateutil')
try:
    import kiteconnect
except ImportError:
    os.system('python -m pip install kiteconnect')
try:
    import pyotp
except ImportError:
    os.system('python -m pip install pyotp')

import time
import requests
import dateutil.parser
import pyotp
import json

from kiteconnect import KiteTicker

def get_totp(totp_key):
    pin = pyotp.TOTP(totp_key).now()
    twoFA = f"{int(pin):06d}" if len(pin) <= 5 else pin
    return twoFA

def get_enctoken(userid, password, twofa):
    session = requests.Session()
    response = session.post('https://kite.zerodha.com/api/login', data={
        "user_id": userid,
        "password": password
    })
    response = session.post('https://kite.zerodha.com/api/twofa', data={
        "request_id": response.json()['data']['request_id'],
        "twofa_value": twofa,
        "user_id": response.json()['data']['user_id']
    })
    enctoken = response.cookies.get('enctoken')
    if enctoken:
        return enctoken
    else:
        raise Exception("Enter valid details !!!!")

class KiteApp:
    # Products
    PRODUCT_MIS = "MIS"
    PRODUCT_CNC = "CNC"
    PRODUCT_NRML = "NRML"
    PRODUCT_CO = "CO"

    # Order types
    ORDER_TYPE_MARKET = "MARKET"
    ORDER_TYPE_LIMIT = "LIMIT"
    ORDER_TYPE_SLM = "SL-M"
    ORDER_TYPE_SL = "SL"

    # Varities
    VARIETY_REGULAR = "regular"
    VARIETY_CO = "co"
    VARIETY_AMO = "amo"

    # Transaction type
    TRANSACTION_TYPE_BUY = "BUY"
    TRANSACTION_TYPE_SELL = "SELL"

    # Validity
    VALIDITY_DAY = "DAY"
    VALIDITY_IOC = "IOC"

    # Exchanges
    EXCHANGE_NSE = "NSE"
    EXCHANGE_BSE = "BSE"
    EXCHANGE_NFO = "NFO"
    EXCHANGE_CDS = "CDS"
    EXCHANGE_BFO = "BFO"
    EXCHANGE_MCX = "MCX"

    # GTT order type
    GTT_TYPE_OCO = "two-leg"
    GTT_TYPE_SINGLE = "single"

    # GTT order status
    GTT_STATUS_ACTIVE = "active"
    GTT_STATUS_TRIGGERED = "triggered"
    GTT_STATUS_DISABLED = "disabled"
    GTT_STATUS_EXPIRED = "expired"
    GTT_STATUS_CANCELLED = "cancelled"
    GTT_STATUS_REJECTED = "rejected"
    GTT_STATUS_DELETED = "deleted"

    def __init__(self, enctoken, user_id=''):
        self.enctoken = enctoken
        self.headers = {"Authorization": f"enctoken {self.enctoken}"}
        self.session = requests.session()
        self.root_url = "https://kite.zerodha.com/oms"
        self.session.get(self.root_url, headers=self.headers)
        self.user_id = user_id if user_id else self.profile()["user_id"]
        self.kws = KiteTicker(api_key="TradingPython", access_token=enctoken+"&user_id="+self.user_id)

    def instruments(self, exchange=None):
        data = self.session.get(f"https://api.kite.trade/instruments").text.split("\n")
        Exchange = []
        for i in data[1:-1]:
            row = i.split(",")
            if exchange is None or exchange == row[11]:
                Exchange.append({'instrument_token': int(row[0]), 'exchange_token': row[1], 'tradingsymbol': row[2],
                                 'name': row[3][1:-1], 'last_price': float(row[4]),
                                 'expiry': dateutil.parser.parse(row[5]).date() if row[5] != "" else None,
                                 'strike': float(row[6]), 'tick_size': float(row[7]), 'lot_size': int(row[8]),
                                 'instrument_type': row[9], 'segment': row[10],
                                 'exchange': row[11]})
        return Exchange

    def historical_data(self, instrument_token, from_date, to_date, interval='day', continuous=False, oi=False):
        params = {"from": from_date,
                  "to": to_date,
                  "interval": interval,
                  "continuous": 1 if continuous else 0,
                  "oi": 1 if oi else 0}
        lst = self.session.get(
            f"{self.root_url}/instruments/historical/{instrument_token}/{interval}", params=params,
            headers=self.headers).json()["data"]["candles"]
        records = []
        for i in lst:
            record = {"Date": dateutil.parser.parse(i[0]), "Open": i[1], "High": i[2], "Low": i[3],
                      "Close": i[4], "Volume": i[5],}
            if len(i) == 7:
                record["OI"] = i[6]
            records.append(record)
        return records

    def margins(self):
        margins = self.session.get(f"{self.root_url}/user/margins", headers=self.headers).json()["data"]
        return margins

    def profile(self):
        profile = self.session.get(f"{self.root_url}/user/profile", headers=self.headers).json()["data"]
        return profile

    def orders(self):
        orders = self.session.get(f"{self.root_url}/orders", headers=self.headers).json()["data"]
        return orders
    
    def order_history(self, order_id):
        """
        Get history of individual order.

        - `order_id` is the ID of the order to retrieve order history.
        """
        return self.session.get(f"{self.root_url}/orders/{order_id}", headers=self.headers).json()["data"]

    def positions(self):
        positions = self.session.get(f"{self.root_url}/portfolio/positions", headers=self.headers).json()["data"]
        return positions
    
    def holdings(self):
        holdings = self.session.get(f"{self.root_url}/portfolio/holdings", headers=self.headers).json()["data"]
        return holdings

    def place_order(self, variety, exchange, tradingsymbol, transaction_type, quantity, product, order_type, price=None,
                    validity=None, disclosed_quantity=None, trigger_price=None, squareoff=None, stoploss=None,
                    trailing_stoploss=None, tag=None):
        params = locals()
        del params["self"]
        for k in list(params.keys()):
            if params[k] is None:
                del params[k]
        print(params)
        order_id = self.session.post(f"{self.root_url}/orders/{variety}",
                                     data=params, headers=self.headers).json()["data"]["order_id"]
        return order_id

    def modify_order(self, variety, order_id, parent_order_id=None, quantity=None, price=None, order_type=None,
                     trigger_price=None, validity=None, disclosed_quantity=None):
        params = locals()
        del params["self"]
        for k in list(params.keys()):
            if params[k] is None:
                del params[k]

        order_id = self.session.put(f"{self.root_url}/orders/{variety}/{order_id}",
                                    data=params, headers=self.headers).json()["data"][
            "order_id"]
        return order_id

    def cancel_order(self, variety, order_id, parent_order_id=None):
        order_id = self.session.delete(f"{self.root_url}/orders/{variety}/{order_id}",
                                       data={"parent_order_id": parent_order_id} if parent_order_id else {},
                                       headers=self.headers).json()["data"]["order_id"]
        return order_id
    

    # MY CODE
    def gtt_orders(self):
        gtt_orders = self.session.get(f"{self.root_url}/gtt/triggers", headers=self.headers).json()["data"]
        return gtt_orders
    
    def gtt_order(self, order_id):
        gtt_order = self.session.get(f"{self.root_url}/gtt/triggers/{order_id}", headers=self.headers).json()["data"]
        return gtt_order
    
    def _get_gtt_payload(self, trigger_type, tradingsymbol, exchange, trigger_values, last_price, orders):
        """Get GTT payload"""
        if type(trigger_values) != list:
            raise Exception("invalid type for `trigger_values`")
        if trigger_type == self.GTT_TYPE_SINGLE and len(trigger_values) != 1:
            raise Exception("invalid `trigger_values` for single leg order type")
        elif trigger_type == self.GTT_TYPE_OCO and len(trigger_values) != 2:
            raise Exception("invalid `trigger_values` for OCO order type")

        condition = {
            "exchange": exchange,
            "tradingsymbol": tradingsymbol,
            "trigger_values": trigger_values,
            "last_price": last_price,
        }

        gtt_orders = []
        for o in orders:
            # Assert required keys inside gtt order.
            for req in ["transaction_type", "quantity", "order_type", "product", "price"]:
                if req not in o:
                    raise Exception("`{req}` missing inside orders".format(req=req))
            gtt_orders.append({
                "exchange": exchange,
                "tradingsymbol": tradingsymbol,
                "transaction_type": o["transaction_type"],
                "quantity": int(o["quantity"]),
                "order_type": o["order_type"],
                "product": o["product"],
                "price": float(o["price"]),
            })

        return condition, gtt_orders

    
    def place_gtt(self, trigger_type, tradingsymbol, exchange, trigger_values, last_price, orders):
        # Validations.
        assert trigger_type in [self.GTT_TYPE_OCO, self.GTT_TYPE_SINGLE]
        condition, gtt_orders = self._get_gtt_payload(trigger_type, tradingsymbol, exchange, trigger_values, last_price, orders)

        params = {
            "condition": json.dumps(condition),
            "orders": json.dumps(gtt_orders),
            "type": trigger_type
        }
        trigger_id = self.session.post(f"{self.root_url}/gtt/triggers",
                                     data=params, headers=self.headers).json()["data"]["trigger_id"]
        return trigger_id
    
    def modify_gtt(
        self, trigger_id, trigger_type, tradingsymbol, exchange, trigger_values, last_price, orders
    ):
        condition, gtt_orders = self._get_gtt_payload(trigger_type, tradingsymbol, exchange, trigger_values, last_price, orders)
        
        params = {
            "condition": json.dumps(condition),
            "orders": json.dumps(gtt_orders),
            "type": trigger_type
        }
        trigger_id = self.session.put(f"{self.root_url}/gtt/triggers/{trigger_id}",
                                     data=params, headers=self.headers).json()["data"]["trigger_id"]
        return trigger_id
    
    def delete_gtt(self, trigger_id):
        trigger_id = self.session.delete(f"{self.root_url}/gtt/triggers/{trigger_id}", 
                                         headers=self.headers).json()["data"]["trigger_id"]
        return trigger_id

    def start_stream(self, on_ticks, instrument_tokens, mode=KiteTicker.MODE_FULL):
        self.kws.on_ticks = on_ticks
        self.kws.connect(threaded=True)
        while not self.kws.is_connected():
            time.sleep(1)
        print("WebSocket : Connected")
        self.kws.subscribe(instrument_tokens)
        self.kws.set_mode(mode, instrument_tokens)

    def end_stream(self, instrument_tokens):
        self.kws.unsubscribe(instrument_tokens)
        self.kws.close()