import os
import asyncio
import json
import urllib.request
from telebot.async_telebot import AsyncTeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram import Client
from pyrogram.errors import SessionPasswordNeeded, PhoneCodeInvalid, PasswordHashInvalid

# ==========================================
# 1. إعدادات البوت والآي دي والتطبيق المباشرة
# ==========================================
BOT_TOKEN = "7662959141:AAG6n0yqVm-lvD8eq1PS1NNWAsvSlmcYbos"
API_ID = 37129514
API_HASH = "29af008f32ddd784867118d0a58fb8c6"
ADMIN_ID = 8145086924

# رابط قاعدة البيانات السحابية (اختياري، يعمل محلياً وسحابياً)
DB_ENDPOINT = os.environ.get("DB_ENDPOINT", "")
DB_API_KEY = os.environ.get("DB_API_KEY", "")

bot = AsyncTeleBot(BOT_TOKEN)

login_sessions = {}
active_clients = {}

# ==========================================
# 2. إدارة التخزين السحابي / المحلي للجلسات
# ==========================================
def save_account_cloud(phone_number, session_string):
    """حفظ الجلسة لضمان عدم فقدان الحسابات نهائياً"""
    if not DB_ENDPOINT:
        local_db = {}
        if os.path.exists("saved_sessions.json"):
            try:
                with open("saved_sessions.json", "r") as f: local_db = json.load(f)
            except: pass
        local_db[phone_number] = session_string
        with open("saved_sessions.json", "w") as f: json.dump(local_db, f)
        return

    try:
        data = json.dumps({phone_number: session_string}).encode("utf-8")
        req = urllib.request.Request(DB_ENDPOINT, data=data, headers={
            "Content-Type": "application/json",
            "X-Master-Key": DB_API_KEY
        }, method="PUT")
        urllib.request.urlopen(req)
    except Exception as e:
        print(f"Cloud DB Save Error: {e}")

def get_all_saved_accounts():
    """استرجاع كل الحسابات المحفوظة"""
    if not DB_ENDPOINT:
        if os.path.exists("saved_sessions.json"):
            try:
                with open("saved_sessions.json", "r") as f: return json.load(f)
            except: pass
        return {}
    try:
        req = urllib.request.Request(DB_ENDPOINT, headers={"X-Master-Key": DB_API_KEY})
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())
    except:
        return {}

# ==========================================
# 3. واجهة التحكم والأوامر
# ==========================================
@bot.message_handler(commands=['start'])
async def start_cmd(message):
    if message.chat.id != ADMIN_ID:
        await bot.reply_to(message, "⛔ هذا البوت مخصص للإدارة والتحكم بالحسابات فقط.")
        return

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("➕ تسجيل دخول حساب جديد", callback_data="add_account"))
    markup.add(InlineKeyboardButton("📱 الحسابات المتصلة", callback_data="list_accounts"))
    markup.add(InlineKeyboardButton("⚡ ميزة أولية: فحص نشاط الحسابات", callback_data="check_status"))

    await bot.send_message(
        message.chat.id,
        "👋 **مرحباً بك في نظام إدارة حسابات تليجرام**\n\nاختر من الخيارات بالأسفل للبدء:",
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.message.chat.id == ADMIN_ID)
async def callbacks(call):
    if call.data == "add_account":
        login_sessions[ADMIN_ID] = {"step": "phone"}
        await bot.send_message(ADMIN_ID, "📱 أرسل رقم هاتف الحساب مع المفتاح الدولي (مثال: `+966500000000`):", parse_mode="Markdown")
        await bot.answer_callback_query(call.id)

    elif call.data == "list_accounts":
        accounts = get_all_saved_accounts()
        if not accounts:
            await bot.send_message(ADMIN_ID, "📭 لا يوجد أي حسابات مسجلة حتى الآن.")
        else:
            text = "📋 **الحسابات المسجلة والدائمة:**\n\n"
            for phone in accounts.keys():
                text += f"• `{phone}`\n"
            await bot.send_message(ADMIN_ID, text, parse_mode="Markdown")
        await bot.answer_callback_query(call.id)

    elif call.data == "check_status":
        accounts = get_all_saved_accounts()
        if not accounts:
            await bot.send_message(ADMIN_ID, "❌ لا توجد حسابات لإجراء الفحص.")
            await bot.answer_callback_query(call.id)
            return

        await bot.send_message(ADMIN_ID, "⏳ جاري فحص حالة الحسابات ومزامنة معلوماتها...")
        for phone, session_str in accounts.items():
            try:
                client = Client(f"session_{phone}", api_id=API_ID, api_hash=API_HASH, session_string=session_str, in_memory=True)
                await client.start()
                me = await client.get_me()
                await bot.send_message(
                    ADMIN_ID,
                    f"🟢 **حساب نشط:**\n"
                    f"👤 الاسم: {me.first_name}\n"
                    f"🆔 الآي دي: `{me.id}`\n"
                    f"📞 الرقم: `{phone}`\n"
                    f"💬 اليوزر: @{me.username or 'بدون'}",
                    parse_mode="Markdown"
                )
                await client.stop()
            except Exception as e:
                await bot.send_message(ADMIN_ID, f"🔴 **فشل الاتصال بالحساب `{phone}`:**\n{e}", parse_mode="Markdown")
        await bot.answer_callback_query(call.id)

