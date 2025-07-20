from flask import Flask, request, redirect, url_for, render_template, send_from_directory
from flask_sqlalchemy import SQLAlchemy
import requests
import os
import smtplib
import threading
import time
from datetime import datetime
from email.mime.text import MIMEText
from dotenv import load_dotenv
from urllib.parse import urlparse
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from PIL import Image
import hashlib
import numpy as np

# Load environment variables
load_dotenv()

app = Flask(__name__, static_folder='static')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///urls.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

required_vars = [("EMAIL_SENDER", EMAIL_SENDER), ("EMAIL_PASSWORD", EMAIL_PASSWORD),
                 ("EMAIL_RECEIVER", EMAIL_RECEIVER), ("TELEGRAM_TOKEN", TELEGRAM_TOKEN),
                 ("TELEGRAM_CHAT_ID", TELEGRAM_CHAT_ID)]
missing = [name for name, val in required_vars if not val]
if missing:
    raise ValueError(f"Missing environment variables: {', '.join(missing)}")

SCREENSHOTS_DIR = "screenshots"
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

class URL(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    interval = db.Column(db.Integer, default=60)
    last_checked = db.Column(db.DateTime)
    status = db.Column(db.String(20))
    last_screenshot = db.Column(db.String(255))

def get_screenshot_filename(url, suffix=""):
    url_hash = hashlib.md5(url.encode()).hexdigest()
    return os.path.join(SCREENSHOTS_DIR, f"{url_hash}{suffix}.png")

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
        time.sleep(2)
        timestamp = int(time.time())
        screenshot_path = get_screenshot_filename(url, f"_{timestamp}")
        driver.save_screenshot(screenshot_path)
        driver.quit()
        print(f"[INFO] Screenshot saved: {screenshot_path}")
        return screenshot_path
    except Exception as e:
        print(f"[ERROR] Screenshot failed for {url}: {e}")
        return None

def compare_screenshots(img1_path, img2_path, threshold=0.1):
    try:
        print(f"[DEBUG] Comparing {img1_path} vs {img2_path}")
        img1 = Image.open(img1_path).convert("RGB").resize((1280, 720))
        img2 = Image.open(img2_path).convert("RGB").resize((1280, 720))
        arr1 = np.array(img1)
        arr2 = np.array(img2)
        mse = np.mean((arr1 - arr2) ** 2)
        difference = mse / (255 ** 2)
        print(f"[INFO] MSE: {mse:.2f}, Normalized: {difference:.4f}")
        return difference > threshold
    except Exception as e:
        print(f"[ERROR] Image comparison failed: {e}")
        return False

def send_email(subject, body):
    try:
        msg = MIMEText(body)
        msg['From'] = EMAIL_SENDER
        msg['To'] = EMAIL_RECEIVER
        msg['Subject'] = subject
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.send_message(msg)
        print("[INFO] Email sent.")
    except Exception as e:
        print(f"[ERROR] Failed to send email: {e}")

def send_telegram(message):
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                      data={"chat_id": TELEGRAM_CHAT_ID, "text": message})
        print("[INFO] Telegram message sent.")
    except Exception as e:
        print(f"[ERROR] Failed to send Telegram message: {e}")

def monitor_websites():
    with app.app_context():
        last_check = {}
        print("[INFO] Monitoring thread started.")
        while True:
            try:
                urls = URL.query.all()
                now = time.time()
                for url_obj in urls:
                    if not url_obj.is_active:
                        continue
                    last_time = last_check.get(url_obj.id, 0)
                    if now - last_time >= url_obj.interval:
                        try:
                            response = requests.get(url_obj.url, timeout=5)
                            status = "Up" if response.status_code == 200 else f"Down ({response.status_code})"
                        except Exception as e:
                            print(f"[ERROR] {url_obj.url} unreachable: {e}")
                            status = "Down"

                        new_shot = take_screenshot(url_obj.url)
                        visual_change = False
                        if new_shot and url_obj.last_screenshot and os.path.exists(url_obj.last_screenshot):
                            visual_change = compare_screenshots(url_obj.last_screenshot, new_shot)

                        if (url_obj.status != status or visual_change) and status != "Unknown":
                            alert = f"URL: {url_obj.url}\nStatus: {status}"
                            if visual_change:
                                alert += "\nVisual change detected!"
                            send_email("Website Status Alert", alert)
                            send_telegram(alert)

                        if new_shot:
                            old = url_obj.last_screenshot
                            url_obj.last_screenshot = new_shot
                            if old and os.path.exists(old):
                                try:
                                    os.remove(old)
                                except Exception as e:
                                    print(f"[ERROR] Could not delete old screenshot: {e}")

                        url_obj.status = status
                        url_obj.last_checked = datetime.utcnow()
                        try:
                            db.session.commit()
                            last_check[url_obj.id] = now
                            print(f"[INFO] Checked {url_obj.url}")
                        except Exception as e:
                            db.session.rollback()
                            print(f"[ERROR] Commit failed: {e}")

                sleep_time = min([u.interval for u in urls if u.is_active] or [60])
                print(f"[INFO] Sleeping for {sleep_time}s")
                time.sleep(sleep_time)

            except Exception as e:
                print(f"[ERROR] Monitor thread error: {e}")
                time.sleep(60)

@app.route('/')
def index():
    try:
        urls = URL.query.all()
        return render_template('index.html', urls=urls)
    except Exception as e:
        return f"Error: {e}", 500

@app.route('/add', methods=['POST'])
def add():
    url = request.form.get('url')
    interval = request.form.get('interval', type=int, default=60)
    parsed = urlparse(url)
    if not url or not parsed.scheme or not parsed.netloc:
        return "Invalid URL", 400
    try:
        new_url = URL(url=url, interval=interval)
        db.session.add(new_url)
        db.session.commit()
        return redirect(url_for('index'))
    except Exception as e:
        db.session.rollback()
        return f"Add failed: {e}", 500

@app.route('/start/<int:url_id>')
def start(url_id):
    try:
        url_obj = URL.query.get_or_404(url_id)
        url_obj.is_active = True
        db.session.commit()
        return redirect(url_for('index'))
    except Exception as e:
        db.session.rollback()
        return f"Start failed: {e}", 500

@app.route('/stop/<int:url_id>')
def stop(url_id):
    try:
        url_obj = URL.query.get_or_404(url_id)
        url_obj.is_active = False
        db.session.commit()
        return redirect(url_for('index'))
    except Exception as e:
        db.session.rollback()
        return f"Stop failed: {e}", 500

@app.route('/delete/<int:url_id>')
def delete(url_id):
    try:
        url_obj = URL.query.get_or_404(url_id)
        if url_obj.last_screenshot and os.path.exists(url_obj.last_screenshot):
            os.remove(url_obj.last_screenshot)
        db.session.delete(url_obj)
        db.session.commit()
        return redirect(url_for('index'))
    except Exception as e:
        db.session.rollback()
        return f"Delete failed: {e}", 500

@app.route('/screenshots/<path:filename>')
def serve_screenshot(filename):
    return send_from_directory(SCREENSHOTS_DIR, filename)

@app.route('/test-static')
def test_static():
    return send_from_directory(app.static_folder, 'style.css')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    threading.Thread(target=monitor_websites, daemon=True).start()
    app.run(host="0.0.0.0", port=8080, debug=True)
