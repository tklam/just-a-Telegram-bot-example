#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json
import os
import math

import sys
import telepot
import time

from telepot.loop import MessageLoop
from telepot.namedtuple import InlineKeyboardMarkup, InlineKeyboardButton
from spreadsheet_reader import getDataFromSpreadsheet

TOKEN = ""
PASSWORD = "changeme"
region_keyboard = None
region_callbacks={}
region_button_index=0
restaurants_page_callbacks={}

def restaurantToStr(r):
    restaurant_msg = '*{}*\n'.format(r['name'])
    if 'address' in r:
        restaurant_msg = restaurant_msg + '地址：{}\n'.format(r['address'])
    if 'tel' in r :
        restaurant_msg = restaurant_msg + '電話：{}\n'.format(r['tel'])
    if 'opening_hours' in r:
        restaurant_msg = restaurant_msg + '營業時間：{}\n'.format(r['opening_hours'])
    if 'remark' in r:
        restaurant_msg = restaurant_msg + '備註：{}\n'.format(r['remark'])
    restaurant_msg = restaurant_msg + '\n'
    return restaurant_msg

def buildRestaurantsPage(start_index, end_index, restaurants):
    restaurant_msg = '' 
    for i in range(start_index, end_index): 
        if i == len(restaurants): 
            break 
        r = restaurants[i] 
        restaurant_msg = restaurant_msg + restaurantToStr(r) 
    return restaurant_msg

def editRestaurantsPage(chat_id, message_id, start_index, end_index, restaurants):
    try:
        bot.editMessageText((chat_id, message_id), text=buildRestaurantsPage(start_index, end_index, restaurants), parse_mode='Markdown')
    except telepot.exception.TelegramError:
        return

def replySelectedRegion(bot, chat_id, query_id, data_root, region_name, traverse_next_data_root):
    global restaurants_page_callbacks
    bot.answerCallbackQuery(query_id, text=region_name)
    if traverse_next_data_root:
        keyboard = createRegionKeyboard(data_root, region_callbacks)
        bot.sendMessage(chat_id, '麻煩揀分區？', reply_markup=keyboard)
    else: # list restaurant
        # build the first page of restaurants
        restaurant_msg = ''
        max_res_per_page = 5
        if 'restaurants' not in data_root:
            return

        res = data_root['restaurants']
        restaurant_msg = buildRestaurantsPage(0, max_res_per_page, res)
        chat_message_id = telepot.message_identifier(bot.sendMessage(chat_id, restaurant_msg, parse_mode='Markdown'))

        # build buttons for changing pages
        num_page = math.ceil(len(res) / (max_res_per_page * 1.0))
        if num_page == 1:
            return

        res_button_rows=[]
        page_buttons=[]
        for i in range(0, num_page):
            callback_data = 'restaurants-' + str(chat_message_id[0])+ '-' + str(chat_message_id[1]) + '-' + str(i)
            page_buttons.append(InlineKeyboardButton(text=i, callback_data=callback_data))
            if len(page_buttons) == 5:
                res_button_rows.append(page_buttons)
                page_buttons = []

            restaurants_page_callbacks[callback_data] = \
                lambda bot=bot, chat_id=chat_message_id[0], message_id=chat_message_id[1], restaurants=res, start_index=i*max_res_per_page, end_index=i*max_res_per_page+max_res_per_page : \
                    editRestaurantsPage(chat_id, message_id, start_index, end_index, restaurants)

        if len(page_buttons) > 0:
            res_button_rows.append(page_buttons)

        bot.sendMessage(chat_id, '頁數', reply_markup=InlineKeyboardMarkup(inline_keyboard=res_button_rows))


def createRegionKeyboard(data_root, callbacks):
    global region_button_index
    region_button_rows=[]
    region_buttons=[]
    for k,v in data_root['regions'].items():
        callback_data = 'regions-' + str(region_button_index) + '-' + k
        region_button_index=region_button_index+1
        region_name=v['name']
        if 'regions' in v:
            traverse_next_data_root = True
        else:
            traverse_next_data_root = False

        callbacks[callback_data] = \
                lambda bot, chat_id, query_id, next_data_root=v, region_name=region_name, traverse_next_data_root=traverse_next_data_root: \
                    replySelectedRegion(bot, chat_id, query_id, next_data_root, region_name, traverse_next_data_root)

        if 'restaurants' in v:
            region_buttons.append(InlineKeyboardButton(text=region_name, callback_data=callback_data))

        # every row contains up to 3 buttons
        if len(region_buttons) == 3: 
            region_button_rows.append(region_buttons)
            region_buttons = []

    if len(region_buttons) > 0:  # the last row
        region_button_rows.append(region_buttons)

    return InlineKeyboardMarkup(inline_keyboard=region_button_rows)

