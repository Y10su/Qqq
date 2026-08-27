import os
import asyncio
import json
import re
import time
import random
import tempfile
from telebot.async_telebot import AsyncTeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram import Client, filters
from pyrogram.handlers import MessageHandler
from pyrogram.errors import SessionPasswordNeeded, PhoneCodeInvalid, PasswordHashInvalid, AuthKeyUnregistered, SessionRevoked
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

# سجل تتبع الرد المستمر النشط
ACTIVE_RAIDS = {}  # Format: { "phone": { "target_user_id": True/False } }

# ==========================================
# 2. نظام قاعدة البيانات السحابية الحية
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
                                    "exceptions": {"storage": [], "autoreply": []}, "last_replies": {},
                                    "raid": {"sentences": []}
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
                                if "raid" not in info: info["raid"] = {"sentences": []}
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
    formatted_text = f"📦 **قاعدة بيانات اليوزر بوت**\n\n```json\n{payload}\n```"
    try:
        if DB_MESSAGE_ID and not create_new:
            try:
                await bot.edit_message_text(formatted_text, chat_id=DB_CHANNEL_ID, message_id=DB_MESSAGE_ID, parse_mode="Markdown")
            except Exception as edit_err:
                if "message to edit not found" in str(edit_err).lower():
                    msg = await bot.send_message(DB_CHANNEL_ID, formatted_text, parse_mode="Markdown")
                    DB_MESSAGE_ID = msg.message_id
                    await bot.pin_chat_message(DB_CHANNEL_ID, msg.message_id)
        else:
            msg = await bot.send_message(DB_CHANNEL_ID, formatted_text, parse_mode="Markdown")
            DB_MESSAGE_ID = msg.message_id
            await bot.pin_chat_message(DB_CHANNEL_ID, msg.message_id)
    except Exception:
        pass

# ==========================================
# 3. أنظمة اليوزر بوت الآلية المستمرة
# ==========================================

async def fetch_account_groups(client):
    groups = []
    try:
        async for d in client.get_dialogs(limit=0):
            if d.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
                groups.append({"id": d.chat.id, "title": d.chat.title})
    except: pass
    return groups

async def create_storage_group(client):
    try:
        chat = await client.create_supergroup("مجموعة التخزين 📁", "يتم تحويل رسائل الخاص وحفظ الميديا هنا تلقائياً")
        link = chat.invite_link or await chat.export_invite_link()
        return chat.id, link
    except:
        try:
            chat = await client.create_channel("مجموعة التخزين 📁", "يتم تحويل رسائل الخاص وحفظ الميديا هنا تلقائياً")
            link = chat.invite_link or await chat.export_invite_link()
            return chat.id, link
        except: return None, None

async def download_telebot_media(message):
    file_id = None
    ext = ".tmp"
    if message.photo: file_id = message.photo[-1].file_id; ext = ".jpg"
    elif message.video: file_id = message.video.file_id; ext = ".mp4"
    elif message.voice: file_id = message.voice.file_id; ext = ".ogg"
    elif message.audio: file_id = message.audio.file_id; ext = ".mp3"
    elif message.document: file_id = message.document.file_id; ext = getattr(message.document, "file_name", ".tmp")
    elif message.video_note: file_id = message.video_note.file_id; ext = ".mp4"
    
    if not file_id: return None
    file_info = await bot.get_file(file_id)
    downloaded_file = await bot.download_file(file_info.file_path)
    tmp_dir = tempfile.gettempdir()
    path = os.path.join(tmp_dir, f"temp_media_{int(time.time())}_{random.randint(1000,9999)}{ext}")
    with open(path, 'wb') as new_file:
        new_file.write(downloaded_file)
    return path

# ====== مهمة الرد المستمر ======
async def raid_worker(client, phone, chat_id, target_msg_id, target_user_id, sentences):
    while ACTIVE_RAIDS.get(phone, {}).get(target_user_id):
        for sentence in sentences:
            if not ACTIVE_RAIDS.get(phone, {}).get(target_user_id):
                break  # خروج فوري إذا تم إيقافه
            try:
                await client.send_message(chat_id, sentence, reply_to_message_id=target_msg_id)
                # تأخير عشوائي للحماية من الحظر
                await asyncio.sleep(random.uniform(2.0, 3.5)) 
            except Exception as e:
                # إذا قام الشخص بحذف رسالته، نرسل بدون ريبلاي
                if "MESSAGE_ID_INVALID" in str(e).upper():
                    try:
                        await client.send_message(chat_id, sentence)
                        await asyncio.sleep(random.uniform(2.0, 3.5))
                    except: pass
                else:
                    await asyncio.sleep(3)

# ====== معالج الرد المستمر ======
async def handle_continuous_reply(client, message):
    phone = getattr(client, "acc_phone", None)
    if not phone or not message.text: return
    
    text = message.text.strip()
    if text not in [".ضرب", ".ايقاف"]:
        return

    raid_config = DB_STATE["accounts"].get(phone, {}).get("raid", {})
    sentences = raid_config.get("sentences", [])
    
    target_user = message.reply_to_message.from_user if message.reply_to_message else None
    if not target_user: return
    
    target_id = target_user.id

    # تشغيل الرد المستمر
    if text == ".ضرب":
        if not sentences:
            await message.edit_text("❌ لم تقم بإضافة أي جمل للرد المستمر من إعدادات البوت!")
            return
            
        if phone not in ACTIVE_RAIDS: ACTIVE_RAIDS[phone] = {}
        
        if ACTIVE_RAIDS[phone].get(target_id):
            await message.edit_text("⚠️ الرد المستمر شغال بالفعل على هذا الشخص!")
            return
            
        ACTIVE_RAIDS[phone][target_id] = True
        await message.delete() 
        asyncio.create_task(raid_worker(client, phone, message.chat.id, message.reply_to_message.id, target_id, sentences))

    # إيقاف الرد المستمر
    elif text == ".ايقاف":
        if phone in ACTIVE_RAIDS and ACTIVE_RAIDS[phone].get(target_id):
            ACTIVE_RAIDS[phone][target_id] = False
            await message.edit_text("🛑 تم إيقاف الرد المستمر عن هذا الشخص.")
            await asyncio.sleep(2)
            await message.delete()

