from flask import Flask, render_template, request, redirect
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from dotenv import load_dotenv
from email.mime.text import MIMEText
import os
import smtplib
import threading
import hashlib
import time
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

load_dotenv()

# Load credentials
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///urls.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Model
class URL(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(500), nullable=False)
    last_hash = db.Column(db.String(64), nullable=True)
    last_checked = db.Column(db.DateTime, default=datetime.utcnow)

# Selenium setup
def get_rendered_html(url):
    options = Options()
    options.add_argument("--headless")
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')

    try:
        driver = webdriver.Chrome(options=options)
        driver.get(url)
        time.sleep(3)
        html = driver.page_source
        driver.quit()
        return html
    except Exception as e:
        print(f"Selenium error for {url}: {e}")
        return None

# Notification functions
def send_email(subject, body):
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = EMAIL_SENDER
        msg['To'] = EMAIL_RECEIVER

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
        print("Email sent.")
    except Exception as e:
        print("Failed to send email:", e)

def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
        requests.post(url, data=data)
        print("Telegram alert sent.")
    except Exception as e:
        print("Telegram error:", e)

# Monitor Function
def monitor_websites():
    while True:
        urls = URL.query.all()
        for url_obj in urls:
            url = url_obj.url
            html = get_rendered_html(url)
            if not html:
                continue

            current_hash = hashlib.sha256(html.encode()).hexdigest()
            if url_obj.last_hash and current_hash != url_obj.last_hash:
                msg = f"Change detected at: {url}"
                send_email("Website Content Changed!", msg)
                send_telegram(msg)
            url_obj.last_hash = current_hash
            url_obj.last_checked = datetime.utcnow()
            db.session.commit()
        time.sleep(60)  # Wait 60 seconds before next check

# Flask routes
@app.route('/', methods=['GET'])
def index():
    urls = URL.query.all()
    return render_template('index.html', urls=urls)

@app.route('/add', methods=['POST'])
def add_url():
    url = request.form.get('url')
    if url:
        html = get_rendered_html(url)
        if html:
            content_hash = hashlib.sha256(html.encode()).hexdigest()
            new_url = URL(url=url, last_hash=content_hash)
            db.session.add(new_url)
            db.session.commit()
    return redirect('/')

@app.route('/delete/<int:url_id>', methods=['GET'])
def delete_url(url_id):
    url_obj = db.session.get(URL, url_id)
    if url_obj:
        db.session.delete(url_obj)
        db.session.commit()
    return redirect('/')

# Main
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    threading.Thread(target=monitor_websites, daemon=True).start()
    app.run(debug=False, host='0.0.0.0', port=8080)
