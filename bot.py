import telebot
import re
import os
import json
from flask import Flask
from threading import Thread

# ==========================================
# الإعدادات الأساسية
# ==========================================
BOT_TOKEN = "8938474760:AAHBLfDoV_d1D8EKhYmSRocCpVTimbDpUgk"

# الآي دي الخاص بك أنت (المدير الأساسي الوحيد اللي يقدر يضيف إدمنية)
PRIMARY_ADMIN_ID = 8145086924  

# ملفات الحفظ
ADMINS_FILE = "admins.json"
USERS_FILE = "users.json" # ملف جديد لحفظ الطلاب للإذاعة

def load_data(filename, default_data):
    """دالة عامة لتحميل البيانات من الملفات"""
    if os.path.exists(filename):
        with open(filename, 'r') as f:
            try:
                return set(json.load(f))
            except:
                pass
    return default_data

def save_data(filename, data_set):
    """دالة عامة لحفظ البيانات"""
    with open(filename, 'w') as f:
        json.dump(list(data_set), f)

# تحميل الإدمنية والطلاب عند التشغيل
ADMINS = load_data(ADMINS_FILE, {PRIMARY_ADMIN_ID})
USERS = load_data(USERS_FILE, set())

# قاموس لتتبع حالة الإدمنية (هل هو في وضع الإذاعة أم لا)
broadcasting_admins = {}

bot = telebot.TeleBot(BOT_TOKEN)

WELCOME_MESSAGE = """أهلًا بك {name} في بوت قمة للقدرات لتجميع الاقسام  ✨

🔴 يرجى إرسال أي أسئلة أو أفكار تذكرها في اختبارك أو رأيتها في مواقع التواصل وردت في الاختبار، حتى نقوم بتجميعها وتنقيحها ونشرها وإفادة الطلاب 🩵

🔴 تقدر ترسل جزء من السؤال إذا ما تذكره كامل 👌

 @Saqimmah"""

# ==========================================
# أوامر الإدارة (خاصة بالمدير الأساسي فقط)
# ==========================================

@bot.message_handler(commands=['addadmin'])
def add_admin(message):
    if message.chat.id == PRIMARY_ADMIN_ID:
        try:
            new_admin = int(message.text.split()[1])
            ADMINS.add(new_admin)
            save_data(ADMINS_FILE, ADMINS)
            bot.reply_to(message, f"✅ تم إضافة الأدمن بنجاح.\nالآي دي: `{new_admin}`", parse_mode="Markdown")
        except Exception:
            bot.reply_to(message, "❌ خطأ! الطريقة الصحيحة للإضافة هي كتابة الأمر متبوعاً بالآي دي.\nمثال:\n`/addadmin 123456789`", parse_mode="Markdown")
    else:
        bot.reply_to(message, "⛔️ هذا الأمر مخصص للمدير الأساسي فقط.")

@bot.message_handler(commands=['deladmin'])
def del_admin(message):
    if message.chat.id == PRIMARY_ADMIN_ID:
        try:
            target_admin = int(message.text.split()[1])
            if target_admin == PRIMARY_ADMIN_ID:
                bot.reply_to(message, "❌ لا يمكنك حذف نفسك من الإدارة!")
                return
            
            if target_admin in ADMINS:
                ADMINS.remove(target_admin)
                save_data(ADMINS_FILE, ADMINS)
                bot.reply_to(message, f"🗑 تم إزالة الأدمن: `{target_admin}`", parse_mode="Markdown")
            else:
                bot.reply_to(message, "❌ هذا الآي دي غير موجود في قائمة الإدمنية.")
        except Exception:
            bot.reply_to(message, "❌ خطأ! الطريقة الصحيحة:\n`/deladmin 123456789`", parse_mode="Markdown")

@bot.message_handler(commands=['adminlist'])
def list_admins(message):
    if message.chat.id == PRIMARY_ADMIN_ID:
        text = "📋 **قائمة الإدمنية الحاليين:**\n\n"
        for admin in ADMINS:
            text += f"- `{admin}`\n"
        bot.reply_to(message, text, parse_mode="Markdown")

# ==========================================
# أوامر البوت الأساسية والإذاعة
# ==========================================

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.chat.id
    
    # حفظ الطالب في قائمة المستخدمين
    if user_id not in USERS:
        USERS.add(user_id)
        save_data(USERS_FILE, USERS)

    if user_id in ADMINS:
        # إضافة أزرار شفافة للإدارة
        markup = telebot.types.InlineKeyboardMarkup()
        broadcast_btn = telebot.types.InlineKeyboardButton("📢 إذاعة رسالة للطلاب", callback_data="broadcast_mode")
        markup.add(broadcast_btn)
        
        bot.reply_to(message, "أهلاً بك في لوحة الإدارة. أنت مسجل كأدمن في هذا البوت 👮‍♂️.\n\n👇 للتحكم السريع استخدم الأزرار:", reply_markup=markup)
    else:
        bot.reply_to(message, WELCOME_MESSAGE.format(name=message.from_user.first_name))

