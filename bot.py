import os
import threading
import time
import asyncio
from flask import Flask

# التعديل الأهم: تهيئة Event Loop في الخيط الرئيسي قبل استيراد أي بوت
try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

# استيراد ملفات البوتات بعد التهيئة
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
    # نعطي كل Thread اللوب الخاص فيه
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    if bot1 and hasattr(bot1, 'run'):
        print("[INFO] Starting Bot 1 (Saqimmah)...")
        while True:
            try:
                bot1.run()
            except Exception as e:
                print(f"[ERROR] Bot 1 crashed: {e}. Restarting in 10 seconds...")
                time.sleep(10)

def run_bot2():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    if bot2 and hasattr(bot2, 'run'):
        print("[INFO] Starting Bot 2 (Userbot Manager)...")
        while True:
            try:
                bot2.run()
            except Exception as e:
                print(f"[ERROR] Bot 2 crashed: {e}. Restarting in 10 seconds...")
                time.sleep(10)

if __name__ == '__main__':
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        print("[INFO] Initializing bots threads...")
        
        if bot1:
            t1 = threading.Thread(target=run_bot1, daemon=True)
            t1.start()
            
        if bot2:
            t2 = threading.Thread(target=run_bot2, daemon=True)
            t2.start()

    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, use_reloader=False)
