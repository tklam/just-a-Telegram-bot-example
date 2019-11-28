from __future__ import print_function
import pickle
import os.path
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from oauth2client.service_account import ServiceAccountCredentials

# If modifying these scopes, delete the file token.pickle.
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']

# The ID and range of a sample spreadsheet.
SPREADSHEET_ID = #FIXME your spreadsheets ID
REGION_RANGE_NAME = '光復香港!A2:B' # max 2 levels of hierarchy #FIXME
RESTAURANT_RANGE_NAME= '時代革命!A2:H' #FIXME

def isRowHasData(row):
    num_cols = len(row)
    has_data=False
    indent=0
    for i in range(0, num_cols):
        if row[i]:
            indent=i
            has_data=True
            break

    return has_data, indent

def parseRegionData(region_values):
    if not region_values:
        sys.exit("Cannot obtain region data")

    indent=0
    prev_indent=-1
    row_count=0
    region_data = {}
    hier_stack=[]
    hier_stack.append(region_data)

    for row in region_values:
        has_data, indent = isRowHasData(row)
        if not has_data:
            continue

        # key=str(row_count)+'-'+row[indent]
        key=row[indent]

        if indent>prev_indent: # go deeper
            hier_stack[-1]['regions'] = {}
            region_data = hier_stack[-1]['regions']
            region_data[key] = {}
            region_data[key]['name'] = row[indent]
            hier_stack.append(region_data[key])
            #print(region_data)
        elif indent == prev_indent: # same level
            hier_stack.pop()
            region_data[key] = {}
            region_data[key]['name'] = row[indent]
            hier_stack.append(region_data[key])
            #print(region_data)
        elif indent < prev_indent: # go up
            for i in range(0, prev_indent - indent +1):
                hier_stack.pop() # the first element in the previous deeper level
            region_data = hier_stack[-1]['regions']
            region_data[key] = {}
            region_data[key]['name'] = row[indent]
            hier_stack.append(region_data[key])
            #print(region_data)

        prev_indent=indent
        row_count=row_count+1

    region_data = hier_stack[0]
    #print(region_data)

    return region_data

def parseRestaurantData(restaurant_values):
    if not restaurant_values:
        sys.exit("Cannot obtain region data")

    restaurant_data = {}

    i = 0
    for row in restaurant_values:
        has_data, _ = isRowHasData(row)
        if not has_data:
            continue

        if len(row) < 4:
            continue

        if row[3] == '':
            continue

        key = str(i) + '-' + row[3]
        restaurant_data[key] = {}

        restaurant_data[key]['name'] = row[3]
        if len(row) > 4:
            restaurant_data[key]['tel'] = row[4]
        if len(row) > 5:
            restaurant_data[key]['address'] = row[5]
        if len(row) > 6:
            restaurant_data[key]['opening_hours'] = row[6]
        if len(row) > 7:
            restaurant_data[key]['remark'] = row[7]

        restaurant_data[key]['address-1'] = row[0]
        restaurant_data[key]['address-2'] = row[1]
        restaurant_data[key]['region'] = row[2]
        if restaurant_data[key]['region'] == '':
            restaurant_data[key]['region'] = restaurant_data[key]['address-2']

    return restaurant_data


def getDataFromSpreadsheet():
    #FIXME need to get "Service Account Credentials" in console.google.com
    creds = ServiceAccountCredentials.from_json_keyfile_name(#FIXME , scopes=SCOPES)
    service = build('sheets', 'v4', credentials=creds)

    # Call the Sheets API
    sheet = service.spreadsheets()
    region_data = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=REGION_RANGE_NAME).execute()
    restaurant_data = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=RESTAURANT_RANGE_NAME).execute()
    region_values = region_data.get('values', [])
    restaurant_values = restaurant_data.get('values', [])

    # process regions
    region_data = parseRegionData(region_values);
        
    # process restaurants
    restaurant_data = parseRestaurantData(restaurant_values);

    # supplement region data with restaurant data
    for _,r in restaurant_data.items():
        x = region_data['regions'][r['address-1']]['regions'][r['address-2']]
        if 'regions' not in x:
            x['regions'] = {}
        x['regions'][r['region']] = {}
        x['regions'][r['region']]['name'] = r['region']

    return region_data, restaurant_data

if __name__ == '__main__':
    region_data, restaurant_data = getDataFromSpreadsheet()
    print(region_data)
    print(restaurant_data)
