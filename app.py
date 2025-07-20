# FULL UPDATED FLASK APP WITH HASH + SCREENSHOT COMPARISON + RENDER TEMPLATE

from flask import Flask, request, redirect, render_template
from flask_sqlalchemy import SQLAlchemy
import requests
import hashlib
import os
import smtplib
import threading
import time
from datetime import datetime
from email.mime.text import MIMEText
from dotenv import load_dotenv

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import cv2
from PIL import Image
import numpy as np

# Load environment variables
load_dotenv()
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///urls.db'
db = SQLAlchemy(app)

class URL(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    link = db.Column(db.String(500), nullable=False)
    monitoring = db.Column(db.Boolean, default=False)
    interval = db.Column(db.Integer, default=60)

with app.app_context():
    db.create_all()

monitoring_threads = {}

def send_email(subject, body):
    msg = MIMEText(body)
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECEIVER
    msg['Subject'] = subject
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.send_message(msg)
        print("[INFO] Email sent.")
    except Exception as e:
        print(f"[ERROR] Failed to send email: {e}")

def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
        requests.post(url, data=payload)
        print("[INFO] Telegram message sent.")
    except Exception as e:
        print(f"[ERROR] Telegram error: {e}")

def take_screenshot(url, filename):
    try:
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        driver = webdriver.Chrome(ChromeDriverManager().install(), options=chrome_options)
        driver.set_window_size(1920, 1080)
        driver.get(url)
        time.sleep(2)
        driver.save_screenshot(filename)
        driver.quit()
        print(f"[SCREENSHOT] Saved {filename}")
        return True
    except Exception as e:
        print(f"[ERROR] Screenshot failed: {e}")
        return False

def images_different(img1_path, img2_path):
    try:
        img1 = cv2.imread(img1_path)
        img2 = cv2.imread(img2_path)
        if img1 is None or img2 is None:
            return False
        diff = cv2.absdiff(img1, img2)
        gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 30, 255, cv2.THRESH_BINARY)
        non_zero = cv2.countNonZero(thresh)
        return non_zero > 1000
    except Exception as e:
        print(f"[ERROR] Comparison failed: {e}")
        return False

def monitor_website(url, url_id, interval):
    print(f"[MONITORING STARTED] Monitoring thread launched for {url}")
    baseline_img = f"screenshots/{url_id}_baseline.png"
    os.makedirs("screenshots", exist_ok=True)

    # Initial fetch and screenshot
    try:
        resp = requests.get(url, timeout=10)
        hash_baseline = hashlib.md5(resp.content).hexdigest()
        print(f"[INIT] Initial hash for {url}: {hash_baseline}")
        if not take_screenshot(url, baseline_img):
            print(f"[ERROR] Couldn't capture baseline screenshot for {url}")
            return
        print(f"[INIT] Baseline screenshot saved at {baseline_img}")
    except Exception as e:
        print(f"[ERROR] Init fetch or screenshot failed for {url}: {e}")
        return

    if not os.path.isfile(baseline_img):
        print(f"[ERROR] Baseline screenshot file missing: {baseline_img}")
        return

    while True:
        with app.app_context():
            url_obj = db.session.get(URL, url_id)
            if not url_obj or not url_obj.monitoring:
                print(f"[INFO] Monitoring stopped for {url}")
                break

        time.sleep(interval)

        try:
            resp = requests.get(url, timeout=10)
            current_hash = hashlib.md5(resp.content).hexdigest()
            print(f"[CHECK] Current hash for {url}: {current_hash}")

            current_img = f"screenshots/{url_id}_current.png"
            if not take_screenshot(url, current_img):
                print(f"[ERROR] Couldn't take current screenshot for {url}")
                continue

            if not (os.path.exists(baseline_img) and os.path.exists(current_img)):
                print(f"[ERROR] Missing screenshot(s): {baseline_img}, {current_img}")
                continue

            visual_diff = images_different(baseline_img, current_img)
            print(f"[CHECK] Visual difference detected? {visual_diff}")

            if current_hash != hash_baseline or visual_diff:
                msg = f"🔔 Change detected on: {url} at {datetime.now():%Y-%m-%d %H:%M:%S}"
                print(f"[ALERT] {msg}")
                send_email("Website Changed", msg)
                send_telegram(msg)

                # Update baseline
                hash_baseline = current_hash
                os.replace(current_img, baseline_img)
                print("[INFO] Baseline updated with current screenshot.")
            else:
                print(f"[DEBUG] No change for {url}.")
        except Exception as e:
            print(f"[ERROR] Monitoring loop error for {url}: {e}")


@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        link = request.form['link']
        interval = int(request.form['interval'])
        if link and interval:
            new_url = URL(link=link, interval=interval)
            db.session.add(new_url)
            db.session.commit()
    urls = URL.query.all()
    return render_template("index.html", urls=urls)

@app.route('/start/<int:url_id>')
def start_monitoring(url_id):
    url_entry = URL.query.get_or_404(url_id)
    if not url_entry.monitoring:
        url_entry.monitoring = True
        db.session.commit()

        print(f"[THREAD] Preparing to launch monitor for URL ID: {url_id}")
        print(f"[THREAD] URL: {url_entry.link}, Interval: {url_entry.interval}")

        try:
            thread = threading.Thread(
                target=monitor_website,
                args=(url_entry.link, url_id, url_entry.interval),
                daemon=True
            )
            monitoring_threads[url_id] = thread
            thread.start()
            print(f"[THREAD] Thread started for URL ID: {url_id}")
        except Exception as e:
            print(f"[ERROR] Failed to start thread: {e}")
    else:
        print(f"[THREAD] Monitoring already active for URL ID: {url_id}")
    return redirect('/')



@app.route('/stop/<int:url_id>')
def stop_monitoring(url_id):
    url_entry = URL.query.get_or_404(url_id)
    url_entry.monitoring = False
    db.session.commit()
    return redirect('/')

@app.route('/delete/<int:url_id>')
def delete_url(url_id):
    url_entry = URL.query.get_or_404(url_id)
    if url_entry.monitoring:
        url_entry.monitoring = False
    db.session.delete(url_entry)
    db.session.commit()
    return redirect('/')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
