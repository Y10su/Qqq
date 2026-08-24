import os
import asyncio
import json
import re
import time
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

# قائمة لحفظ الحسابات المتصلة النشطة
RUNNING_CLIENTS = {}

# ==========================================
# 2. نظام قاعدة البيانات السحابية
# ==========================================
DB_STATE = {
    "admins": [PRIMARY_ADMIN_ID],
    "accounts": {} 
    # الصيغة: { "phone": {"session": "...", "owner_id": 123, "auto_save": False, "autopost": {"active": False, "target": "", "msg": "", "interval": 60}} }
}
DB_MESSAGE_ID = None
LAST_POST_TIME = {} # تعقب وقت آخر نشر لتفادي الحظر { "phone": timestamp }

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
                                accounts[phone] = {"session": info, "owner_id": PRIMARY_ADMIN_ID, "auto_save": False, "autopost": {"active": False}}
                            else:
                                if "auto_save" not in info: info["auto_save"] = False
                                if "autopost" not in info: info["autopost"] = {"active": False}
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
# 3. أنظمة اليوزر بوت الآلية (حفظ الصور والنشر)
# ==========================================
async def handle_disappearing_media(client, message):
    """صيد الصور والفويسات ذاتية التدمير وحفظها تلقائياً"""
    phone = getattr(client, "acc_phone", None)
    if not phone: return
    
    acc_info = DB_STATE["accounts"].get(phone, {})
    if not acc_info.get("auto_save"): return

    is_ttl = False
    if getattr(message, "ttl_seconds", None): is_ttl = True
    elif message.photo and getattr(message.photo, "ttl_seconds", None): is_ttl = True
    elif message.video and getattr(message.video, "ttl_seconds", None): is_ttl = True
    elif message.voice and getattr(message.voice, "ttl_seconds", None): is_ttl = True
    elif message.video_note and getattr(message.video_note, "ttl_seconds", None): is_ttl = True

    if is_ttl:
        try:
            path = await message.download()
            if path:
                caption = f"🤫 **تم اصطياد وسائط ذاتية التدمير!**\nالمرسل: {message.from_user.first_name if message.from_user else 'مجهول'}"
                if message.photo:
                    await client.send_photo("me", path, caption=caption)
                elif message.video:
                    await client.send_video("me", path, caption=caption)
                else:
                    await client.send_document("me", path, caption=caption)
                os.remove(path)
        except Exception as e:
            print(f"Error saving TTL for {phone}: {e}")

async def start_active_sessions():
    """تشغيل جميع الحسابات في الخلفية عند إقلاع السيرفر"""
    for phone, info in DB_STATE["accounts"].items():
        if phone not in RUNNING_CLIENTS:
            session = info.get("session")
            client = Client(f"acc_{phone}", session_string=session, in_memory=True)
            client.acc_phone = phone
            
            # إضافة معالج صيد الصور ذاتية التدمير
            client.add_handler(MessageHandler(handle_disappearing_media, filters.private & (filters.photo | filters.video | filters.voice | filters.video_note)))
            
            try:
                await client.start()
                RUNNING_CLIENTS[phone] = client
                print(f"✅ الحساب {phone} متصل وجاهز للاستماع الآلي.")
            except AuthKeyUnregistered:
                print(f"⚠️ الحساب {phone} تم تسجيل الخروج منه.")
            except Exception as e:
                print(f"❌ فشل تشغيل {phone}: {e}")

