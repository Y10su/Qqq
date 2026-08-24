import os
import asyncio
import json
import re
from telebot.async_telebot import AsyncTeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram import Client
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

# ==========================================
# 2. نظام قاعدة البيانات السحابية (بصيغة الملكية)
# ==========================================
DB_STATE = {
    "admins": [PRIMARY_ADMIN_ID],
    "accounts": {} # الصيغة: { "phone": {"session": "...", "owner_id": 123} }
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
                        
                        # توافق مع البيانات القديمة إن وجدت
                        accounts = data.get("accounts", {})
                        for phone, info in accounts.items():
                            if isinstance(info, str):
                                accounts[phone] = {"session": info, "owner_id": PRIMARY_ADMIN_ID}
                        DB_STATE["accounts"] = accounts
                        
                        print(f"✅ تم استرجاع: {len(DB_STATE['admins'])} أدمن و {len(DB_STATE['accounts'])} حساب.")
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
        print(f"❌ خطأ الحفظ: {e}")

# ==========================================
# 3. لوحة التحكم الأساسية (المدير + الإدمنية)
# ==========================================
@bot.message_handler(commands=['start'])
async def start_cmd(message):
    user_id = message.chat.id
    if user_id not in DB_STATE["admins"]:
        await bot.reply_to(message, "⛔ عذراً، هذا البوت مخصص للإدارة فقط.")
        return

    markup = InlineKeyboardMarkup()
    # أزرار مشتركة لكل الإدمنية
    markup.add(
        InlineKeyboardButton("➕ إضافة حساب", callback_data="add_account"),
        InlineKeyboardButton("📱 حساباتي المرتبطة", callback_data="my_accounts")
    )
    
    # أزرار مخصصة للمدير الأساسي فقط
    if user_id == PRIMARY_ADMIN_ID:
        markup.add(
            InlineKeyboardButton("➕ إضافة أدمن", callback_data="add_admin"),
            InlineKeyboardButton("🗑 حذف أدمن", callback_data="del_admin")
        )
    
    owned_accounts = sum(1 for acc in DB_STATE["accounts"].values() if acc["owner_id"] == user_id)
    
    msg_text = (
        f"👋 **أهلاً بك في لوحة تحكم اليوزر بوت**\n\n"
        f"👤 صفتك: **{'مدير أساسي 👑' if user_id == PRIMARY_ADMIN_ID else 'أدمن فرعي 💼'}**\n"
        f"📱 حساباتك المرتبطة: **{owned_accounts}**\n\n"
        f"اختر من القائمة أدناه:"
    )
    await bot.send_message(user_id, msg_text, reply_markup=markup, parse_mode="Markdown")

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
        if not owned:
            await bot.answer_callback_query(call.id, "لا تملك أي حسابات مرتبطة حالياً.", show_alert=True)
            return
        
        for phone in owned:
            markup.add(InlineKeyboardButton(f"📱 {phone}", callback_data=f"panel_{phone}"))
        
        await bot.edit_message_text("👇 **حساباتك المرتبطة:**\nاضغط على الحساب للتحكم به:", chat_id=user_id, message_id=call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    elif data.startswith("panel_"):
        phone = data.split("_")[1]
        if phone not in DB_STATE["accounts"] or DB_STATE["accounts"][phone]["owner_id"] != user_id:
            await bot.answer_callback_query(call.id, "خطأ: الحساب غير موجود أو لا تملكه.", show_alert=True)
            return
            
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("✍️ تغيير النبذة (Bio)", callback_data=f"bio_{phone}"))
        markup.add(InlineKeyboardButton("🔗 الانضمام لقناة/جروب", callback_data=f"join_{phone}"))
        markup.add(InlineKeyboardButton("🗑 حذف الحساب نهائياً", callback_data=f"delete_{phone}"))
        markup.add(InlineKeyboardButton("🔙 رجوع", callback_data="my_accounts"))
        
        await bot.edit_message_text(f"⚙️ **لوحة التحكم بالحساب: `{phone}`**\nماذا تريد أن تفعل؟", chat_id=user_id, message_id=call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    # إجراءات اليوزر بوت
    elif data.startswith("bio_"):
        phone = data.split("_")[1]
        user_states[user_id] = {"step": "wait_bio", "phone": phone}
        await bot.send_message(user_id, "✍️ أرسل النبذة (Bio) الجديدة الآن:")
        await bot.answer_callback_query(call.id)

    elif data.startswith("join_"):
        phone = data.split("_")[1]
        user_states[user_id] = {"step": "wait_link", "phone": phone}
        await bot.send_message(user_id, "🔗 أرسل رابط القناة أو الجروب (العام أو الخاص) للانضمام إليه:")
        await bot.answer_callback_query(call.id)
        
    elif data.startswith("delete_"):
        phone = data.split("_")[1]
        DB_STATE["accounts"].pop(phone, None)
        await save_to_channel()
        await bot.answer_callback_query(call.id, "✅ تم حذف الحساب من النظام.", show_alert=True)
        await bot.edit_message_text("✅ تم الحذف بنجاح.", chat_id=user_id, message_id=call.message.message_id)

    # إدارة الإدمنية (للمدير الأساسي)
    elif data == "add_admin" and user_id == PRIMARY_ADMIN_ID:
        user_states[user_id] = {"step": "add_admin_id"}
        await bot.send_message(user_id, "👥 أرسل الآي دي (ID) الخاص بالأدمن الجديد:")
        await bot.answer_callback_query(call.id)
        
    elif data == "del_admin" and user_id == PRIMARY_ADMIN_ID:
        markup = InlineKeyboardMarkup()
        for ad_id in DB_STATE["admins"]:
            if ad_id != PRIMARY_ADMIN_ID:
                markup.add(InlineKeyboardButton(f"🗑 {ad_id}", callback_data=f"remove_admin_{ad_id}"))
        if len(markup.keyboard) == 0:
            await bot.answer_callback_query(call.id, "لا يوجد إدمنية فرعيين لحذفهم.", show_alert=True)
            return
        await bot.edit_message_text("👇 اختر الأدمن المراد حذفه:", chat_id=user_id, message_id=call.message.message_id, reply_markup=markup)

    elif data.startswith("remove_admin_") and user_id == PRIMARY_ADMIN_ID:
        target = int(data.split("_")[2])
        if target in DB_STATE["admins"]:
            DB_STATE["admins"].remove(target)
            await save_to_channel()
            await bot.answer_callback_query(call.id, "✅ تم حذف الأدمن بنجاح.", show_alert=True)
            await bot.delete_message(user_id, call.message.message_id)

# ==========================================
# 4. معالجة الإدخال النصي (تسجيل، أوامر الحسابات، الإدارة)
# ==========================================
@bot.message_handler(func=lambda msg: msg.chat.id in DB_STATE["admins"] and msg.chat.id in user_states)
async def handle_inputs(message):
    user_id = message.chat.id
    state = user_states[user_id]
    step = state.get("step")

    # --- إجراءات تسجيل الدخول ---
    if step == "phone":
        phone = message.text.strip().replace(" ", "")
        client = Client(f"temp_{phone}", api_id=API_ID, api_hash=API_HASH, in_memory=True)
        await client.connect()
        try:
            sent_code = await client.send_code(phone)
            user_states[user_id] = {"step": "code", "phone": phone, "client": client, "phone_code_hash": sent_code.phone_code_hash}
            await bot.reply_to(message, "📩 تم إرسال الكود. أرسله هنا مفصولاً بمسافات (مثل: `1 2 3 4 5`):", parse_mode="Markdown")
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
            DB_STATE["accounts"][phone] = {"session": session, "owner_id": user_id}
            await save_to_channel()
            await client.disconnect()
            user_states.pop(user_id, None)
            await bot.reply_to(message, f"✅ **تم تسجيل الحساب `{phone}` وربطه بك!**", parse_mode="Markdown")
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
            DB_STATE["accounts"][phone] = {"session": session, "owner_id": user_id}
            await save_to_channel()
            await client.disconnect()
            user_states.pop(user_id, None)
            await bot.reply_to(message, f"✅ **تم التسجيل وكلمة المرور صحيحة للحساب `{phone}`!**", parse_mode="Markdown")
        except Exception as e:
            await bot.reply_to(message, f"❌ كلمة المرور خطأ: {e}")

    # --- إجراءات اليوزر بوت الفورية ---
    elif step == "wait_bio":
        phone = state["phone"]
        bio = message.text
        session = DB_STATE["accounts"].get(phone, {}).get("session")
        if session:
            await bot.reply_to(message, "⏳ جاري تحديث النبذة...")
            client = Client(f"temp_action_{phone}", session_string=session, in_memory=True)
            try:
                await client.connect()
                await client.update_profile(bio=bio)
                await client.disconnect()
                await bot.reply_to(message, "✅ تم تغيير النبذة بنجاح!")
            except AuthKeyUnregistered:
                await bot.reply_to(message, "❌ الجلسة منتهية، يرجى تسجيل الدخول مجدداً.")
            except Exception as e:
                await bot.reply_to(message, f"❌ خطأ: {e}")
        user_states.pop(user_id, None)

    elif step == "wait_link":
        phone = state["phone"]
        link = message.text
        session = DB_STATE["accounts"].get(phone, {}).get("session")
        if session:
            await bot.reply_to(message, "⏳ جاري محاولة الانضمام...")
            client = Client(f"temp_action_{phone}", session_string=session, in_memory=True)
            try:
                await client.connect()
                await client.join_chat(link)
                await client.disconnect()
                await bot.reply_to(message, "✅ تم الانضمام بنجاح!")
            except Exception as e:
                await bot.reply_to(message, f"❌ خطأ: {e}")
        user_states.pop(user_id, None)

    # --- إدارة الإدمنية ---
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
# 5. دالة التشغيل
# ==========================================
async def start_bot():
    await sync_from_channel()
    print("Bot 2 (Userbot Agency) is running with Cloud DB...")
    await bot.polling(non_stop=True)

def run():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(start_bot())