# ====== الاختصارات ======
async def handle_user_shortcuts(client, message):
    phone = getattr(client, "acc_phone", None)
    if not phone or not message.text: return
    
    shortcuts = DB_STATE["accounts"].get(phone, {}).get("shortcuts", {})
    text = message.text.strip()
    
    if text in shortcuts:
        shortcut = shortcuts[text]
        try:
            if shortcut["type"] == "text":
                await message.edit_text(shortcut["text"])
            elif shortcut["type"] == "media":
                await message.delete()
                chat_id = shortcut.get("chat_id", "me")
                chat_id = int(chat_id) if str(chat_id).lstrip('-').isdigit() else chat_id
                storage_link = DB_STATE["accounts"].get(phone, {}).get("storage_chat_link")
                if storage_link:
                    try: await client.join_chat(storage_link)
                    except: pass
                await client.copy_message(message.chat.id, chat_id, shortcut["msg_id"])
        except Exception: pass

# ====== معالج الخاص والذاتية ======
async def handle_private_messages(client, message):
    phone = getattr(client, "acc_phone", None)
    if not phone: return
    acc_info = DB_STATE["accounts"].get(phone, {})
    
    my_id = getattr(client, "my_id", None)
    user = message.from_user
    if not user: return

    user_id_str = str(user.id)
    username = f"@{user.username.lower()}" if user.username else ""
    exceptions = acc_info.get("exceptions", {"storage": [], "autoreply": []})
    
    is_storage_exc = False
    if user_id_str in exceptions["storage"] or (username and username in exceptions["storage"]):
        is_storage_exc = True
        
    is_reply_exc = False
    if user.id == my_id or user.is_bot: 
        is_reply_exc = True
    elif user_id_str in exceptions["autoreply"] or (username and username in exceptions["autoreply"]):
        is_reply_exc = True

    is_ttl = bool(message.ttl_seconds)

    if is_ttl and acc_info.get("auto_save"):
        path = None
        for attempt in range(3): 
            try:
                path = await message.download()
                if path and os.path.exists(path):
                    sender_name = user.first_name if user else "مجهول"
                    caption = f"🤫 **تم صيد رسالة ذاتية التدمير!**\nالمرسل: {sender_name}"
                    if message.photo: await client.send_photo("me", path, caption=caption)
                    elif message.video: await client.send_video("me", path, caption=caption)
                    elif message.voice: await client.send_voice("me", path, caption=caption)
                    elif message.video_note: await client.send_video_note("me", path)
                    else: await client.send_document("me", path, caption=caption)
                    break
                else: await asyncio.sleep(1)
            except Exception: await asyncio.sleep(1)
            finally:
                if path and os.path.exists(path):
                    try: os.remove(path)
                    except: pass

    storage_id = acc_info.get("storage_chat_id")
    if storage_id and not is_ttl and not is_storage_exc:
        try:
            await message.forward(int(storage_id))
        except:
            link = acc_info.get("storage_chat_link")
            if link:
                try: 
                    await client.join_chat(link)
                    await message.forward(int(storage_id))
                except: pass

    auto_reply = acc_info.get("auto_reply", {})
    if auto_reply.get("active") and auto_reply.get("msg") and not is_reply_exc and not is_ttl:
        cooldown_sec = auto_reply.get("cooldown_hours", 3) * 3600
        last_replies = acc_info.get("last_replies", {})
        last_time = last_replies.get(user_id_str, 0)
        current_time = time.time()
        
        if (current_time - last_time) >= cooldown_sec:
            try:
                await client.send_message(user.id, auto_reply["msg"])
                DB_STATE["accounts"][phone]["last_replies"][user_id_str] = current_time 
                asyncio.create_task(save_to_channel())  
            except: pass

# ====== مهام النشر التلقائي ======
async def run_single_autopost(phone, idx, task):
    while True:
        acc = DB_STATE["accounts"].get(phone)
        if not acc: break
        tasks = acc.get("autopost", [])
        if idx >= len(tasks): break
        current_task = tasks[idx]
        if not current_task.get("active"): break 

        interval = current_task.get("interval", 60)
        await asyncio.sleep(interval * 60) 

        acc = DB_STATE["accounts"].get(phone)
        if not acc: break
        tasks = acc.get("autopost", [])
        if idx >= len(tasks): break
        current_task = tasks[idx]
        if not current_task.get("active"): break

        client = RUNNING_CLIENTS.get(phone)
        if not client: continue

        targets = current_task.get("targets", [])
        msg = current_task.get("msg")
        for target in targets:
            try:
                await client.send_message(target, msg)
                await asyncio.sleep(random.randint(5, 15))
            except Exception: await asyncio.sleep(10)
            
        if phone in DB_STATE["accounts"] and idx < len(DB_STATE["accounts"][phone]["autopost"]):
            DB_STATE["accounts"][phone]["autopost"][idx]["last_sent"] = time.time()
            asyncio.create_task(save_to_channel())

async def autopost_worker():
    while True:
        await asyncio.sleep(300)

async def start_single_client(phone, info):
    try:
        session = info.get("session")
        if not session: return
        client = Client(
            f"acc_{phone}",
            session_string=session,
            in_memory=True
        )
        client.acc_phone = phone
        
        # توزيع المهام بصلاحيات منفصلة لتجنب التداخل
        client.add_handler(MessageHandler(handle_private_messages, filters.private & filters.incoming), group=1)
        client.add_handler(MessageHandler(handle_user_shortcuts, filters.me & filters.text), group=2)
        client.add_handler(MessageHandler(handle_continuous_reply, filters.me & filters.reply & filters.text), group=3)
        
        await client.start()
        client.my_id = (await client.get_me()).id
        RUNNING_CLIENTS[phone] = client
        print(f"✅ الحساب {phone} متصل وجاهز.")

        tasks = info.get("autopost", [])
        for idx, task in enumerate(tasks):
            if task.get("active"):
                asyncio.create_task(run_single_autopost(phone, idx, task))
    except (AuthKeyUnregistered, SessionRevoked):
        print(f"⚠️ الجلسة منتهية للحساب {phone}، سيتم حذفه تلقائياً.")
        DB_STATE["accounts"].pop(phone, None)
        await save_to_channel()
    except Exception as e:
        print(f"❌ فشل تشغيل {phone}: {e}")

