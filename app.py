from flask import Flask, render_template, request, redirect, send_from_directory, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import threading
import requests
import time
import hashlib
import os
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from PIL import Image
import numpy as np

load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///urls.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SCREENSHOTS_DIR = "/app/screenshots"
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

print(f"DEBUG - TELEGRAM_TOKEN: {TELEGRAM_TOKEN}")
print(f"DEBUG - TELEGRAM_CHAT_ID: {TELEGRAM_CHAT_ID}")

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    raise ValueError("Missing TELEGRAM_TOKEN or TELEGRAM_CHAT_ID environment variables")

class URL(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    link = db.Column(db.String(500), nullable=False)
    last_hash = db.Column(db.String(64), nullable=True)
    last_screenshot = db.Column(db.String(255), nullable=True)
    interval = db.Column(db.Integer, default=60)  # Configurable interval in seconds
    alerted = db.Column(db.Boolean, default=False)

with app.app_context():
    db.create_all()

def get_screenshot_filename(url):
    url_hash = hashlib.md5(url.encode()).hexdigest()
    timestamp = int(time.time())
    return os.path.join(SCREENSHOTS_DIR, f"{url_hash}_{timestamp}.png")

def take_screenshot(url):
    try:
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.binary_location = os.getenv("CHROME_BIN", "/usr/bin/chromium")
        service = Service(os.getenv("CHROMEDRIVER_PATH", "/usr/lib/chromium-browser/chromedriver"))
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_window_size(1280, 720)
        driver.get(url)
        time.sleep(5)
        screenshot_path = get_screenshot_filename(url)
        driver.save_screenshot(screenshot_path)
        driver.quit()
        if os.path.exists(screenshot_path):
            print(f"[INFO] Screenshot saved: {screenshot_path}")
            return screenshot_path
        return None
    except Exception as e:
        print(f"[ERROR] Screenshot failed for {url}: {e}")
        return None

def compare_screenshots(img1_path, img2_path, threshold=0.1):
    try:
        img1 = Image.open(img1_path).convert("RGB").resize((1280, 720))
        img2 = Image.open(img2_path).convert("RGB").resize((1280, 720))
        arr1 = np.array(img1)
        arr2 = np.array(img2)
        mse = np.mean((arr1 - arr2) ** 2)
        difference = mse / (255 ** 2)
        print(f"[INFO] MSE: {mse:.2f}, Normalized: {difference:.4f}")
        return difference > threshold, difference
    except Exception as e:
        print(f"[ERROR] Image comparison failed: {e}")
        return False, 0.0

def send_telegram_alert(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message})
        print("[INFO] Telegram alert sent.")
    except Exception as e:
        print(f"[ERROR] Failed to send Telegram alert: {e}")

def monitor_websites():
    while True:
        with app.app_context():
            urls = URL.query.all()
            now = time.time()
            for url_obj in urls:
                if not url_obj.alerted or now - time.time() >= url_obj.interval:  # Reset or check interval
                    try:
                        response = requests.get(url_obj.link, timeout=10)
                        content_hash = hashlib.sha256(response.text.encode()).hexdigest()
                        content_change = url_obj.last_hash and content_hash != url_obj.last_hash

                        new_shot = take_screenshot(url_obj.link)
                        visual_change = False
                        mse_value = 0.0
                        if new_shot and url_obj.last_screenshot and os.path.exists(url_obj.last_screenshot):
                            visual_change, mse_value = compare_screenshots(url_obj.last_screenshot, new_shot)

                        if (content_change or visual_change) and url_obj.link:
                            alert = f"Website changed: {url_obj.link}\nTime: {datetime.utcnow()}"
                            if visual_change:
                                alert += f"\nVisual change detected! MSE: {mse_value:.4f}"
                            send_telegram_alert(alert)
                            url_obj.alerted = True
                        elif not (content_change or visual_change):
                            url_obj.alerted = False  # Reset alerted if no change

                        if new_shot:
                            if url_obj.last_screenshot and os.path.exists(url_obj.last_screenshot):
                                os.remove(url_obj.last_screenshot)
                            url_obj.last_screenshot = new_shot
                        url_obj.last_hash = content_hash
                        url_obj.last_checked = datetime.utcnow()
                        db.session.commit()
                        print(f"[INFO] Checked {url_obj.link} at {datetime.utcnow()}")
                    except Exception as e:
                        print(f"[ERROR] Error checking {url_obj.link}: {e}")
                        time.sleep(5)  # Brief pause on error
            time.sleep(5)  # Minimum sleep to prevent tight loop

@app.route('/')
def index():
    urls = URL.query.all()
    return render_template('index.html', urls=urls)

@app.route('/add', methods=['POST'])
def add():
    link = request.form.get('link')
    interval = request.form.get('interval', type=int, default=60)
    if link:
        parsed = urlparse(link)
        if parsed.scheme and parsed.netloc:
            new_url = URL(link=link, interval=interval)
            db.session.add(new_url)
            db.session.commit()
    return redirect('/')

@app.route('/delete/<int:url_id>')
def delete(url_id):
    url = URL.query.get_or_404(url_id)
    if url.last_screenshot and os.path.exists(url.last_screenshot):
        os.remove(url.last_screenshot)
    db.session.delete(url)
    db.session.commit()
    return redirect('/')

@app.route('/screenshots/<path:filename>')
def serve_screenshot(filename):
    try:
        return send_from_directory(SCREENSHOTS_DIR, filename)
    except Exception as e:
        print(f"[ERROR] Failed to serve screenshot: {e}")
        return "Screenshot not found", 404

# Start background monitor thread
monitor_thread = threading.Thread(target=monitor_websites, daemon=True)
monitor_thread.start()

if __name__ == '__main__':
    app.run(debug=False, host="0.0.0.0", port=8080)