# ==========================================
# 4. استقبال خطوات تسجيل الدخول
# ==========================================
@bot.message_handler(func=lambda msg: msg.chat.id == ADMIN_ID and ADMIN_ID in login_sessions)
async def handle_login_flow(message):
    session_data = login_sessions[ADMIN_ID]
    step = session_data.get("step")

    # الخطوة 1: الرقم وإرسال الكود
    if step == "phone":
        phone = message.text.strip().replace(" ", "")
        client = Client(f"temp_{phone}", api_id=API_ID, api_hash=API_HASH, in_memory=True)
        await client.connect()
        try:
            sent_code = await client.send_code(phone)
            login_sessions[ADMIN_ID] = {
                "step": "code",
                "phone": phone,
                "client": client,
                "phone_code_hash": sent_code.phone_code_hash
            }
            await bot.reply_to(message, "📩 تم إرسال الكود إلى تطبيق تليجرام.\n\nأرسل الكود مفصولاً بمسافات (مثل: `1 2 3 4 5`):", parse_mode="Markdown")
        except Exception as e:
            await client.disconnect()
            login_sessions.pop(ADMIN_ID, None)
            await bot.reply_to(message, f"❌ خطأ أثناء إرسال الكود: {e}")

    # الخطوة 2: فحص الكود
    elif step == "code":
        code = message.text.strip().replace(" ", "")
        client = session_data["client"]
        phone = session_data["phone"]
        phone_code_hash = session_data["phone_code_hash"]

        try:
            await client.sign_in(phone, phone_code_hash, code)
            session_string = await client.export_session_string()
            save_account_cloud(phone, session_string)
            await client.disconnect()
            login_sessions.pop(ADMIN_ID, None)
            await bot.reply_to(message, f"✅ **تم تسجيل الدخول بنجاح وحفظ الحساب `{phone}`!**", parse_mode="Markdown")
        except SessionPasswordNeeded:
            login_sessions[ADMIN_ID]["step"] = "2fa"
            await bot.reply_to(message, "🔐 الحساب محمي بالتحقق بخطوتين (2FA).\nالرجاء إرسال كلمة المرور الآن:")
        except (PhoneCodeInvalid, Exception) as e:
            await bot.reply_to(message, f"❌ كود غير صحيح أو خطأ: {e}")

    # الخطوة 3: التحقق بخطوتين
    elif step == "2fa":
        password = message.text.strip()
        client = session_data["client"]
        phone = session_data["phone"]

        try:
            await client.check_password(password)
            session_string = await client.export_session_string()
            save_account_cloud(phone, session_string)
            await client.disconnect()
            login_sessions.pop(ADMIN_ID, None)
            await bot.reply_to(message, f"✅ **تم التحقق وحفظ الحساب `{phone}` دائماً!**", parse_mode="Markdown")
        except (PasswordHashInvalid, Exception) as e:
            await bot.reply_to(message, f"❌ كلمة المرور غير صحيحة: {e}")

# ==========================================
# 5. دالة التشغيل المتوافقة مع المشغل الرئيسي bot.py
# ==========================================
async def start_bot():
    print("Bot 3 (Telegram Account Manager) is running...")
    await bot.polling(non_stop=True)

def run():
    asyncio.run(start_bot())