async def start_active_sessions():
    for phone, info in list(DB_STATE["accounts"].items()):
        if phone not in RUNNING_CLIENTS:
            await start_single_client(phone, info)

# ==========================================
# 5. لوحة التحكم والإدارة
# ==========================================
@bot.message_handler(commands=['format_db'])
async def format_db_cmd(message):
    if message.chat.id == PRIMARY_ADMIN_ID:
        global DB_STATE, DB_MESSAGE_ID
        await bot.reply_to(message, "⏳ جاري مسح القاعدة وتسجيل الخروج...")
        for phone, client in list(RUNNING_CLIENTS.items()):
            try: await client.log_out()
            except: 
                try: await client.stop()
                except: pass
        RUNNING_CLIENTS.clear()
        DB_STATE = {"admins": [PRIMARY_ADMIN_ID], "accounts": {}}
        try:
            chat = await bot.get_chat(DB_CHANNEL_ID)
            if chat.pinned_message:
                await bot.delete_message(DB_CHANNEL_ID, chat.pinned_message.message_id)
        except: pass
        DB_MESSAGE_ID = None
        await save_to_channel(create_new=True)
        await bot.reply_to(message, "🗑 تمت فرمتة القاعدة وتسجيل الخروج من جميع الحسابات.")

@bot.message_handler(commands=['start'])
async def start_cmd(message):
    user_id = message.chat.id
    if user_id not in DB_STATE["admins"]: return

    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("➕ إضافة حساب", callback_data="add_account"),
        InlineKeyboardButton("📱 حساباتي المرتبطة", callback_data="my_accounts")
    )
    if user_id == PRIMARY_ADMIN_ID:
        markup.add(InlineKeyboardButton("👥 إدارة الإدمنية", callback_data="manage_admins"))
    
    owned = sum(1 for acc in DB_STATE["accounts"].values() if acc["owner_id"] == user_id)
    await bot.send_message(
        user_id,
        f"👋 **أهلاً بك في لوحة تحكم اليوزر بوت المتقدمة**\n\n📱 حساباتك المرتبطة: **{owned}**",
        reply_markup=markup, parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.message.chat.id in DB_STATE["admins"])
