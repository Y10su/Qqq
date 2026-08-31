import json
import io
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ================= إعدادات البوت =================
BOT_TOKEN = "8979324057:AAG4Bk_3Stbm3RVcnTbkz5vD5LD2Ml3dRbE"  # التوكن الجديد
CHANNEL_ID = "-1004308948350"  # آيدي القناة (للاختبارات وقاعدة البيانات)
ADMIN_ID = 8145086924  # الآيدي الخاص بك

bot = telebot.TeleBot(BOT_TOKEN)

# متغيرات لتخزين قاعدة البيانات في الذاكرة
bot_db = {}
pinned_msg_id = None
# ================================================

# --- إدارة قاعدة البيانات عبر الرسالة المثبتة ---
def load_db_from_channel():
    """البحث عن رسالة مثبتة في القناة وتحميل قاعدة البيانات منها"""
    global bot_db, pinned_msg_id
    try:
        chat = bot.get_chat(CHANNEL_ID)
        pinned = chat.pinned_message
        if pinned and pinned.document and pinned.document.file_name == 'db.json':
            file_info = bot.get_file(pinned.document.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            bot_db = json.loads(downloaded_file.decode('utf-8'))
            pinned_msg_id = pinned.message_id
            print("✅ تم تحميل قاعدة البيانات من الرسالة المثبتة في القناة.")
            return
    except Exception as e:
        print(f"⚠️ لم يتم العثور على قاعدة بيانات مثبتة، سيتم إنشاء واحدة جديدة. ({e})")
    
    # إذا لم يجد ملف، ينشئ هيكل جديد فارغ
    bot_db = {"الترم الأول": {}, "الترم الثاني": {}}

def save_db_to_channel():
    """حفظ التحديثات وإرسال الملف للقناة وتثبيته"""
    global pinned_msg_id
    try:
        # تحويل القاموس إلى ملف JSON في الذاكرة
        json_str = json.dumps(bot_db, ensure_ascii=False, indent=2)
        file_stream = io.BytesIO(json_str.encode('utf-8'))
        file_stream.name = 'db.json'
        
        # إرسال الملف الجديد للقناة
        msg = bot.send_document(CHANNEL_ID, file_stream, caption="🔄 قاعدة بيانات البوت (محدثة تلقائياً)")
        
        # تثبيت الرسالة الجديدة
        bot.pin_chat_message(CHANNEL_ID, msg.message_id)
        
        # حذف الرسالة المثبتة القديمة لتنظيف القناة
        if pinned_msg_id:
            try:
                bot.delete_message(CHANNEL_ID, pinned_msg_id)
            except:
                pass
        
        pinned_msg_id = msg.message_id
        print("✅ تم تحديث وتثبيت قاعدة البيانات بنجاح.")
    except Exception as e:
        print(f"❌ خطأ في حفظ قاعدة البيانات: {e}")

# --- استخراج File ID (أداة سريعة للمالك) ---
@bot.message_handler(content_types=['document', 'photo'])
def handle_docs_for_id(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    # استخراج الـ ID سواء كان المستند ملف JSON أو صورة
    if message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name
    elif message.photo:
        file_id = message.photo[-1].file_id  # أعلى جودة
        file_name = "صورة"
        
    bot.reply_to(message, f"📌 الـ File ID لـ ({file_name}) هو:\n`{file_id}`\n\n(اضغط على الكود لنسخه)", parse_mode="Markdown")

# --- واجهة التحكم (للمالك فقط) ---
@bot.message_handler(commands=['start'])
def start_cmd(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "⛔️ عذراً، هذا البوت مخصص للاستخدام الشخصي فقط.")
        return
    
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("الترم الأول", callback_data="view_term_الترم الأول"),
               InlineKeyboardButton("الترم الثاني", callback_data="view_term_الترم الثاني"))
    markup.row(InlineKeyboardButton("➕ إضافة مادة جديدة", callback_data="add_content"))
    
    bot.reply_to(message, "👑 أهلاً بك في لوحة تحكم الإدارة.\nاختر ما تود القيام به:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if call.from_user.id != ADMIN_ID:
        return

    # استعراض الأترام
    if call.data.startswith("view_term_"):
        term = call.data.split("_")[2]
        markup = InlineKeyboardMarkup()
        # جلب الصفوف الموجودة داخل هذا الترم
        grades = bot_db.get(term, {})
        for grade in grades:
            markup.add(InlineKeyboardButton(grade, callback_data=f"view_grade_{term}_{grade}"))
        markup.add(InlineKeyboardButton("🔙 رجوع", callback_data="back_to_start"))
        
        bot.edit_message_text(f"📚 {term}\nاختر الصف:", call.message.chat.id, call.message.message_id, reply_markup=markup)

    # زر الرجوع
    elif call.data == "back_to_start":
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("الترم الأول", callback_data="view_term_الترم الأول"),
                   InlineKeyboardButton("الترم الثاني", callback_data="view_term_الترم الثاني"))
        markup.row(InlineKeyboardButton("➕ إضافة مادة جديدة", callback_data="add_content"))
        bot.edit_message_text("👑 أهلاً بك في لوحة تحكم الإدارة.\nاختر ما تود القيام به:", call.message.chat.id, call.message.message_id, reply_markup=markup)

    # بدء عملية الإضافة
    elif call.data == "add_content":
        msg = bot.send_message(call.message.chat.id, "حدد الترم (اكتب 'الترم الأول' أو 'الترم الثاني'):")
        bot.register_next_step_handler(msg, add_step_1_term)

# --- سلسلة الإضافة الديناميكية ---
def add_step_1_term(message):
    term = message.text
    if term not in ["الترم الأول", "الترم الثاني"]:
        bot.send_message(message.chat.id, "❌ خطأ: يجب أن تكتب 'الترم الأول' أو 'الترم الثاني'. أعد المحاولة من البداية.")
        return
    msg = bot.send_message(message.chat.id, f"✅ تم اختيار {term}.\nالآن، اكتب اسم الصف (مثال: أول ثانوي):")
    bot.register_next_step_handler(msg, add_step_2_grade, term)

def add_step_2_grade(message, term):
    grade = message.text
    msg = bot.send_message(message.chat.id, f"✅ تم تسجيل: {grade}.\nالآن، اكتب اسم المادة (مثال: كيمياء):")
    bot.register_next_step_handler(msg, add_step_3_subject, term, grade)

def add_step_3_subject(message, term, grade):
    subject = message.text
    msg = bot.send_message(message.chat.id, f"✅ تم تسجيل: {subject}.\nالآن، اكتب اسم الفصل (مثال: الفصل الأول - مقدمة):")
    bot.register_next_step_handler(msg, add_step_4_chapter, term, grade, subject)

def add_step_4_chapter(message, term, grade, subject):
    chapter = message.text
    msg = bot.send_message(message.chat.id, f"✅ تم تسجيل: {chapter}.\nالخطوة الأخيرة: أرسل الـ File ID لملف الكويز (JSON) الخاص بهذا الفصل:")
    bot.register_next_step_handler(msg, add_step_5_finish, term, grade, subject, chapter)

def add_step_5_finish(message, term, grade, subject, chapter):
    file_id = message.text
    
    # بناء الشجرة الهرمية إذا لم تكن موجودة
    if grade not in bot_db[term]:
        bot_db[term][grade] = {}
    if subject not in bot_db[term][grade]:
        bot_db[term][grade][subject] = {}
        
    # إضافة الـ File ID للفصل
    bot_db[term][grade][subject][chapter] = file_id
    
    bot.send_message(message.chat.id, f"🎉 تمت الإضافة بنجاح!\n\nالترم: {term}\nالصف: {grade}\nالمادة: {subject}\nالفصل: {chapter}\n\nجاري تحديث قاعدة البيانات في القناة...")
    
    # حفظ التحديثات في القناة
    save_db_to_channel()

if __name__ == '__main__':
    # 1. تحميل قاعدة البيانات من القناة بمجرد التشغيل
    print("⏳ جاري فحص القناة للبحث عن قاعدة البيانات...")
    load_db_from_channel()
    
    # 2. تشغيل البوت
    print("🤖 البوت يعمل الآن ويستمع للطلبات...")
    bot.infinity_polling(skip_pending=True)
