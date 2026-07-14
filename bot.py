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

# ملف حفظ الإدمنية عشان ما ينحذفون لو طفى البوت
ADMINS_FILE = "admins.json"

def load_admins():
    """تحميل قائمة الإدمنية من الملف"""
    if os.path.exists(ADMINS_FILE):
        with open(ADMINS_FILE, 'r') as f:
            try:
                return set(json.load(f))
            except:
                pass
    return {PRIMARY_ADMIN_ID}

def save_admins(admins_set):
    """حفظ قائمة الإدمنية في الملف"""
    with open(ADMINS_FILE, 'w') as f:
        json.dump(list(admins_set), f)

# تحميل الإدمنية عند التشغيل
ADMINS = load_admins()

bot = telebot.TeleBot(BOT_TOKEN)

WELCOME_MESSAGE = """أهلًا بك {name} في بوت قمة للقدرات لاستقبال التسريبات ✨

🔴 يرجى إرسال أي أسئلة أو أفكار تذكرها في اختبارك أو رأيتها في مواقع التواصل وردت في الاختبار، حتى نقوم بتجميعها وتنقيحها ونشرها وإفادة الطلاب 👍💛

🔴 تقدر ترسل جزء من السؤال إذا ما تذكره كامل 👌

🔴 التسريبات سيتم نشرها في @Saqimmah"""

# ==========================================
# أوامر الإدارة (خاصة بالمدير الأساسي فقط)
# ==========================================

@bot.message_handler(commands=['addadmin'])
def add_admin(message):
    """إضافة أدمن جديد عبر الآي دي"""
    if message.chat.id == PRIMARY_ADMIN_ID:
        try:
            # استخراج الآي دي من الأمر (مثال: /addadmin 123456)
            new_admin = int(message.text.split()[1])
            ADMINS.add(new_admin)
            save_admins(ADMINS)
            bot.reply_to(message, f"✅ تم إضافة الأدمن بنجاح.\nالآي دي: `{new_admin}`", parse_mode="Markdown")
        except Exception:
            bot.reply_to(message, "❌ خطأ! الطريقة الصحيحة للإضافة هي كتابة الأمر متبوعاً بالآي دي.\nمثال:\n`/addadmin 123456789`", parse_mode="Markdown")
    else:
        bot.reply_to(message, "⛔️ هذا الأمر مخصص للمدير الأساسي فقط.")

@bot.message_handler(commands=['deladmin'])
def del_admin(message):
    """حذف أدمن"""
    if message.chat.id == PRIMARY_ADMIN_ID:
        try:
            target_admin = int(message.text.split()[1])
            if target_admin == PRIMARY_ADMIN_ID:
                bot.reply_to(message, "❌ لا يمكنك حذف نفسك من الإدارة!")
                return
            
            if target_admin in ADMINS:
                ADMINS.remove(target_admin)
                save_admins(ADMINS)
                bot.reply_to(message, f"🗑 تم إزالة الأدمن: `{target_admin}`", parse_mode="Markdown")
            else:
                bot.reply_to(message, "❌ هذا الآي دي غير موجود في قائمة الإدمنية.")
        except Exception:
            bot.reply_to(message, "❌ خطأ! الطريقة الصحيحة:\n`/deladmin 123456789`", parse_mode="Markdown")

@bot.message_handler(commands=['adminlist'])
def list_admins(message):
    """عرض قائمة الإدمنية"""
    if message.chat.id == PRIMARY_ADMIN_ID:
        text = "📋 **قائمة الإدمنية الحاليين:**\n\n"
        for admin in ADMINS:
            text += f"- `{admin}`\n"
        bot.reply_to(message, text, parse_mode="Markdown")

# ==========================================
# أوامر البوت الأساسية واستقبال الرسائل
# ==========================================

@bot.message_handler(commands=['start'])
def send_welcome(message):
    if message.chat.id in ADMINS:
        bot.reply_to(message, "أهلاً بك في لوحة الإدارة. أنت مسجل كأدمن في هذا البوت 👮‍♂️.")
    else:
        bot.reply_to(message, WELCOME_MESSAGE.format(name=message.from_user.first_name))

# استلام كافة أنواع الملفات والميديا
@bot.message_handler(func=lambda message: message.chat.id not in ADMINS, content_types=['text', 'photo', 'video', 'document', 'audio', 'voice', 'sticker', 'animation', 'video_note', 'location', 'contact'])
def handle_user_message(message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    
    for admin in ADMINS:
        try:
            if message.content_type == 'text':
                text = f"📩 رسالة من: {first_name}\nالآي دي: `{user_id}`\n\n{message.text}"
                bot.send_message(admin, text, parse_mode="Markdown")
            else:
                # نستخدم copy_message لنسخ الملفات بدون تحميلها على السيرفر
                bot.copy_message(admin, message.chat.id, message.message_id)
                bot.send_message(admin, f"👆 المرفق أعلاه من: {first_name}\nالآي دي: `{user_id}`", parse_mode="Markdown")
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
            # 1. إرسال الرد للطالب
            if message.content_type == 'text':
                bot.send_message(user_id, message.text)
            else:
                # في حال قام الأدمن بالرد بصورة أو ملف أو ملصق
                bot.copy_message(user_id, message.chat.id, message.message_id)
                
            bot.reply_to(message, "✅ تم إرسال الرد للطالب بنجاح.")
            
            # 2. إشعار بقية الإدمنية
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
        bot.reply_to(message, "❌ تأكد أنك ترد على رسالة تحتوي على الآي دي.")

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
