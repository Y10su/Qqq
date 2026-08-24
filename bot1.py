bot2_final_code = '''import telebot
import re
import os
import json

# ==========================================
# الإعدادات الأساسية
# ==========================================
BOT_TOKEN = "8938474760:AAHBLfDoV_d1D8EKhYmSRocCpVTimbDpUgk"
PRIMARY_ADMIN_ID = 8145086924  

# قناة التخزين السحابية المحدثة
DB_CHANNEL_ID = -1004485802515  

bot = telebot.TeleBot(BOT_TOKEN)

# ==========================================
# نظام إدارة قاعدة البيانات عبر قناة التليجرام
# ==========================================
DB_STATE = {
    "admins": [PRIMARY_ADMIN_ID],
    "users": [],
    "banned": []
}

def sync_from_channel():
    """قراءة البيانات من الرسالة المثبتة في قناة التخزين عند الإقلاع"""
    global DB_STATE
    try:
        chat = bot.get_chat(DB_CHANNEL_ID)
        if chat.pinned_message and chat.pinned_message.text:
            text = chat.pinned_message.text
            match = re.search(r'```json\\n(.*?)\\n```', text, re.DOTALL)
            if match:
                data = json.loads(match.group(1))
                DB_STATE["admins"] = list(set(data.get("admins", [PRIMARY_ADMIN_ID])))
                DB_STATE["users"] = list(set(data.get("users", [])))
                DB_STATE["banned"] = list(set(data.get("banned", [])))
                print("✅ تم استرجاع قاعدة البيانات بنجاح من القناة.")
                return
    except Exception as e:
        print(f"⚠️ تعذر قراءة قاعدة البيانات القديمة: {e}")

    save_to_channel()

def save_to_channel():
    """حفظ البيانات وتحديثها في القناة مباشرة"""
    payload = json.dumps(DB_STATE, indent=2)
    formatted_text = f"📦 **نسخة قاعدة البيانات المحدثة**\\n\\n```json\\n{payload}\\n```"
    try:
        chat = bot.get_chat(DB_CHANNEL_ID)
        if chat.pinned_message:
            bot.edit_message_text(
                formatted_text,
                chat_id=DB_CHANNEL_ID,
                message_id=chat.pinned_message.message_id,
                parse_mode="Markdown"
            )
        else:
            msg = bot.send_message(DB_CHANNEL_ID, formatted_text, parse_mode="Markdown")
            bot.pin_chat_message(DB_CHANNEL_ID, msg.message_id)
    except Exception as e:
        print(f"❌ خطأ أثناء المزامنة مع القناة: {e}")

# مزامنة البيانات الأولية
sync_from_channel()

broadcasting_admins = {}
adding_admin_state = {}

WELCOME_MESSAGE = """أهلًا بك {name} في بوت قمة للقدرات لتجميع الاقسام  ✨

🔴 يرجى إرسال أي أسئلة أو أفكار تذكرها في اختبارك أو رأيتها في مواقع التواصل وردت في الاختبار، حتى نقوم بتجميعها وتنقيحها ونشرها وإفادة الطلاب 🩵

🔴 تقدر ترسل جزء من السؤال إذا ما تذكره كامل 👌

 @Saqimmah"""

# ==========================================
# أوامر الحظر والإدارة المباشرة
# ==========================================

@bot.message_handler(commands=['ban'])
def ban_user(message):
    if message.chat.id in DB_STATE["admins"]:
        user_id = None
        if message.reply_to_message and message.reply_to_message.text:
            match = re.search(r'الآي دي:\\s*(\\d+)', message.reply_to_message.text)
            if match:
                user_id = int(match.group(1))
        elif len(message.text.split()) > 1:
            try:
                user_id = int(message.text.split()[1])
            except ValueError: pass
            
        if user_id:
            if user_id not in DB_STATE["banned"]:
                DB_STATE["banned"].append(user_id)
                save_to_channel()
            bot.reply_to(message, f"🚫 تم حظر الطالب ذو الآي دي `{user_id}` بنجاح.", parse_mode="Markdown")
        else:
            bot.reply_to(message, "❌ يرجى الرد على رسالة الطالب بـ /ban أو كتابة الأمر متبوعاً بالآي دي.")

@bot.message_handler(commands=['unban'])
def unban_user(message):
    if message.chat.id in DB_STATE["admins"]:
        user_id = None
        if message.reply_to_message and message.reply_to_message.text:
            match = re.search(r'الآي دي:\\s*(\\d+)', message.reply_to_message.text)
            if match:
                user_id = int(match.group(1))
        elif len(message.text.split()) > 1:
            try: user_id = int(message.text.split()[1])
            except ValueError: pass
            
        if user_id and user_id in DB_STATE["banned"]:
            DB_STATE["banned"].remove(user_id)
            save_to_channel()
            bot.reply_to(message, f"✅ تم فك الحظر عن الآي دي `{user_id}`.", parse_mode="Markdown")
        else:
            bot.reply_to(message, "❌ هذا الطالب غير محظور أو لم يتم تحديد الآي دي بشكل صحيح.")

@bot.message_handler(commands=['deladmin'])
def del_admin(message):
    if message.chat.id == PRIMARY_ADMIN_ID:
        try:
            target_admin = int(message.text.split()[1])
            if target_admin == PRIMARY_ADMIN_ID:
                bot.reply_to(message, "❌ لا يمكنك حذف نفسك من الإدارة!")
                return
            if target_admin in DB_STATE["admins"]:
                DB_STATE["admins"].remove(target_admin)
                save_to_channel()
                bot.reply_to(message, f"🗑 تم إزالة الأدمن: `{target_admin}`", parse_mode="Markdown")
            else:
                bot.reply_to(message, "❌ هذا الآي دي غير موجود في قائمة الإدمنية.")
        except Exception:
            bot.reply_to(message, "❌ خطأ! الطريقة الصحيحة:\\n`/deladmin 123456789`", parse_mode="Markdown")

# ==========================================
# أوامر البوت الأساسية والأزرار
# ==========================================

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.chat.id
    
    if user_id not in DB_STATE["users"]:
        DB_STATE["users"].append(user_id)
        save_to_channel()

    if user_id in DB_STATE["admins"]:
        markup = telebot.types.InlineKeyboardMarkup()
        broadcast_btn = telebot.types.InlineKeyboardButton("📢 إذاعة رسالة للطلاب", callback_data="broadcast_mode")
        stats_btn = telebot.types.InlineKeyboardButton("📊 عدد المشتركين", callback_data="stats_mode")
        
        markup.add(broadcast_btn)
        
        if user_id == PRIMARY_ADMIN_ID:
            add_admin_btn = telebot.types.InlineKeyboardButton("➕ إضافة أدمن", callback_data="add_admin_mode")
            markup.row(stats_btn, add_admin_btn)
        else:
            markup.add(stats_btn)
            
        bot.reply_to(message, "أهلاً بك في لوحة الإدارة 👮‍♂️.\\n\\n👇 للتحكم السريع استخدم الأزرار:", reply_markup=markup)
    else:
        if user_id in DB_STATE["banned"]: return
        bot.reply_to(message, WELCOME_MESSAGE.format(name=message.from_user.first_name))

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    if call.data == "broadcast_mode" and call.message.chat.id in DB_STATE["admins"]:
        adding_admin_state[call.message.chat.id] = False
        broadcasting_admins[call.message.chat.id] = True
        bot.edit_message_text(
            "📢 **وضع الإذاعة مفعل:**\\nأرسل الآن الرسالة التي تريد إذاعتها (نص، صورة، أو ملف).\\n\\nلإلغاء الإذاعة أرسل كلمة: `الغاء`",
            chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="Markdown"
        )
    elif call.data == "stats_mode" and call.message.chat.id in DB_STATE["admins"]:
        bot.answer_callback_query(call.id, f"📊 إجمالي عدد الطلاب المفعلين للبوت: {len(DB_STATE['users'])} طالب", show_alert=True)
    elif call.data == "add_admin_mode" and call.message.chat.id == PRIMARY_ADMIN_ID:
        broadcasting_admins[call.message.chat.id] = False
        adding_admin_state[call.message.chat.id] = True
        bot.edit_message_text(
            "➕ **وضع إضافة أدمن:**\\nيرجى إرسال الآي دي (ID) الخاص بالأدمن الجديد الآن.\\n\\nلإلغاء العملية أرسل: `الغاء`",
            chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="Markdown"
        )

@bot.message_handler(func=lambda message: message.chat.id == PRIMARY_ADMIN_ID and adding_admin_state.get(message.chat.id, False))
def handle_add_admin_state(message):
    if message.text == 'الغاء':
        adding_admin_state[message.chat.id] = False
        bot.reply_to(message, "❌ تم إلغاء إضافة الأدمن.")
        return
    
    try:
        new_admin = int(message.text.strip())
        if new_admin not in DB_STATE["admins"]:
            DB_STATE["admins"].append(new_admin)
            save_to_channel()
        adding_admin_state[message.chat.id] = False
        bot.reply_to(message, f"✅ تم إضافة الأدمن بنجاح.\\nالآي دي: `{new_admin}`", parse_mode="Markdown")
    except ValueError:
        bot.reply_to(message, "❌ الرجاء إرسال أرقام فقط (الآي دي)، أو أرسل 'الغاء'.")

@bot.message_handler(func=lambda message: message.chat.id in DB_STATE["admins"] and broadcasting_admins.get(message.chat.id, False), content_types=['text', 'photo', 'video', 'document', 'audio', 'voice', 'sticker'])
def handle_broadcast_message(message):
    if message.content_type == 'text' and message.text == 'الغاء':
        broadcasting_admins[message.chat.id] = False
        bot.reply_to(message, "❌ تم إلغاء عملية الإذاعة.")
        return

    bot.reply_to(message, "⏳ جاري إذاعة الرسالة للطلاب، يرجى الانتظار...")
    success = 0
    for user_id in DB_STATE["users"]:
        if user_id not in DB_STATE["admins"]:
            try:
                bot.copy_message(user_id, message.chat.id, message.message_id)
                success += 1
            except: pass
                
    broadcasting_admins[message.chat.id] = False
    bot.reply_to(message, f"✅ تمت الإذاعة بنجاح ووصلت لـ {success} طالب.")

# ==========================================
# التواصل واستقبال الرسائل من الطلاب
# ==========================================

@bot.message_handler(func=lambda message: message.chat.id not in DB_STATE["admins"], content_types=['text', 'photo', 'video', 'document', 'audio', 'voice', 'sticker', 'animation', 'video_note', 'location', 'contact'])
def handle_user_message(message):
    user_id = message.from_user.id
    
    if user_id in DB_STATE["banned"]:
        return
        
    first_name = message.from_user.first_name
    
    if user_id not in DB_STATE["users"]:
        DB_STATE["users"].append(user_id)
        save_to_channel()
        
    markup = telebot.types.InlineKeyboardMarkup()
    user_btn = telebot.types.InlineKeyboardButton(f"👤 حساب {first_name}", url=f"tg://user?id={user_id}")
    markup.add(user_btn)
    
    bot.reply_to(message, "✅ تم استلام رسالتك وإرسالها للإدارة بنجاح.")
    
    for admin in DB_STATE["admins"]:
        try:
            if message.content_type == 'text':
                text = f"📩 رسالة من: {first_name}\\nالآي دي: `{user_id}`\\n\\n{message.text}"
                bot.send_message(admin, text, parse_mode="Markdown", reply_markup=markup)
            else:
                copied = bot.copy_message(admin, message.chat.id, message.message_id)
                bot.send_message(admin, f"👆 المرفق أعلاه من: {first_name}\\nالآي دي: `{user_id}`", parse_mode="Markdown", reply_markup=markup, reply_to_message_id=copied.message_id)
        except Exception: pass

@bot.message_handler(func=lambda message: message.chat.id in DB_STATE["admins"] and message.reply_to_message)
def reply_to_user(message):
    if message.text and message.text.startswith('/'):
        return
        
    reply_text = message.reply_to_message.text
    user_id = None
    
    if reply_text and "الآي دي:" in reply_text:
        match = re.search(r'الآي دي:\\s*(\\d+)', reply_text)
        if match: user_id = int(match.group(1))
            
    if user_id:
        try:
            if message.content_type == 'text':
                bot.send_message(user_id, message.text)
            else:
                bot.copy_message(user_id, message.chat.id, message.message_id)
                
            bot.reply_to(message, "✅ تم إرسال الرد للطالب بنجاح.")
            
            admin_name = message.from_user.first_name
            for admin in DB_STATE["admins"]:
                if str(admin) != str(message.chat.id):
                    if message.content_type == 'text':
                        bot.send_message(admin, f"🔔 الإدمن **{admin_name}** رد على الآي دي: `{user_id}`\\n\\nنص الرد:\\n{message.text}", parse_mode="Markdown")
                    else:
                        copied = bot.copy_message(admin, message.chat.id, message.message_id)
                        bot.send_message(admin, f"🔔👆 الإدمن **{admin_name}** أرسل المرفق أعلاه للآي دي: `{user_id}`", parse_mode="Markdown", reply_to_message_id=copied.message_id)
        except Exception:
            bot.reply_to(message, "❌ فشل الإرسال، قد يكون الطالب حظر البوت.")
    else:
        bot.reply_to(message, "❌ تأكد أنك ترد (Reply) على رسالة تحتوي على الآي دي.")

# ==========================================
# دالة التشغيل المتوافقة مع المشغل الرئيسي bot.py
# ==========================================
def run():
    print("Bot 2 (Saqimmah) is running with Telegram Channel Cloud DB...")
    bot.infinity_polling(timeout=20, long_polling_timeout=20)
'''

with open("bot2.py", "w", encoding="utf-8") as f:
    f.write(bot2_final_code)

print("File bot2.py updated successfully with channel ID.")