async def callbacks(call):
    user_id = call.message.chat.id
    data = call.data

    if data == "add_account":
        user_states[user_id] = {"step": "phone"}
        await bot.send_message(user_id, "📱 أرسل رقم الحساب مع المفتاح الدولي (مثال: `+9665...`):\n(لإلغاء العملية أرسل `الغاء`)", parse_mode="Markdown")
        await bot.answer_callback_query(call.id)
        
    elif data == "my_accounts":
        markup = InlineKeyboardMarkup()
        owned = [phone for phone, info in DB_STATE["accounts"].items() if info["owner_id"] == user_id]
        for phone in owned:
            markup.add(InlineKeyboardButton(f"📱 {phone}", callback_data=f"panel_{phone}"))
        await bot.edit_message_text("👇 **حساباتك المرتبطة:**", chat_id=user_id, message_id=call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    elif data.startswith("panel_"):
        phone = data.split("_")[1]
        client = RUNNING_CLIENTS.get(phone)
        if client:
            try:
                await client.get_me()
            except (AuthKeyUnregistered, SessionRevoked):
                DB_STATE["accounts"].pop(phone, None)
                RUNNING_CLIENTS.pop(phone, None)
                await save_to_channel()
                await bot.answer_callback_query(call.id, "❌ تم تسجيل الخروج من هذا الحساب من مكان آخر! تم حذفه من النظام.", show_alert=True)
                call.data = "my_accounts"
                await callbacks(call)
                return
            except Exception: pass
        
        acc_info = DB_STATE["accounts"].get(phone, {})
        save_status = "✅ مفعل" if acc_info.get("auto_save") else "❌ معطل"
        reply_status = "✅ مفعل" if acc_info.get("auto_reply", {}).get("active") else "❌ معطل"
        storage_status = "✅ مرتبطة" if acc_info.get("storage_chat_id") else "❌ غير مرتبطة"
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(f"📥 حفظ الذاتية: {save_status}", callback_data=f"autosave_{phone}"))
        markup.add(InlineKeyboardButton(f"🔄 مهام النشر", callback_data=f"autopost_{phone}"), InlineKeyboardButton(f"⚡ الاختصارات", callback_data=f"shortcuts_{phone}"))
        markup.add(InlineKeyboardButton("⚔️ الرد المستمر", callback_data=f"raid_{phone}"))
        markup.add(InlineKeyboardButton(f"💬 الرد التلقائي: {reply_status}", callback_data=f"autoreply_toggle_{phone}"), InlineKeyboardButton("⚙️ إعداد الرد", callback_data=f"autoreply_setup_{phone}"))
        markup.add(InlineKeyboardButton("🛡 إدارة الاستثناءات", callback_data=f"exceptions_{phone}"), InlineKeyboardButton(f"🛠 مجموعة التخزين: {storage_status}", callback_data=f"fixstorage_{phone}"))
        markup.add(InlineKeyboardButton("🔗 انضمام لقناة", callback_data=f"join_{phone}"), InlineKeyboardButton("✍️ النبذة", callback_data=f"bio_{phone}"))
        markup.add(InlineKeyboardButton("🗑 حذف وتسجيل خروج", callback_data=f"delete_{phone}"), InlineKeyboardButton("🔙 رجوع", callback_data="my_accounts"))
        
        await bot.edit_message_text(f"⚙️ **تحكم حساب: `{phone}`**", chat_id=user_id, message_id=call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    # --- إعدادات الرد المستمر ---
    elif data.startswith("raid_"):
        phone = data.split("_")[1]
        raid_data = DB_STATE["accounts"][phone].get("raid", {"sentences": []})
        sentences_count = len(raid_data.get("sentences", []))
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("➕ إضافة جمل", callback_data=f"addrds_{phone}"))
        if sentences_count > 0:
            markup.add(InlineKeyboardButton("🗑 مسح كل الجمل", callback_data=f"clrrds_{phone}"))
        markup.add(InlineKeyboardButton("🔙 رجوع للحساب", callback_data=f"panel_{phone}"))
        
        msg_text = (
            f"⚔️ **إعدادات الرد المستمر - `{phone}`**\n\n"
            f"عدد الجمل المحفوظة: **{sentences_count}**\n\n"
            f"🔹 **طريقة الاستخدام:**\n"
            f"في أي محادثة، رد على رسالة الشخص واكتب: `.ضرب`\n"
            f"لإيقاف الرد المستمر، رد عليه واكتب: `.ايقاف`\n\n"
            f"*(ملاحظة: البوت سيرسل الجمل بالترتيب مع توقف زمني بسيط لحماية حسابك من الباند)*"
        )
        await bot.edit_message_text(msg_text, chat_id=user_id, message_id=call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    elif data.startswith("addrds_"):
        phone = data.split("_")[1]
        user_states[user_id] = {"step": "add_raid_sentences", "phone": phone}
        await bot.send_message(user_id, "✍️ **أرسل الجمل الآن:**\n(إذا كانت أكثر من جملة، ضع كل جملة في سطر منفصل)\n\nلإلغاء العملية أرسل `الغاء`", parse_mode="Markdown")
        await bot.answer_callback_query(call.id)

    elif data.startswith("clrrds_"):
        phone = data.split("_")[1]
        DB_STATE["accounts"][phone]["raid"]["sentences"] = []
        await save_to_channel()
        await bot.answer_callback_query(call.id, "✅ تم مسح جميع جمل الرد المستمر بنجاح!", show_alert=True)
        call.data = f"raid_{phone}"
        await callbacks(call)

    elif data.startswith("fixstorage_"):
        phone = data.split("_")[1]
        client = RUNNING_CLIENTS.get(phone)
        if not client:
            await bot.answer_callback_query(call.id, "الحساب غير متصل حالياً!", show_alert=True)
            return

        storage_id = DB_STATE["accounts"][phone].get("storage_chat_id")
        storage_link = DB_STATE["accounts"][phone].get("storage_chat_link")
        
        if storage_id:
            try:
                if storage_link:
                    try: await client.join_chat(storage_link)
                    except: pass
                else:
                    async for _ in client.get_dialogs(limit=100): pass
                    
                await client.get_chat(int(storage_id))
                if not storage_link:
                    try:
                        link = (await client.get_chat(int(storage_id))).invite_link or await (await client.get_chat(int(storage_id))).export_invite_link()
                        DB_STATE["accounts"][phone]["storage_chat_link"] = link
                        await save_to_channel()
                    except: pass
                    
                await bot.answer_callback_query(call.id, "✅ مجموعة التخزين موجودة ومسجلة في القاعدة وتعمل بشكل سليم!", show_alert=True)
                return
            except Exception: pass 

        await bot.answer_callback_query(call.id, "⏳ جاري إنشاء المجموعة...")
        storage_id, link = await create_storage_group(client)
        if storage_id:
            DB_STATE["accounts"][phone]["storage_chat_id"] = storage_id
            DB_STATE["accounts"][phone]["storage_chat_link"] = link
            await save_to_channel()
            await bot.send_message(user_id, f"✅ تم إنشاء مجموعة التخزين بنجاح وتم حفظ الآيدي بالقاعدة!\n🔗 الرابط: {link}\n*(لا تقم بحذفها)*", parse_mode="Markdown")
        else:
            await bot.send_message(user_id, "❌ فشل إنشاء مجموعة التخزين.")

    elif data.startswith("autosave_"):
        phone = data.split("_")[1]
        current_status = DB_STATE["accounts"][phone].get("auto_save", False)
        DB_STATE["accounts"][phone]["auto_save"] = not current_status
        await save_to_channel()
        call.data = f"panel_{phone}"
        await callbacks(call)

    # --- إدارة الاستثناءات (قوائم) ---
    elif data.startswith("exceptions_"):
        phone = data.split("_")[1]
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🛡 مستثنيين التخزين", callback_data=f"exc_menu_{phone}_storage"))
        markup.add(InlineKeyboardButton("💬 مستثنيين الرد التلقائي", callback_data=f"exc_menu_{phone}_autoreply"))
        markup.add(InlineKeyboardButton("🔙 رجوع للحساب", callback_data=f"panel_{phone}"))
        await bot.edit_message_text(f"🛡 **إدارة الاستثناءات - `{phone}`**\nالرجاء اختيار القائمة التي تريد إدارتها:", chat_id=user_id, message_id=call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    elif data.startswith("exc_menu_"):
        parts = data.split("_")
        phone = parts[2]
        exc_type = parts[3]
        exceptions_list = DB_STATE["accounts"][phone]["exceptions"].get(exc_type, [])
        
        markup = InlineKeyboardMarkup()
        for exc in exceptions_list:
            markup.add(InlineKeyboardButton(f"🗑 حذف: {exc}", callback_data=f"delexc_{phone}_{exc_type}_{exc}"))
            
        markup.add(InlineKeyboardButton("➕ إضافة شخص للقائمة", callback_data=f"addexc_{phone}_{exc_type}"))
        markup.add(InlineKeyboardButton("🔙 رجوع", callback_data=f"exceptions_{phone}"))
        
        title = "تحويل رسائل التخزين" if exc_type == "storage" else "الرد التلقائي"
        await bot.edit_message_text(f"🛡 **قائمة المستثنيين من {title}:**\nانقر على الشخص لإزالته من الاستثناء:", chat_id=user_id, message_id=call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    elif data.startswith("delexc_"):
        parts = data.split("_")
        phone = parts[1]
        exc_type = parts[2]
        target = parts[3]
        if target in DB_STATE["accounts"][phone]["exceptions"][exc_type]:
            DB_STATE["accounts"][phone]["exceptions"][exc_type].remove(target)
            await save_to_channel()
        call.data = f"exc_menu_{phone}_{exc_type}"
        await callbacks(call)

    elif data.startswith("addexc_"):
        parts = data.split("_")
        phone = parts[1]
        exc_type = parts[2]
        user_states[user_id] = {"step": "add_exception", "phone": phone, "exc_type": exc_type}
        await bot.send_message(user_id, "✍️ **أرسل الآي دي (ID) أو المعرف (كمثال `@username`):**\nلإلغاء العملية أرسل `الغاء`", parse_mode="Markdown")
        await bot.answer_callback_query(call.id)

    # --- إدارة الاختصارات ---
    elif data.startswith("shortcuts_"):
        phone = data.split("_")[1]
        shortcuts = DB_STATE["accounts"][phone].get("shortcuts", {})
        markup = InlineKeyboardMarkup()
        for kw in shortcuts:
            markup.add(InlineKeyboardButton(f"🗑 حذف: {kw}", callback_data=f"delshort_{phone}_{kw}"))
        markup.add(InlineKeyboardButton("➕ إضافة اختصار جديد", callback_data=f"newshort_{phone}"))
        markup.add(InlineKeyboardButton("🔙 رجوع للحساب", callback_data=f"panel_{phone}"))
        await bot.edit_message_text(f"⚡ **إدارة الاختصارات (الاستبدال) - `{phone}`**\nإذا كتبت الكلمة في أي محادثة، سيتم استبدالها فوراً بنص أو ميديا:", chat_id=user_id, message_id=call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    elif data.startswith("delshort_"):
        parts = data.split("_")
        phone = parts[1]
        kw = parts[2]
        if kw in DB_STATE["accounts"][phone]["shortcuts"]:
            del DB_STATE["accounts"][phone]["shortcuts"][kw]
            await save_to_channel()
        call.data = f"shortcuts_{phone}"
        await callbacks(call)

    elif data.startswith("newshort_"):
        phone = data.split("_")[1]
        user_states[user_id] = {"step": "shortcut_kw", "phone": phone}
        await bot.send_message(user_id, "✍️ **أرسل الكلمة المفتاحية:**\n(مثال: `حساب`)\nلإلغاء العملية أرسل `الغاء`", parse_mode="Markdown")
        await bot.answer_callback_query(call.id)

    # --- إدارة الرد التلقائي ---
    elif data.startswith("autoreply_toggle_"):
        phone = data.split("_")[2]
        current_status = DB_STATE["accounts"][phone]["auto_reply"]["active"]
        if not current_status and not DB_STATE["accounts"][phone]["auto_reply"].get("msg"):
            await bot.answer_callback_query(call.id, "❌ يجب إعداد رسالة الرد أولاً من الإعدادات!", show_alert=True)
            return
        DB_STATE["accounts"][phone]["auto_reply"]["active"] = not current_status
        await save_to_channel()
        call.data = f"panel_{phone}"
        await callbacks(call)

    elif data.startswith("autoreply_setup_"):
        phone = data.split("_")[2]
        user_states[user_id] = {"step": "autoreply_msg", "phone": phone}
        await bot.send_message(user_id, "💬 **أرسل النص الذي تريده للرد التلقائي:**\nلإلغاء العملية أرسل `الغاء`", parse_mode="Markdown")
        await bot.answer_callback_query(call.id)

    # --- إدارة النشر التلقائي ---
    elif data.startswith("autopost_"):
        phone = data.split("_")[1]
        tasks = DB_STATE["accounts"][phone].get("autopost", [])
        markup = InlineKeyboardMarkup()
        
        for i, task in enumerate(tasks):
            status = "✅" if task.get("active") else "❌"
            targets_count = len(task.get("targets", []))
            markup.add(InlineKeyboardButton(f"{status} مهمة {i+1} ({targets_count} قروبات) - كل {task['interval']}د", callback_data=f"togglepost_{phone}_{i}"))
            markup.add(
                InlineKeyboardButton(f"⚙️ تعديل القروبات", callback_data=f"edittgts_{phone}_{i}_0"),
                InlineKeyboardButton(f"🗑 حذف", callback_data=f"delpost_{phone}_{i}")
            )
            
        markup.add(InlineKeyboardButton("➕ إضافة رسالة جديدة للنشر", callback_data=f"newpost_{phone}"))
        markup.add(InlineKeyboardButton("🔙 رجوع للحساب", callback_data=f"panel_{phone}"))
        
        await bot.edit_message_text(f"🔄 **إدارة مهام النشر التلقائي - `{phone}`**\nيمكنك تخصيص القروبات لكل رسالة بشكل مستقل:", chat_id=user_id, message_id=call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    elif data.startswith("togglepost_"):
        _, phone, idx = data.split("_")
        idx = int(idx)
        current = DB_STATE["accounts"][phone]["autopost"][idx]["active"]
        DB_STATE["accounts"][phone]["autopost"][idx]["active"] = not current
        await save_to_channel()
        if DB_STATE["accounts"][phone]["autopost"][idx]["active"]:
            asyncio.create_task(run_single_autopost(phone, idx, DB_STATE["accounts"][phone]["autopost"][idx]))
        call.data = f"autopost_{phone}"
        await callbacks(call)

    elif data.startswith("delpost_"):
        _, phone, idx = data.split("_")
        idx = int(idx)
        DB_STATE["accounts"][phone]["autopost"].pop(idx)
        await save_to_channel()
        call.data = f"autopost_{phone}"
        await callbacks(call)

    elif data.startswith("newpost_"):
        phone = data.split("_")[1]
        user_states[user_id] = {"step": "post_msg", "phone": phone}
        await bot.send_message(user_id, "✍️ **أرسل الآن الرسالة (النص) التي تريد نشرها:**\nلإلغاء العملية أرسل `الغاء`", parse_mode="Markdown")
        await bot.answer_callback_query(call.id)

    # --- واجهة اختيار القروبات ---
    elif data.startswith("edittgts_"):
        parts = data.split("_")
        phone = parts[1]
        idx = int(parts[2])
        page = int(parts[3])
        
        client = RUNNING_CLIENTS.get(phone)
        if not client:
            await bot.answer_callback_query(call.id, "الحساب غير متصل حالياً!", show_alert=True)
            return

        acc = DB_STATE["accounts"][phone]
        if not acc.get("cached_groups"):
            await bot.answer_callback_query(call.id, "⏳ جاري استخراج القروبات، انتظر ثواني...")
            acc["cached_groups"] = await fetch_account_groups(client)
            await save_to_channel()

        groups = acc["cached_groups"]
        task = acc["autopost"][idx]
        targets = task.get("targets", [])

        PER_PAGE = 10
        start = page * PER_PAGE
        end = start + PER_PAGE
        current_groups = groups[start:end]

        markup = InlineKeyboardMarkup()
        for g in current_groups:
            is_selected = g["id"] in targets
            mark = "✅" if is_selected else "❌"
            title = g["title"][:30]
            markup.add(InlineKeyboardButton(f"{mark} {title}", callback_data=f"tgttgl_{phone}_{idx}_{g['id']}_{page}"))

        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"edittgts_{phone}_{idx}_{page-1}"))
        if end < len(groups):
            nav_buttons.append(InlineKeyboardButton("التالي ➡️", callback_data=f"edittgts_{phone}_{idx}_{page+1}"))
        if nav_buttons:
            markup.add(*nav_buttons)

        markup.add(InlineKeyboardButton("🔄 تحديث قائمة القروبات", callback_data=f"refreshtgts_{phone}_{idx}_{page}"))
        markup.add(InlineKeyboardButton("✅ حفظ التعديلات", callback_data=f"autopost_{phone}"))

        await bot.edit_message_text(f"🎯 **اختر القروبات للمهمة {idx+1}:**\nاضغط على القروب لتفعيله/إلغائه:", chat_id=user_id, message_id=call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    elif data.startswith("tgttgl_"):
        parts = data.split("_")
        phone = parts[1]
        idx = int(parts[2])
        chat_id = int(parts[3])
        page = int(parts[4])

        task = DB_STATE["accounts"][phone]["autopost"][idx]
        if chat_id in task["targets"]:
            task["targets"].remove(chat_id)
        else:
            task["targets"].append(chat_id)

        await save_to_channel()
        call.data = f"edittgts_{phone}_{idx}_{page}"
        await callbacks(call)

    elif data.startswith("refreshtgts_"):
        parts = data.split("_")
        phone = parts[1]
        idx = int(parts[2])
        page = int(parts[3])
        client = RUNNING_CLIENTS.get(phone)
        await bot.answer_callback_query(call.id, "⏳ جاري التحديث من سيرفرات تليجرام...")
        DB_STATE["accounts"][phone]["cached_groups"] = await fetch_account_groups(client)
        await save_to_channel()
        call.data = f"edittgts_{phone}_{idx}_{page}"
        await callbacks(call)

    # --- بقية الأوامر ---
    elif data.startswith("bio_"):
        phone = data.split("_")[1]
        user_states[user_id] = {"step": "wait_bio", "phone": phone}
        await bot.send_message(user_id, "✍️ أرسل النبذة (Bio) الجديدة الآن:\nلإلغاء العملية أرسل `الغاء`", parse_mode="Markdown")
        await bot.answer_callback_query(call.id)

    elif data.startswith("join_"):
        phone = data.split("_")[1]
        user_states[user_id] = {"step": "wait_link", "phone": phone}
        await bot.send_message(user_id, "🔗 أرسل رابط القناة أو الجروب:\nلإلغاء العملية أرسل `الغاء`", parse_mode="Markdown")
        await bot.answer_callback_query(call.id)
        
    elif data.startswith("delete_"):
        phone = data.split("_")[1]
        client = RUNNING_CLIENTS.get(phone)
        if client:
            try: await client.log_out()
            except: 
                try: await client.stop()
                except: pass
            RUNNING_CLIENTS.pop(phone, None)
        DB_STATE["accounts"].pop(phone, None)
        await save_to_channel()
        await bot.answer_callback_query(call.id, "✅ تم الحذف وتسجيل الخروج بنجاح.", show_alert=True)
        await bot.edit_message_text("✅ تم الحذف وتسجيل الخروج من الحساب بنجاح.", chat_id=user_id, message_id=call.message.message_id)

    # --- إدارة الإدمنية ---
    elif data == "manage_admins" and user_id == PRIMARY_ADMIN_ID:
        markup = InlineKeyboardMarkup()
        for ad_id in DB_STATE["admins"]:
            if ad_id != PRIMARY_ADMIN_ID:
                markup.add(InlineKeyboardButton(f"👤 {ad_id}", callback_data=f"none"), InlineKeyboardButton("🗑 حذف", callback_data=f"remove_admin_{ad_id}"))
        markup.add(InlineKeyboardButton("➕ إضافة أدمن جديد", callback_data="add_admin"))
        markup.add(InlineKeyboardButton("🔙 رجوع", callback_data="back_main"))
        await bot.edit_message_text("👥 **قائمة الإدمنية الحاليين:**", chat_id=user_id, message_id=call.message.message_id, reply_markup=markup, parse_mode="Markdown")
        
    elif data == "add_admin" and user_id == PRIMARY_ADMIN_ID:
        user_states[user_id] = {"step": "add_admin_id"}
        await bot.send_message(user_id, "👥 أرسل الآي دي (ID) الخاص بالأدمن الجديد:\nلإلغاء العملية أرسل `الغاء`", parse_mode="Markdown")
        await bot.answer_callback_query(call.id)
        
    elif data.startswith("remove_admin_") and user_id == PRIMARY_ADMIN_ID:
        target = int(data.split("_")[2])
        if target in DB_STATE["admins"]:
            DB_STATE["admins"].remove(target)
            await save_to_channel()
            call.data = "manage_admins"
            await callbacks(call)
            
    elif data == "back_main":
        await start_cmd(call.message)

@bot.message_handler(content_types=['text', 'photo', 'video', 'voice', 'document', 'audio', 'video_note'])
async def handle_inputs(message):
    user_id = message.chat.id
    
    if message.text and message.text.strip() == "الغاء":
        if user_id in user_states:
            user_states.pop(user_id, None)
            await bot.reply_to(message, "🚫 **تم إلغاء العملية بنجاح.**", parse_mode="Markdown")
        return

    if user_id not in DB_STATE["admins"] or user_id not in user_states:
        return

    state = user_states[user_id]
    step = state.get("step")

    # --- إضافة الرد المستمر ---
    if step == "add_raid_sentences":
        phone = state["phone"]
        text = message.text
        if not text:
            await bot.reply_to(message, "❌ أرسل نصاً فقط.")
            return
            
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        DB_STATE["accounts"][phone]["raid"]["sentences"].extend(lines)
        await save_to_channel()
        user_states.pop(user_id, None)
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔙 رجوع لإعدادات الرد المستمر", callback_data=f"raid_{phone}"))
        await bot.reply_to(message, f"✅ تم إضافة **{len(lines)}** جمل بنجاح!", reply_markup=markup, parse_mode="Markdown")

    # --- إضافة الاستثناءات ---
    elif step == "add_exception":
        phone = state["phone"]
        exc_type = state["exc_type"]
        target = message.text.strip().lower()
        if not target.startswith("@") and not target.isdigit():
            target = f"@{target}"
        target_str = str(target)
        if target_str not in DB_STATE["accounts"][phone]["exceptions"][exc_type]:
            DB_STATE["accounts"][phone]["exceptions"][exc_type].append(target_str)
            await save_to_channel()
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🔙 رجوع للقائمة", callback_data=f"exc_menu_{phone}_{exc_type}"))
            await bot.reply_to(message, f"✅ تم إضافة `{target_str}` إلى قائمة الاستثناءات بنجاح!", reply_markup=markup, parse_mode="Markdown")
        else:
            await bot.reply_to(message, f"⚠️ الشخص `{target_str}` موجود بالفعل في القائمة.")
        user_states.pop(user_id, None)

    # --- إضافة الاختصارات ---
    elif step == "shortcut_kw":
        kw = message.text.strip()
        state["keyword"] = kw
        state["step"] = "shortcut_media"
        await bot.reply_to(message, f"✅ حسناً، الكلمة هي `{kw}`.\n\nأرسل الآن ما تريد أن يتم استبداله بها (صورة، فيديو، بصمة صوت، ملف، أو حتى نص طويل):", parse_mode="Markdown")

    elif step == "shortcut_media":
        phone = state["phone"]
        kw = state["keyword"]
        client = RUNNING_CLIENTS.get(phone)
        
        if message.content_type == 'text':
            DB_STATE["accounts"][phone]["shortcuts"][kw] = {"type": "text", "text": message.text}
            await save_to_channel()
            user_states.pop(user_id, None)
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🔙 رجوع للاختصارات", callback_data=f"shortcuts_{phone}"))
            await bot.reply_to(message, f"✅ تم حفظ الاختصار النصي للكلمة: `{kw}`", reply_markup=markup, parse_mode="Markdown")
        else:
            if not client:
                await bot.reply_to(message, "❌ الحساب غير متصل حالياً لحفظ الميديا.")
                return
            await bot.reply_to(message, "⏳ جاري الرفع إلى مجموعة التخزين كقاعدة بيانات، يرجى الانتظار...")
            path = await download_telebot_media(message)
            if path:
                try:
                    caption = message.caption or ""
                    storage_chat_id = DB_STATE["accounts"][phone].get("storage_chat_id")
                    if storage_chat_id:
                        storage_link = DB_STATE["accounts"][phone].get("storage_chat_link")
                        if storage_link:
                            try: await client.join_chat(storage_link)
                            except: pass
                    else:
                        storage_chat_id = "me"
                    if message.photo: msg_s = await client.send_photo(int(storage_chat_id) if str(storage_chat_id).lstrip('-').isdigit() else storage_chat_id, path, caption=caption)
                    elif message.video: msg_s = await client.send_video(int(storage_chat_id) if str(storage_chat_id).lstrip('-').isdigit() else storage_chat_id, path, caption=caption)
                    elif message.voice: msg_s = await client.send_voice(int(storage_chat_id) if str(storage_chat_id).lstrip('-').isdigit() else storage_chat_id, path, caption=caption)
                    elif message.document: msg_s = await client.send_document(int(storage_chat_id) if str(storage_chat_id).lstrip('-').isdigit() else storage_chat_id, path, caption=caption)
                    elif message.audio: msg_s = await client.send_audio(int(storage_chat_id) if str(storage_chat_id).lstrip('-').isdigit() else storage_chat_id, path, caption=caption)
                    elif message.video_note: msg_s = await client.send_video_note(int(storage_chat_id) if str(storage_chat_id).lstrip('-').isdigit() else storage_chat_id, path)
                        
                    DB_STATE["accounts"][phone]["shortcuts"][kw] = {"type": "media", "msg_id": msg_s.id, "chat_id": storage_chat_id}
                    await save_to_channel()
                    user_states.pop(user_id, None)
                    markup = InlineKeyboardMarkup()
                    markup.add(InlineKeyboardButton("🔙 رجوع للاختصارات", callback_data=f"shortcuts_{phone}"))
                    await bot.reply_to(message, f"✅ تم حفظ اختصار الميديا للكلمة: `{kw}`", reply_markup=markup, parse_mode="Markdown")
                except Exception as e:
                    await bot.reply_to(message, f"❌ خطأ في الرفع (تأكد من إعداد مجموعة التخزين أولاً): {e}")
                finally:
                    if os.path.exists(path):
                        os.remove(path)
            else:
                await bot.reply_to(message, "❌ نوع الملف غير مدعوم.")

    # --- تسجيل الدخول ---
    elif step == "phone":
        phone = message.text.strip().replace(" ", "")
        client = Client(f"temp_{phone}", api_id=API_ID, api_hash=API_HASH, in_memory=True)
        await client.connect()
        try:
            sent_code = await client.send_code(phone)
            user_states[user_id] = {"step": "code", "phone": phone, "client": client, "phone_code_hash": sent_code.phone_code_hash}
            await bot.reply_to(message, "📩 تم إرسال الكود. أرسله هنا (مثال: `1 2 3 4 5`):", parse_mode="Markdown")
        except Exception as e:
            await client.disconnect()
            user_states.pop(user_id, None)
            await bot.reply_to(message, f"❌ خطأ: {e}")

    elif step == "code":
        code = message.text.strip().replace(" ", "")
        client = state["client"]
        phone = state["phone"]
        try:
            await client.sign_in(phone, state["phone_code_hash"], code)
            session = await client.export_session_string()
            storage_chat_id, storage_link = await create_storage_group(client)
            DB_STATE["accounts"][phone] = {
                "session": session, "owner_id": user_id, "auto_save": False, 
                "autopost": [], "storage_chat_id": storage_chat_id, "storage_chat_link": storage_link,
                "auto_reply": {"active": False, "msg": "", "cooldown_hours": 3},
                "cached_groups": [], "shortcuts": {}, "exceptions": {"storage": [], "autoreply": []}, "last_replies": {},
                "raid": {"sentences": []}
            }
            await save_to_channel()
            await client.disconnect()
            await start_single_client(phone, DB_STATE["accounts"][phone])  
            user_states.pop(user_id, None)
            msg_reply = f"✅ **تم ربط الحساب `{phone}`!**\n"
            msg_reply += "تم إنشاء 'مجموعة التخزين' بنجاح." if storage_chat_id else "⚠️ فشل إنشاء مجموعة التخزين تلقائياً، يرجى إنشائها من الإعدادات."
            await bot.reply_to(message, msg_reply, parse_mode="Markdown")
        except SessionPasswordNeeded:
            user_states[user_id]["step"] = "2fa"
            await bot.reply_to(message, "🔐 الحساب محمي (2FA). أرسل كلمة المرور:")
        except Exception as e:
            await bot.reply_to(message, f"❌ خطأ: {e}")

    elif step == "2fa":
        client = state["client"]
        phone = state["phone"]
        try:
            await client.check_password(message.text.strip())
            session = await client.export_session_string()
            storage_chat_id, storage_link = await create_storage_group(client)
            DB_STATE["accounts"][phone] = {
                "session": session, "owner_id": user_id, "auto_save": False, 
                "autopost": [], "storage_chat_id": storage_chat_id, "storage_chat_link": storage_link,
                "auto_reply": {"active": False, "msg": "", "cooldown_hours": 3},
                "cached_groups": [], "shortcuts": {}, "exceptions": {"storage": [], "autoreply": []}, "last_replies": {},
                "raid": {"sentences": []}
            }
            await save_to_channel()
            await client.disconnect()
            await start_single_client(phone, DB_STATE["accounts"][phone])
            user_states.pop(user_id, None)
            msg_reply = f"✅ **تم ربط الحساب `{phone}`!**\n"
            msg_reply += "تم إنشاء 'مجموعة التخزين' بنجاح." if storage_chat_id else "⚠️ فشل إنشاء مجموعة التخزين تلقائياً، يرجى إنشائها من الإعدادات."
            await bot.reply_to(message, msg_reply, parse_mode="Markdown")
        except Exception as e:
            await bot.reply_to(message, f"❌ كلمة المرور خطأ: {e}")

    # --- إعدادات الرد التلقائي ---
    elif step == "autoreply_msg":
        user_states[user_id]["reply_msg"] = message.text
        user_states[user_id]["step"] = "autoreply_cooldown"
        await bot.reply_to(message, "⏳ **كم ساعة يجب أن تمر حتى يرد البوت على نفس الشخص مرة أخرى؟**\n(مثال: `5`):")

    elif step == "autoreply_cooldown":
        try:
            hours = int(message.text.strip())
            phone = state["phone"]
            DB_STATE["accounts"][phone]["auto_reply"]["msg"] = state["reply_msg"]
            DB_STATE["accounts"][phone]["auto_reply"]["cooldown_hours"] = hours
            await save_to_channel()
            user_states.pop(user_id, None)
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🔙 رجوع للحساب", callback_data=f"panel_{phone}"))
            await bot.reply_to(message, "✅ **تم حفظ إعدادات الرد التلقائي بنجاح!**", reply_markup=markup, parse_mode="Markdown")
        except:
            await bot.reply_to(message, "❌ يرجى إرسال رقم الساعات فقط (مثال: `5`).")

    # --- إعدادات النشر التلقائي ---
    elif step == "post_msg":
        user_states[user_id]["msg"] = message.text
        user_states[user_id]["step"] = "post_interval"
        await bot.reply_to(message, "⏱ أرسل المدة الزمنية بين كل نشر بالدقائق (مثلاً `60` تعني كل ساعة):")

    elif step == "post_interval":
        try:
            interval = int(message.text.strip())
            phone = state["phone"]
            task = {
                "active": False, "targets": [], "msg": state["msg"],
                "interval": interval, "last_sent": 0
            }
            DB_STATE["accounts"][phone]["autopost"].append(task)
            await save_to_channel()
            task_idx = len(DB_STATE["accounts"][phone]["autopost"]) - 1
            user_states.pop(user_id, None)
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🎯 تحديد القروبات للنشر", callback_data=f"edittgts_{phone}_{task_idx}_0"))
            await bot.reply_to(message, "✅ **تم إنشاء المهمة بنجاح!**\nالرجاء الضغط على الزر أدناه لتحديد القروبات التي سينشر بها:", reply_markup=markup, parse_mode="Markdown")
        except:
            await bot.reply_to(message, "❌ يرجى إرسال أرقام فقط للدقائق.")

# ==========================================
# 7. دوال التشغيل
# ==========================================
async def start_bot():
    await bot.delete_webhook(drop_pending_updates=True)
    await sync_from_channel()
    await start_active_sessions()
    asyncio.create_task(autopost_worker()) 
    print("🚀 Shadow Userbot Agency v3 (optimized) is running on Render!")
    while True:
        try:
            await bot.polling(non_stop=True, timeout=60)
        except Exception as e:
            print(f"🔥 Polling crash: {e}. Restart in 5s...")
            await asyncio.sleep(5)

def run():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(start_bot())
    except KeyboardInterrupt:
        print("🛑 Stopped.")
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()

if __name__ == "__main__":
    run()
