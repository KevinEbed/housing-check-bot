from flask import Flask, render_template, request, redirect
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import requests
import hashlib
import os
import smtplib
import threading
import time
from email.mime.text import MIMEText
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager

load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///urls.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Email and Telegram setup
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

class URL(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    interval = db.Column(db.Integer, default=60)
    last_checked = db.Column(db.DateTime)
    status = db.Column(db.String(20))
    last_screenshot = db.Column(db.String(255))
    last_hash = db.Column(db.String(64))  # ✅ Added for change detection

# Create the DB
with app.app_context():
    db.create_all()

# Get hash of a screenshot file
def get_file_hash(filepath):
    hasher = hashlib.sha256()
    with open(filepath, 'rb') as f:
        buf = f.read()
        hasher.update(buf)
    return hasher.hexdigest()

# Capture screenshot and return file path
def take_screenshot(url, filename):
    options = Options()
    options.headless = True
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
    driver.set_window_size(1920, 1080)
    driver.get(url)
    time.sleep(3)
    filepath = os.path.join('static/screenshots', filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    driver.save_screenshot(filepath)
    driver.quit()
    return filepath

# Email alert
def send_email_alert(url):
    subject = "Website Change Detected"
    body = f"The content of {url} has changed."
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECEIVER

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.send_message(msg)
        print("Email alert sent")
    except Exception as e:
        print(f"Error sending email: {e}")

# Telegram alert
def send_telegram_alert(url):
    message = f"🔔 Website Change Detected:\n{url}"
    telegram_api = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(telegram_api, data={'chat_id': TELEGRAM_CHAT_ID, 'text': message})
        print("Telegram alert sent")
    except Exception as e:
        print(f"Error sending Telegram message: {e}")

# Monitoring loop
def monitor_websites():
    while True:
        with app.app_context():
            urls = URL.query.filter_by(is_active=True).all()
            for url_obj in urls:
                try:
                    now = datetime.now()
                    if url_obj.last_checked is None or (now - url_obj.last_checked).seconds >= url_obj.interval:
                        print(f"[{now}] Checking {url_obj.url}...")
                        response = requests.get(url_obj.url, timeout=10)
                        url_obj.status = str(response.status_code)
                        filename = f"{url_obj.id}_{int(now.timestamp())}.png"
                        screenshot_path = take_screenshot(url_obj.url, filename)
                        new_hash = get_file_hash(screenshot_path)

                        if url_obj.last_hash and new_hash != url_obj.last_hash:
                            print("Change detected!")
                            send_email_alert(url_obj.url)
                            send_telegram_alert(url_obj.url)
                        else:
                            print("No change.")

                        url_obj.last_checked = now
                        url_obj.last_screenshot = screenshot_path
                        url_obj.last_hash = new_hash
                        db.session.commit()
                except Exception as e:
                    print(f"Error checking {url_obj.url}: {e}")
        time.sleep(10)

# Routes
@app.route('/')
def index():
    urls = URL.query.all()
    return render_template('index.html', urls=urls)

@app.route('/add', methods=['POST'])
def add():
    url = request.form['url']
    interval = int(request.form.get('interval', 60))
    new_url = URL(url=url, interval=interval)
    db.session.add(new_url)
    db.session.commit()
    return redirect('/')

@app.route('/toggle/<int:url_id>')
def toggle(url_id):
    url = URL.query.get_or_404(url_id)
    url.is_active = not url.is_active
    db.session.commit()
    return redirect('/')

@app.route('/delete/<int:url_id>')
def delete(url_id):
    url = URL.query.get_or_404(url_id)
    db.session.delete(url)
    db.session.commit()
    return redirect('/')

if __name__ == '__main__':
    threading.Thread(target=monitor_websites, daemon=True).start()
    app.run(debug=False, host='0.0.0.0', port=8080)
