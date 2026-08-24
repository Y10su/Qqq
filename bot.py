import os
import threading
import time
from flask import Flask

# استيراد ملفات البوتات
try:
    import bot1
except ImportError:
    bot1 = None

try:
    import bot2
except ImportError:
    bot2 = None

app = Flask(__name__)

@app.route('/')
def home():
    return "Bots are running successfully!"

def run_bot1():
    if bot1 and hasattr(bot1, 'run'):
        print("[INFO] Starting Bot 1 (Saqimmah)...")
        while True:
            try:
                bot1.run()
            except Exception as e:
                print(f"[ERROR] Bot 1 crashed: {e}. Restarting in 10 seconds...")
                time.sleep(10)

def run_bot2():
    if bot2 and hasattr(bot2, 'run'):
        print("[INFO] Starting Bot 2 (Userbot Manager)...")
        while True:
            try:
                bot2.run()
            except Exception as e:
                print(f"[ERROR] Bot 2 crashed: {e}. Restarting in 10 seconds...")
                time.sleep(10)

if __name__ == '__main__':
    # تأكد من أننا نشغل البوتات مرة واحدة فقط لتفادي خطأ 409
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        print("[INFO] Initializing bots threads...")
        
        if bot1:
            t1 = threading.Thread(target=run_bot1, daemon=True)
            t1.start()
            
        if bot2:
            t2 = threading.Thread(target=run_bot2, daemon=True)
            t2.start()

    # تشغيل خادم الويب
    port = int(os.environ.get('PORT', 10000))
    # نستخدم use_reloader=False لمنع Flask من تشغيل الكود مرتين
    app.run(host='0.0.0.0', port=port, use_reloader=False)
