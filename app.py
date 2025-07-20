from flask import Flask, request, redirect, url_for, render_template
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

load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///urls.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Verify environment variables
if not all([EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECEIVER, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]):
    raise ValueError("One or more environment variables are missing. Check your .env file.")

class URL(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    last_checked = db.Column(db.DateTime)
    status = db.Column(db.String(20))

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
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message
        }
        requests.post(url, data=payload)
        print("[INFO] Telegram message sent.")
    except Exception as e:
        print(f"[ERROR] Failed to send Telegram message: {e}")

def monitor_websites():
    with app.app_context():
        while True:
            try:
                urls = URL.query.all()
                for url_obj in urls:
                    if url_obj.is_active:
                        try:
                            response = requests.get(url_obj.url, timeout=5)
                            status = "Up" if response.status_code == 200 else f"Down ({response.status_code})"
                        except Exception as e:
                            status = "Down"
                            print(f"[ERROR] Failed to check {url_obj.url}: {e}")
                        if url_obj.status != status:
                            alert = f"URL: {url_obj.url} changed status to {status}"
                            send_email("Website Status Alert", alert)
                            send_telegram(alert)
                            url_obj.status = status
                            url_obj.last_checked = datetime.utcnow()
                            try:
                                db.session.commit()
                            except Exception as e:
                                db.session.rollback()
                                print(f"[ERROR] Database commit failed: {e}")
                        time.sleep(1)  # Delay between requests
            except Exception as e:
                print(f"[ERROR] Monitor thread error: {e}")
            time.sleep(60)

@app.route('/')
def index():
    try:
        urls = URL.query.all()
        return render_template('index.html', urls=urls)
    except Exception as e:
        print(f"[ERROR] Index route error: {e}")
        return "Failed to load URLs", 500

@app.route('/add', methods=['POST'])
def add():
    url = request.form.get('url')
    if not url:
        return "Missing URL", 400
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return "Invalid URL", 400
    try:
        new_url = URL(url=url)
        db.session.add(new_url)
        db.session.commit()
        return redirect(url_for('index'))
    except Exception as e:
        db.session.rollback()
        print(f"[ERROR] Failed to add URL: {e}")
        return "Failed to add URL", 500

@app.route('/toggle/<int:url_id>')
def toggle(url_id):
    try:
        url_obj = URL.query.get_or_404(url_id)
        url_obj.is_active = not url_obj.is_active
        db.session.commit()
        return redirect(url_for('index'))
    except Exception as e:
        db.session.rollback()
        print(f"[ERROR] Failed to toggle URL: {e}")
        return "Failed to toggle URL", 500

@app.route('/delete/<int:url_id>')
def delete(url_id):
    try:
        url_obj = URL.query.get_or_404(url_id)
        db.session.delete(url_obj)
        db.session.commit()
        return redirect(url_for('index'))
    except Exception as e:
        db.session.rollback()
        print(f"[ERROR] Failed to delete URL: {e}")
        return "Failed to delete URL", 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    threading.Thread(target=monitor_websites, daemon=True).start()
    app.run(host="0.0.0.0", port=8080, debug=True)
