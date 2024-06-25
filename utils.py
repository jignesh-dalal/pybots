import os
import re
import json
import gspread
import requests
import pandas as pd

from datetime import datetime
from typing import Dict, Any

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


def notification(title, description, notification_key):
    url = 'https://maker.ifttt.com/trigger/droid_notification/with/key/{}'.format(notification_key)
    myobj = {'value1': title, 'value2': description }

    requests.post(url, data=myobj)

def read_file(file):
    try:
        with open(file, "r") as f:
            data = f.read().strip()
        return data
    except FileNotFoundError:
        return None
    
def get_values_from_worksheet(spreadsheet_name="trading_python", worksheet_name="Creds") -> Dict[str, Dict[str, str]]:
    sh = get_spreadsheet_by_name(spreadsheet_name)
    worksheet = sh.worksheet(worksheet_name)
    all_values_list = worksheet.get_all_values()
    prop_list = all_values_list[0]

    values_dict = {}
    for i in range(1, len(all_values_list)):
        item = all_values_list[i]
        # print(f'i->{i}, I->{item}')
        key = item[0]
        value = {prop_list[j]: item[j] for j, d in enumerate(prop_list)}
        values_dict[key] = value

    return values_dict

def update_values_by_row_key_in_worksheet(row_key, values: Dict[str, str], spreadsheet_name="trading_python", worksheet_name="Creds"):
    sh = get_spreadsheet_by_name(spreadsheet_name)
    worksheet = sh.worksheet(worksheet_name)
    row_number = worksheet.find(row_key).row
    
    if row_number is not None:
        prop_list = worksheet.row_values(1)
        for i, d in enumerate(prop_list):
            # print(i)
            prop_key = prop_list[i]
            if prop_key in values.keys():
                value_to_update = values[prop_key]
                # print(f"Col->{i} - Prop->{prop_key} - Val->{value_to_update}")
                worksheet.update_cell(row_number, i+1, value_to_update)

# all_creds_dict = None
def get_creds(spreadsheet_name="trading_python"):
    # if all_creds_dict is not None:
    #     return all_creds_dict
    
    # try:
    #     GOOGLE_JSON = os.environ["GOOGLE_JSON"]
    # except KeyError:
    #     GOOGLE_JSON = read_file('config/creds.json')

    # credentials = json.loads(GOOGLE_JSON)
    # # print(type(credentials))
    # gc = gspread.service_account_from_dict(credentials)
    # sh = gc.open("trading_python")

    sh = get_spreadsheet_by_name(spreadsheet_name)

    worksheet = sh.worksheet("Creds")
    # all_records = worksheet.get_records()
    all_values_list = worksheet.get_all_values()
    prop_list = all_values_list[0]

    creds_dict = {}
    for i in range(1, len(all_values_list)):
        item = all_values_list[i]
        # print(f'i->{i}, I->{item}')
        key = item[0]
        value = {prop_list[j]: item[j] for j, d in enumerate(prop_list)}
        creds_dict[key] = value

    # all_creds_dict = creds_dict
    return creds_dict

def get_creds_by_user_id(user_id):
    creds = get_values_from_worksheet() # get_creds()
    return creds[user_id]

def get_spreadsheet_by_name(name):
    try:
        GOOGLE_JSON = os.environ["GOOGLE_JSON"]
    except KeyError:
        GOOGLE_JSON = read_file('config/creds.json')

    credentials = json.loads(GOOGLE_JSON)
    # print(type(credentials))
    gc = gspread.service_account_from_dict(credentials)
    sh = gc.open(name)
    return sh

def get_worksheets(spreadsheet_name, exclude_list=[], exclude_hidden=False):
    sh = get_spreadsheet_by_name(spreadsheet_name)
    wks_list = [wks for wks in sh.worksheets(exclude_hidden) if wks.title not in exclude_list]
    return wks_list

def get_last_row(worksheet):
    str_list = list(filter(None, worksheet.col_values(1)))
    return len(str_list)

def next_available_row(worksheet):
    return str(get_last_row(worksheet)+1)

def get_all_records_from_sheet(spreadsheet_name="trading_python", worksheet_name="Logs"):
    sh = get_spreadsheet_by_name(spreadsheet_name)
    worksheet = sh.worksheet(worksheet_name)
    return worksheet.get_all_records()

def write_log_to_excel(title, data, spreadsheet_name="trading_python", worksheet_name="Logs"):
    sh = get_spreadsheet_by_name(spreadsheet_name)
    worksheet = sh.worksheet(worksheet_name)
    next_row = next_available_row(worksheet)
    worksheet.update_acell(f"A{next_row}", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    worksheet.update_acell(f"B{next_row}", title)
    worksheet.update_acell(f"C{next_row}", data)

def write_df_to_excel_sheet(df, spreadsheet_name="trading_python", worksheet_name="Logs"):
    headers = [df.columns.values.tolist()]
    rows = df.values.tolist()
    sh = get_spreadsheet_by_name(spreadsheet_name)
    worksheet = sh.worksheet(worksheet_name)
    worksheet.update(headers + rows)

def write_toppers_to_excel(data, spreadsheet_name="trading_python", worksheet_name="Top13"):
    sh = get_spreadsheet_by_name(spreadsheet_name)
    worksheet = sh.worksheet(worksheet_name)
    worksheet.update_acell(f"A1", data)

def read_toppers_from_excel(spreadsheet_name="trading_python", worksheet_name="Top13"):
    sh = get_spreadsheet_by_name(spreadsheet_name)
    worksheet = sh.worksheet(worksheet_name)
    return worksheet.acell('A1').value


niftyindices_headers = {
    'Connection': 'keep-alive',
    'Cache-Control': 'max-age=0',
    'DNT': '1',
    'Upgrade-Insecure-Requests': '1',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.79 Safari/537.36',
    'Sec-Fetch-User': '?1',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-Mode': 'navigate',
    'Accept-Encoding': 'gzip, deflate, br',
    'Accept-Language': 'en-US,en;q=0.9,hi;q=0.8',
}

index_stock_list_url = 'https://www.niftyindices.com/IndexConstituent/ind_{0}list.csv'

def get_nse_index_stocklist(index_name):
    trim_index_name = re.sub(r'\s+', '', index_name)
    url = index_stock_list_url.format(trim_index_name.lower())
    
    # reading the data in the csv file 
    df = pd.read_csv(url, storage_options=niftyindices_headers)
    df.index = df.index + 1

    return df