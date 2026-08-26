import os
import asyncio
import json
import re
import time
import random
from telebot.async_telebot import AsyncTeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram import Client, filters
from pyrogram.handlers import MessageHandler
from pyrogram.errors import SessionPasswordNeeded, PhoneCodeInvalid, PasswordHashInvalid, AuthKeyUnregistered
from pyrogram.enums import ChatType

# ==========================================
# 1. إعدادات اليوزر بوت
# ==========================================
BOT_TOKEN = "8666142908:AAFZhEu_McY2TEy_6wtGbB7RhjFbxF7fTeE"
API_ID = 37129514
API_HASH = "29af008f32ddd784867118d0a58fb8c6"
PRIMARY_ADMIN_ID = 8145086924
DB_CHANNEL_ID = -1004352728061

bot = AsyncTeleBot(BOT_TOKEN)
user_states = {}
RUNNING_CLIENTS = {}
LAST_REPLY_TIME = {}

# ==========================================
# 2. نظام قاعدة البيانات السحابية
# ==========================================
DB_STATE = {
    "admins": [PRIMARY_ADMIN_ID],
    "accounts": {} 
}
DB_MESSAGE_ID = None

async def sync_from_channel():
    global DB_STATE, DB_MESSAGE_ID
    try:
        chat = await bot.get_chat(DB_CHANNEL_ID)
        if chat.pinned_message:
            DB_MESSAGE_ID = chat.pinned_message.message_id
            text = chat.pinned_message.text or chat.pinned_message.caption
            if text:
                match = re.search(r'(\{.*\})', text, re.DOTALL)
                if match:
                    try:
                        data = json.loads(match.group(1))
                        DB_STATE["admins"] = list(set(data.get("admins", []) + [PRIMARY_ADMIN_ID]))
                        
                        accounts = data.get("accounts", {})
                        for phone, info in accounts.items():
                            if isinstance(info, str):
                                accounts[phone] = {
                                    "session": info, "owner_id": PRIMARY_ADMIN_ID, "auto_save": False, 
                                    "autopost": [], "storage_chat_id": None, "storage_chat_link": None,
                                    "auto_reply": {"active": False, "msg": "", "cooldown_hours": 3}, 
                                    "cached_groups": [], "shortcuts": {}, 
                                    "exceptions": {"storage": [], "autoreply": []}, "last_replies": {}
                                }
                            else:
                                if "auto_save" not in info: info["auto_save"] = False
                                if "autopost" not in info or isinstance(info["autopost"], dict): info["autopost"] = []
                                if "storage_chat_id" not in info: info["storage_chat_id"] = None
                                if "storage_chat_link" not in info: info["storage_chat_link"] = None
                                if "auto_reply" not in info: info["auto_reply"] = {"active": False, "msg": "", "cooldown_hours": 3}
                                if "cached_groups" not in info: info["cached_groups"] = []
                                if "shortcuts" not in info: info["shortcuts"] = {}
                                if "exceptions" not in info: info["exceptions"] = {"storage": [], "autoreply": []}
                                if "last_replies" not in info: info["last_replies"] = {}
                        DB_STATE["accounts"] = accounts
                        print(f"✅ تم استرجاع {len(DB_STATE['accounts'])} حساب محفوظ.")
                        return
                    except Exception as e:
                        print(f"❌ فشل فك التشفير: {e}")
        await save_to_channel()
    except Exception as e:
        print(f"❌ خطأ قراءة القناة: {e}")
        await save_to_channel(create_new=True)

async def save_to_channel(create_new=False):
    global DB_MESSAGE_ID
    if PRIMARY_ADMIN_ID not in DB_STATE["admins"]:
        DB_STATE["admins"].append(PRIMARY_ADMIN_ID)
    payload = json.dumps(DB_STATE, indent=2, ensure_ascii=False)
    formatted_text = f"📦 **قاعدة بيانات اليوزر بوت**\n\n```json\n{payload}\n