async def autopost_loop():
    """مؤقت زمني يعمل كل دقيقة للتحقق من النشر التلقائي"""
    while True:
        await asyncio.sleep(60)
        current_time = time.time()
        
        for phone, info in DB_STATE["accounts"].items():
            autopost = info.get("autopost", {})
            if autopost.get("active"):
                client = RUNNING_CLIENTS.get(phone)
                target = autopost.get("target")
                msg_text = autopost.get("msg")
                interval_minutes = autopost.get("interval", 60)
                
                last_sent = LAST_POST_TIME.get(phone, 0)
                
                # إذا حان وقت النشر
                if client and target and msg_text and (current_time - last_sent >= interval_minutes * 60):
                    try:
                        await client.send_message(target, msg_text)
                        LAST_POST_TIME[phone] = current_time
                    except Exception as e:
                        print(f"⚠️ خطأ النشر التلقائي لحساب {phone}: {e}")

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
        markup.add(InlineKeyboardButton("➕ إضافة أدمن", callback_data="add_admin"), InlineKeyboardButton("🗑 حذف أدمن", callback_data="del_admin"))
    
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
        post_status = "✅ مفعل" if acc_info.get("autopost", {}).get("active") else "❌ معطل"
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(f"📥 حفظ التدمير الذاتي: {save_status}", callback_data=f"autosave_{phone}"))
        markup.add(InlineKeyboardButton(f"🔄 النشر التلقائي: {post_status}", callback_data=f"autopost_{phone}"))
        markup.add(InlineKeyboardButton("🔗 الانضمام لقناة", callback_data=f"join_{phone}"), InlineKeyboardButton("✍️ تغيير النبذة", callback_data=f"bio_{phone}"))
        markup.add(InlineKeyboardButton("🗑 حذف الحساب", callback_data=f"delete_{phone}"), InlineKeyboardButton("🔙 رجوع", callback_data="my_accounts"))
        
        await bot.edit_message_text(f"⚙️ **تحكم حساب: `{phone}`**", chat_id=user_id, message_id=call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    elif data.startswith("autosave_"):
        phone = data.split("_")[1]
        current_status = DB_STATE["accounts"][phone].get("auto_save", False)
        DB_STATE["accounts"][phone]["auto_save"] = not current_status
        await save_to_channel()
        # تحديث اللوحة
        call.data = f"panel_{phone}"
        await callbacks(call)

    elif data.startswith("autopost_"):
        phone = data.split("_")[1]
        current_status = DB_STATE["accounts"][phone].get("autopost", {}).get("active", False)
        if current_status:
            DB_STATE["accounts"][phone]["autopost"]["active"] = False
            await save_to_channel()
            call.data = f"panel_{phone}"
            await callbacks(call)
        else:
            user_states[user_id] = {"step": "post_target", "phone": phone}
            await bot.send_message(user_id, "🎯 أرسل يوزر القناة/القروب المراد النشر فيه (مثال: `@username`):", parse_mode="Markdown")
            await bot.answer_callback_query(call.id)

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

@bot.message_handler(func=lambda msg: msg.chat.id in DB_STATE["admins"] and msg.chat.id in user_states)
async def handle_inputs(message):
    user_id = message.chat.id
    state = user_states[user_id]
    step = state.get("step")

    # [تسجيل الدخول - نفس الكود السابق تماماً]
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
            DB_STATE["accounts"][phone] = {"session": session, "owner_id": user_id, "auto_save": False, "autopost": {"active": False}}
            await save_to_channel()
            await client.disconnect()
            await start_active_sessions() # تشغيل الحساب فوراً
            user_states.pop(user_id, None)
            await bot.reply_to(message, f"✅ **تم ربط وتشغيل الحساب `{phone}`!**", parse_mode="Markdown")
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
            DB_STATE["accounts"][phone] = {"session": session, "owner_id": user_id, "auto_save": False, "autopost": {"active": False}}
            await save_to_channel()
            await client.disconnect()
            await start_active_sessions()
            user_states.pop(user_id, None)
            await bot.reply_to(message, f"✅ **تم ربط وتشغيل الحساب `{phone}`!**", parse_mode="Markdown")
        except Exception as e:
            await bot.reply_to(message, f"❌ كلمة المرور خطأ: {e}")

    # [إعدادات النشر التلقائي]
    elif step == "post_target":
        user_states[user_id]["target"] = message.text.strip()
        user_states[user_id]["step"] = "post_msg"
        await bot.reply_to(message, "✍️ ممتاز، أرسل الآن الرسالة (النص) التي تريد نشرها تلقائياً:")

    elif step == "post_msg":
        user_states[user_id]["msg"] = message.text
        user_states[user_id]["step"] = "post_interval"
        await bot.reply_to(message, "⏱ أرسل المدة الزمنية بين كل نشر بالدقائق (مثلاً `60` تعني كل ساعة):")

    elif step == "post_interval":
        try:
            interval = int(message.text.strip())
            phone = state["phone"]
            DB_STATE["accounts"][phone]["autopost"] = {
                "active": True,
                "target": state["target"],
                "msg": state["msg"],
                "interval": interval
            }
            await save_to_channel()
            user_states.pop(user_id, None)
            await bot.reply_to(message, "✅ **تم تفعيل النشر التلقائي بنجاح!**", parse_mode="Markdown")
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

# ==========================================
# 5. دوال التشغيل والمزامنة
# ==========================================
async def start_bot():
    await sync_from_channel()
    await start_active_sessions() # تشغيل جميع الحسابات المخزنة
    asyncio.create_task(autopost_loop()) # تشغيل مؤقت النشر التلقائي في الخلفية
    
    print("Bot 2 (Userbot Agency) is running actively...")
    await bot.polling(non_stop=True)

def run():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(start_bot())