def loadDataAndPrepareCallbacks():
    global region_keyboard
    # load from Google Sheet if the cache has expired
    region_data = {}
    need_reload_spreadsheet=False
    if os.path.isfile('region_data.json') and os.path.isfile('restaurant_data.json'):
        if os.path.getmtime('region_data.json') < (time.time()-60*2):
            need_reload_spreadsheet=True
    else:
        need_reload_spreadsheet=True

    if not region_keyboard:
        need_reload_spreadsheet=True

    if not need_reload_spreadsheet:
        return region_keyboard

    print('Reloading region data from spreadsheet')
    region_data, restaurant_data = getDataFromSpreadsheet()
    with open('region_data.json', 'w', encoding='utf-8') as f:
        f.write(json.dumps(region_data, ensure_ascii=False))
    with open('restaurant_data.json', 'w', encoding='utf-8') as f:
        f.write(json.dumps(restaurant_data, ensure_ascii=False))

    # mark the regions that have restaurants
    def markRegionHasRestaurant(data_root):
        contains_restaurant = False
        for k,v in data_root['regions'].items():
            if 'regions' in v:
                contains_restaurant = markRegionHasRestaurant(v) or contains_restaurant
            else:
                for r in restaurant_data:
                    # print('check ' + r + ': ' + restaurant_data[r]['region'] + ' against ' + k)
                    if restaurant_data[r]['region'] == k:
                        if not 'restaurants' in v:
                            v['restaurants'] = []
                        v['restaurants'].append(restaurant_data[r])
                        contains_restaurant = True
        if contains_restaurant:
            data_root['restaurants'] = []
        return contains_restaurant
        
    markRegionHasRestaurant(region_data)

    # setup button callbacks for user to select restaurants by regions
    region_keyboard = createRegionKeyboard(region_data, region_callbacks)

#---------------------------- message handlers

def on_chat_message(msg):
    content_type, chat_type, chat_id = telepot.glance(msg)
    if content_type != 'text':
        return

    print('- - -')
    print("Message: " + str(msg))
    print("Content type: " + content_type)
    print("Chat ID:" + str(chat_id))

    txt = ''

    if 'text' in msg:
        txt = txt + msg['text']
    elif 'caption' in msg:
        txt = txt + msg['caption']

    # Addme and rmme only valid on personal chats.
    if msg['chat']['type'] != 'private':
        return

    if '/hi' == txt.strip()[:3] or '/start' == txt.strip()[:6]:
        loadDataAndPrepareCallbacks()
        bot.sendMessage(chat_id, '想喺邊一區食飯呀？', reply_markup=region_keyboard)

def on_callback_query(msg):
    query_id, from_id, callback_data = telepot.glance(msg, flavor='callback_query')
    print('Callback query:', query_id, ' from: ', from_id, callback_data)
    print('- - -')
    print("Callback: " + str(msg))

    if not region_keyboard:
        loadDataAndPrepareCallbacks()

    if callback_data in region_callbacks:
        region_callbacks[callback_data](bot, from_id, query_id)
    elif callback_data in restaurants_page_callbacks:
        restaurants_page_callbacks[callback_data]()

#---------------------------- main
if os.path.isfile('config.json'):
    with open('config.json', 'r') as f:
        config = json.load(f)
        if config['token'] == "": # The token is your Telegram bot's token
            sys.exit("No token defined. Define it in a file called config.json.")
        if config['password'] == "":
            print("WARNING: Empty Password for registering to use the bot." +
                  " It could be dangerous, because anybody could use this bot" +
                  " and forward messages to the channels associated to it")
        TOKEN = config['token']
        PASSWORD = config['password']
else:
    sys.exit("config.json is not found.")

bot = telepot.Bot(TOKEN)

print('This is me!')
print(bot.getMe())
print()

MessageLoop(bot, {'chat': on_chat_message,
                  'callback_query' : on_callback_query
                 }).run_as_thread()
print('Listening ...')
# Keep the program running.
while 1:
    time.sleep(10)
