import os
import asyncio
import json
import re
from telebot.async_telebot import AsyncTeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram import Client
from pyrogram.errors import SessionPasswordNeeded, PhoneCodeInvalid, PasswordHashInvalid

# ==========================================
# 1. إعدادات اليوزر بوت
# ==========================================
BOT_TOKEN = "8666142908:AAFZhEu_McY2TEy_6wtGbB7RhjFbxF7fTeE"
API_ID = 37129514
API_HASH = "29af008f32ddd784867118d0a58fb8c6"
PRIMARY_ADMIN_ID = 8145086924

# قناة التخزين السحابي الجديدة لليوزر بوت
DB_CHANNEL_ID = -1004352728061

bot = AsyncTeleBot(BOT_TOKEN)
login_sessions = {}

# ==========================================
# 2. نظام إدارة قاعدة البيانات عبر قناة التليجرام
# ==========================================
DB_STATE = {
    "admins": [PRIMARY_ADMIN_ID],
    "accounts": {}  # سيتم حفظ الحسابات هنا: { "رقم الجوال": "كود الجلسة" }
}

DB_MESSAGE_ID = None

async def sync_from_channel():
    """استرجاع قاعدة البيانات السحابية لليوزر بوت (نفس طريقة البوت الأول)"""
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
                        DB_STATE["accounts"] = data.get("accounts", {})
                        print(f"✅ تم استرجاع البيانات بنجاح: {len(DB_STATE['accounts'])} حساب محفوظ.")
                        return
                    except Exception as e:
                        print(f"❌ فشل فك تشفير البيانات من القناة: {e}")

        print("⚠️ لم يتم العثور على قاعدة بيانات صالحة، جاري الإنشاء...")
        await save_to_channel()

    except Exception as e:
        print(f"❌ خطأ أثناء قراءة القناة (تأكد من رفع البوت كمشرف): {e}")
        await save_to_channel(create_new=True)

async def save_to_channel(create_new=False):
    """تحديث الرسالة المثبتة في القناة بدون مسح البيانات"""
    global DB_MESSAGE_ID
    if PRIMARY_ADMIN_ID not in DB_STATE["admins"]:
        DB_STATE["admins"].append(PRIMARY_ADMIN_ID)

    payload = json.dumps(DB_STATE, indent=2, ensure_ascii=False)
    formatted_text = f"📦 **قاعدة بيانات اليوزر بوت (الحسابات والجلسات)**\n\n```json\n{payload}\n```"

    try:
        if DB_MESSAGE_ID and not create_new:
            try:
                await bot.edit_message_text(
                    formatted_text,
                    chat_id=DB_CHANNEL_ID,
                    message_id=DB_MESSAGE_ID,
                    parse_mode="Markdown"
                )
            except Exception as edit_err:
                if "message to edit not found" in str(edit_err).lower():
                    msg = await bot.send_message(DB_CHANNEL_ID, formatted_text, parse_mode="Markdown")
                    DB_MESSAGE_ID = msg.message_id
                    await bot.pin_chat_message(DB_CHANNEL_ID, msg.message_id)
        else:
            msg = await bot.send_message(DB_CHANNEL_ID, formatted_text, parse_mode="Markdown")
            DB_MESSAGE_ID = msg.message_id
            await bot.pin_chat_message(DB_CHANNEL_ID, msg.message_id)
            print(f"📌 تم تثبيت رسالة قاعدة البيانات الجديدة برقم: {DB_MESSAGE_ID}")
    except Exception as e:
        print(f"❌ خطأ أثناء الحفظ في القناة: {e}")

# ==========================================
# 3. واجهة التحكم باليوزر بوت
# ==========================================
@bot.message_handler(commands=['start'])
async def start_cmd(message):
    if message.chat.id not in DB_STATE["admins"]:
        await bot.reply_to(message, "⛔ هذا البوت مخصص للإدارة فقط.")
        return

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("➕ إضافة حساب جديد (تسجيل دخول)", callback_data="add_account"))
    
    accounts_count = len(DB_STATE["accounts"])
    await bot.send_message(
        message.chat.id,
        f"👋 **لوحة تحكم اليوزر بوت (Userbot Manager)**\n\n"
        f"☁️ *الحسابات المحفوظة حالياً:* **{accounts_count}**\n"
        f"يتم حفظ الجلسات في القناة السحابية باستخدام نفس نظام البوت الأول.",
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.message.chat.id in DB_STATE["admins"])
async def callbacks(call):
    if call.data == "add_account":
        login_sessions[call.message.chat.id] = {"step": "phone"}
        await bot.send_message(call.message.chat.id, "📱 أرسل رقم هاتف الحساب مع المفتاح الدولي (مثال: `+966500000000`):", parse_mode="Markdown")
        await bot.answer_callback_query(call.id)