# التعامل مع الضغط على الأزرار الشفافة
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    if call.data == "broadcast_mode" and call.message.chat.id in ADMINS:
        broadcasting_admins[call.message.chat.id] = True
        bot.edit_message_text(
            "📢 **وضع الإذاعة مفعل:**\nأرسل الآن الرسالة التي تريد إذاعتها (نص، صورة، أو ملف).\n\nلإلغاء الإذاعة أرسل كلمة: `الغاء`",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode="Markdown"
        )

# استقبال رسالة الإذاعة من الأدمن
@bot.message_handler(func=lambda message: message.chat.id in ADMINS and broadcasting_admins.get(message.chat.id, False), content_types=['text', 'photo', 'video', 'document', 'audio', 'voice', 'sticker'])
def handle_broadcast_message(message):
    # إلغاء الإذاعة
    if message.content_type == 'text' and message.text == 'الغاء':
        broadcasting_admins[message.chat.id] = False
        bot.reply_to(message, "❌ تم إلغاء عملية الإذاعة.")
        return

    bot.reply_to(message, "⏳ جاري إذاعة الرسالة للطلاب، يرجى الانتظار...")
    
    success = 0
    for user_id in USERS:
        # لا ترسل الإذاعة للإدمنية
        if user_id not in ADMINS:
            try:
                bot.copy_message(user_id, message.chat.id, message.message_id)
                success += 1
            except:
                pass
                
    broadcasting_admins[message.chat.id] = False
    bot.reply_to(message, f"✅ تمت الإذاعة بنجاح ووصلت لـ {success} طالب.")

# ==========================================
# التواصل واستقبال الرسائل من الطلاب
# ==========================================

@bot.message_handler(func=lambda message: message.chat.id not in ADMINS, content_types=['text', 'photo', 'video', 'document', 'audio', 'voice', 'sticker', 'animation', 'video_note', 'location', 'contact'])
def handle_user_message(message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    
    # حفظ المستخدم احتياطاً
    if user_id not in USERS:
        USERS.add(user_id)
        save_data(USERS_FILE, USERS)
        
    # زر شفاف يوجه الأدمن لحساب الطالب
    markup = telebot.types.InlineKeyboardMarkup()
    user_btn = telebot.types.InlineKeyboardButton(f"👤 حساب {first_name}", url=f"tg://user?id={user_id}")
    markup.add(user_btn)
    
    # تأكيد الاستلام للطالب
    bot.reply_to(message, "✅ تم استلام رسالتك وإرسالها للإدارة بنجاح.")
    
    for admin in ADMINS:
        try:
            if message.content_type == 'text':
                text = f"📩 رسالة من: {first_name}\nالآي دي: `{user_id}`\n\n{message.text}"
                bot.send_message(admin, text, parse_mode="Markdown", reply_markup=markup)
            else:
                copied = bot.copy_message(admin, message.chat.id, message.message_id)
                bot.send_message(admin, f"👆 المرفق أعلاه من: {first_name}\nالآي دي: `{user_id}`", parse_mode="Markdown", reply_markup=markup, reply_to_message_id=copied.message_id)
        except Exception as e:
            print(f"فشل الإرسال للأدمن {admin}: {e}")

@bot.message_handler(func=lambda message: message.chat.id in ADMINS and message.reply_to_message)
def reply_to_user(message):
    reply_text = message.reply_to_message.text
    user_id = None
    
    if reply_text and "الآي دي:" in reply_text:
        match = re.search(r'الآي دي:\s*(\d+)', reply_text)
        if match:
            user_id = match.group(1)
            
    if user_id:
        try:
            if message.content_type == 'text':
                bot.send_message(user_id, message.text)
            else:
                bot.copy_message(user_id, message.chat.id, message.message_id)
                
            bot.reply_to(message, "✅ تم إرسال الرد للطالب بنجاح.")
            
            # إشعار بقية الإدمنية
            admin_name = message.from_user.first_name
            for admin in ADMINS:
                if str(admin) != str(message.chat.id):
                    if message.content_type == 'text':
                        notification = f"🔔 الإدمن **{admin_name}** رد على الآي دي: `{user_id}`\n\nنص الرد:\n{message.text}"
                        bot.send_message(admin, notification, parse_mode="Markdown")
                    else:
                        bot.copy_message(admin, message.chat.id, message.message_id)
                        bot.send_message(admin, f"🔔👆 الإدمن **{admin_name}** أرسل المرفق أعلاه للآي دي: `{user_id}`", parse_mode="Markdown")
        except Exception:
            bot.reply_to(message, "❌ فشل الإرسال، قد يكون الطالب حظر البوت.")
    else:
        # إذا لم يجد الآي دي في الرسالة المقتبسة
        bot.reply_to(message, "❌ تأكد أنك ترد (Reply) على رسالة تحتوي على الآي دي.")

# ==========================================
# إعداد الخادم (Port Bind) ليتوافق مع Render
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive and running!"

def run():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

if __name__ == "__main__":
    keep_alive()
    print("Bot is running...")
    bot.infinity_polling()
