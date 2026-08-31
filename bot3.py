import os
import json
import time
import telebot
from flask import Flask
from threading import Thread

# ================= إعدادات البوت =================
BOT_TOKEN = "8697790665:AAF2aEsbObT1ZSKrDiXiu0hnXJfL0MUcGU0"
# ايدي القناة العامة اللي بتنزل فيها الكويزات للطلاب
MAIN_CHANNEL_ID = "-1004308948350" 

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
# ================================================

# --- 1. خادم الويب المصغر (عشان ريندر و UptimeRobot) ---
@app.route('/')
def home():
    return "البوت يعمل بنجاح 🚀"

def run_flask():
    # المنفذ يتحدد تلقائياً من ريندر، أو يختار 8080 محلياً
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

# --- 2. منطق البوت (Telebot) ---

@bot.message_handler(commands=['start'])
def handle_start(message):
    bot.reply_to(
        message, 
        "👋 أهلاً بك يا مدير!\n\n"
        "قم بتحويل أي ملف JSON (قاعدة بيانات الأسئلة) من قناة البيانات إلى هنا، "
        "وسأقوم بقراءته ونشر الاختبار مباشرة في القناة العامة."
    )

@bot.message_handler(content_types=['document'])
def handle_document(message):
    """استقبال ملف الـ JSON، قراءته من الذاكرة، وبدء النشر"""
    
    # التأكد من أن الملف بصيغة JSON
    if message.document.mime_type != 'application/json' and not message.document.file_name.endswith('.json'):
        bot.reply_to(message, "⚠️ الرجاء إرسال ملف بصيغة JSON فقط.")
        return

    msg = bot.reply_to(message, "⏳ جاري تحميل الملف وقراءته من سيرفرات تيليجرام...")
    
    try:
        # تحميل الملف إلى الذاكرة (Memory) بدون حفظه في السيرفر
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        # تحويل البيانات إلى قاموس بايثون
        quiz_data = json.loads(downloaded_file.decode('utf-8'))
        
        if 'questions' not in quiz_data:
            bot.edit_message_text("❌ الملف لا يحتوي على أسئلة بالتنسيق الصحيح.", chat_id=message.chat.id, message_id=msg.message_id)
            return
            
        bot.edit_message_text(f"🚀 تم القراءة بنجاح!\nجاري نشر {len(quiz_data['questions'])} أسئلة في القناة العامة...", chat_id=message.chat.id, message_id=msg.message_id)
        
        # بدء عملية النشر للقناة
        post_quiz_to_channel(quiz_data)
        
        bot.send_message(message.chat.id, "✅ اكتمل نشر جميع الأسئلة في القناة بنجاح!")
        
    except Exception as e:
        bot.edit_message_text(f"❌ حدث خطأ أثناء المعالجة:\n{e}", chat_id=message.chat.id, message_id=msg.message_id)

def post_quiz_to_channel(data):
    """دالة لمعالجة الأسئلة وإرسالها للقناة"""
    
    lesson_name = data.get('collection_name', data.get('lesson_name', 'اختبار جديد'))
    
    # إرسال رسالة افتتاحية للكويز
    bot.send_message(MAIN_CHANNEL_ID, f"📝 **{lesson_name}**\nاستعد للإجابة...", parse_mode="Markdown")
    time.sleep(2)

    for q in data['questions']:
        q_text = q.get('question_text', '').strip()
        correct_idx = q.get('correct_option_index', 0)
        options = q.get('options', [])

        # 1. إرسال صور السؤال (إذا وجدت)
        q_images = q.get('image_file_ids', [])
        if q.get('image_file_id'):
            q_images.append(q.get('image_file_id'))
            
        for img_id in q_images:
            try:
                bot.send_document(MAIN_CHANNEL_ID, document=img_id, caption=f"🖼 تابع للسؤال رقم {q.get('question_number', '')}")
            except Exception as e:
                print(f"تعذر إرسال صورة السؤال: {e}")

        # 2. تجهيز الخيارات وإرسال صورها (إن وجدت)
        poll_options = []
        for idx, opt in enumerate(options):
            opt_text = opt.get('text', '').strip()
            
            # التعامل مع صور الخيارات
            opt_images = opt.get('images_file_ids', [])
            if opt.get('image_file_id'):
                opt_images.append(opt.get('image_file_id'))
                
            for img_id in opt_images:
                try:
                    # نرسلها كـ مستند للحفاظ على الجودة العالية
                    bot.send_document(MAIN_CHANNEL_ID, document=img_id, caption=f"🖼 خيار رقم {idx + 1}")
                except:
                    pass
            
            # إذا الخيار مافيه نص (صورة فقط)، نعطيه اسم بديل عشان يقبله الكويز
            if not opt_text:
                opt_text = f"الخيار {idx + 1}"
            
            poll_options.append(opt_text)

        # ضبط طول السؤال (تيليجرام لا يقبل أكثر من 300 حرف في الـ Poll)
        if len(q_text) > 290:
            display_q_text = q_text[:287] + "..."
        elif not q_text:
            display_q_text = f"السؤال رقم {q.get('question_number', '')}"
        else:
            display_q_text = q_text

        # 3. إرسال الكويز
        try:
            bot.send_poll(
                chat_id=MAIN_CHANNEL_ID,
                question=display_q_text,
                options=poll_options,
                type='quiz',
                correct_option_id=correct_idx,
                is_anonymous=True, # خليه True عشان الطلاب ما يشوفون إجابات بعض
                allows_multiple_answers=False
            )
        except Exception as e:
            print(f"خطأ في إرسال الكويز: {e}")

        # تأخير بين كل سؤال وسؤال لتجنب الحظر من تيليجرام (Flood Limit)
        time.sleep(3)

if __name__ == '__main__':
    # تشغيل سيرفر الويب في مسار (Thread) منفصل
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    print("🤖 البوت يعمل الآن ويستمع للرسائل...")
    # تم إضافة skip_pending=True لمسح أي رسائل قديمة وتجنب خطأ 409
    bot.infinity_polling(skip_pending=True)
