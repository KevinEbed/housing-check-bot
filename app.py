from flask import Flask, request, redirect, render_template_string
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
            urls = URL.query.all()
            for url_obj in urls:
                if url_obj.is_active:
                    try:
                        response = requests.get(url_obj.url, timeout=5)
                        status = "Up" if response.status_code == 200 else f"Down ({response.status_code})"
                    except Exception:
                        status = "Down"

                    if url_obj.status != status:
                        alert = f"URL: {url_obj.url} changed status to {status}"
                        send_email("Website Status Alert", alert)
                        send_telegram(alert)
                        url_obj.status = status
                        url_obj.last_checked = datetime.utcnow()
                        db.session.commit()
            import time
            time.sleep(60)

@app.route('/')
def index():
    urls = URL.query.all()
    return render_template('index.html', urls=urls)

@app.route('/add', methods=['POST'])
def add():
    url = request.form['url']
    if not url:
        return "Missing URL", 400
    new_url = URL(url=url)
    db.session.add(new_url)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/toggle/<int:url_id>')
def toggle(url_id):
    url_obj = URL.query.get_or_404(url_id)
    url_obj.is_active = not url_obj.is_active
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/delete/<int:url_id>')
def delete(url_id):
    url_obj = URL.query.get_or_404(url_id)
    db.session.delete(url_obj)
    db.session.commit()
    return redirect(url_for('index'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    threading.Thread(target=monitor_websites, daemon=True).start()
    app.run(host="0.0.0.0", port=8080)
