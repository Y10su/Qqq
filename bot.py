import os
import sys
import threading
import importlib
import logging
from flask import Flask

# إعداد السجلات (Logs)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")
logger = logging.getLogger("BotRunner")

# 1. إعداد خادم Flask للربط مع Render ومنفذ الخدمة (Keep-Alive)
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ السيرفر يعمل بنجاح والبوتات نشطة!"

@app.route('/health')
def health():
    return {"status": "ok", "message": "Service is running"}, 200

def run_flask_server():
    # قراءة المنفذ تلقائياً من إعدادات Render أو استخدام 8080 كافتراضي
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"🚀 بدء تشغيل خادم الويب على المنفذ: {port}")
    app.run(host="0.0.0.0", port=port)

def safe_start_bot(module_name):
    """دالة لمحاولة استدعاء وتشغيل البوت بأمان بدون كراش إذا كان الملف فارغاً أو غير موجود"""
    try:
        # استدعاء الملف بشكل ديناميكي
        bot_module = importlib.import_module(module_name)
        
        # التأكد من وجود دالة التشغيل run داخل الملف
        if hasattr(bot_module, "run") and callable(getattr(bot_module, "run")):
            logger.info(f"▶️ جاري تشغيل البوت: [{module_name}.py] ...")
            try:
                bot_module.run()
            except Exception as e:
                logger.error(f"❌ خطأ أثناء تشغيل البوت [{module_name}]: {e}")
        else:
            logger.warning(f"⚠️ الملف [{module_name}.py] موجود لكن لا يحتوي على دالة run() أو فارغ - تم تخطيه بأمان.")
            
    except ModuleNotFoundError:
        logger.info(f"ℹ️ الملف [{module_name}.py] غير موجود - تم التخطي.")
    except Exception as e:
        logger.error(f"❌ حدث خطأ في تحميل الملف [{module_name}]: {e} - تم إكمال التشغيل لبقية البوتات.")

if __name__ == "__main__":
    logger.info("⚡ بدء تشغيل السيرفر الموحد وإدارة البوتات...")

    # قائمة ملفات البوتات الفرعية فقط: من bot1 إلى bot10
    bot_modules = [f"bot{i}" for i in range(1, 11)]

    # تشغيل كل بوت في خيط مستقل (Thread) معزول تماماً
    for module_name in bot_modules:
        bot_thread = threading.Thread(target=safe_start_bot, args=(module_name,), daemon=True)
        bot_thread.start()

    # تشغيل سيرفر الويب لـ Render لإبقاء الخدمة متصلة بالبورت
    run_flask_server()