# ==========================================
# 4. تسجيل الدخول والتعامل مع الأكواد و 2FA
# ==========================================
@bot.message_handler(func=lambda msg: msg.chat.id in DB_STATE["admins"] and msg.chat.id in login_sessions)
async def handle_login_flow(message):
    admin_id = message.chat.id
    session_data = login_sessions[admin_id]
    step = session_data.get("step")

    # الخطوة 1: طلب الكود
    if step == "phone":
        phone = message.text.strip().replace(" ", "")
        client = Client(f"temp_{phone}", api_id=API_ID, api_hash=API_HASH, in_memory=True)
        await client.connect()
        try:
            sent_code = await client.send_code(phone)
            login_sessions[admin_id] = {
                "step": "code",
                "phone": phone,
                "client": client,
                "phone_code_hash": sent_code.phone_code_hash
            }
            await bot.reply_to(message, "📩 تم إرسال الكود إلى تطبيق تليجرام الخاص بالحساب.\n\nأرسل الكود هنا (يُفضل إرساله مفصولاً بمسافات لتفادي الحظر مثل: `1 2 3 4 5`):", parse_mode="Markdown")
        except Exception as e:
            await client.disconnect()
            login_sessions.pop(admin_id, None)
            await bot.reply_to(message, f"❌ خطأ أثناء إرسال الكود: {e}")

    # الخطوة 2: التحقق من الكود
    elif step == "code":
        code = message.text.strip().replace(" ", "")
        client = session_data["client"]
        phone = session_data["phone"]
        phone_code_hash = session_data["phone_code_hash"]

        try:
            await client.sign_in(phone, phone_code_hash, code)
            session_string = await client.export_session_string()
            
            # حفظ الحساب في القاعدة السحابية
            DB_STATE["accounts"][phone] = session_string
            await save_to_channel()
            
            await client.disconnect()
            login_sessions.pop(admin_id, None)
            await bot.reply_to(message, f"✅ **تم تسجيل الدخول بنجاح!**\nتم حفظ جلسة الحساب `{phone}` في قاعدتك السحابية.", parse_mode="Markdown")
        except SessionPasswordNeeded:
            login_sessions[admin_id]["step"] = "2fa"
            await bot.reply_to(message, "🔐 الحساب محمي بالتحقق بخطوتين (2FA).\nالرجاء إرسال كلمة المرور الآن:")
        except (PhoneCodeInvalid, Exception) as e:
            await bot.reply_to(message, f"❌ الكود غير صحيح أو حدث خطأ: {e}")

    # الخطوة 3: التحقق بخطوتين
    elif step == "2fa":
        password = message.text.strip()
        client = session_data["client"]
        phone = session_data["phone"]

        try:
            await client.check_password(password)
            session_string = await client.export_session_string()
            
            # حفظ الحساب في القاعدة السحابية
            DB_STATE["accounts"][phone] = session_string
            await save_to_channel()
            
            await client.disconnect()
            login_sessions.pop(admin_id, None)
            await bot.reply_to(message, f"✅ **تم التحقق وكلمة المرور صحيحة!**\nتم حفظ جلسة الحساب `{phone}` في قاعدتك السحابية.", parse_mode="Markdown")
        except (PasswordHashInvalid, Exception) as e:
            await bot.reply_to(message, f"❌ كلمة المرور غير صحيحة: {e}")

# ==========================================
# 5. دالة التشغيل
# ==========================================
async def start_bot():
    await sync_from_channel()
    print("Bot 2 (Userbot Manager) is running with Cloud DB...")
    await bot.polling(non_stop=True)

def run():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(start_bot())
