from flask import Flask, render_template, request, redirect
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import requests
import smtplib
from email.mime.text import MIMEText
import threading
import os
import hashlib
import time
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///urls.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Environment variables
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

class URL(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    address = db.Column(db.String(2083), nullable=False)
    interval = db.Column(db.Integer, default=60)
    last_checked = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), nullable=True)
    content_hash = db.Column(db.String(64), nullable=True)

def get_hash(content):
    return hashlib.sha256(content.encode('utf-8')).hexdigest()

def send_email(subject, body):
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = EMAIL_SENDER
        msg['To'] = EMAIL_RECEIVER

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(EMAIL_SENDER, EMAIL_PASSWORD)
            smtp.send_message(msg)
        print("Email sent")
    except Exception as e:
        print("Email failed:", e)

def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
        requests.post(url, data=data)
        print("Telegram sent")
    except Exception as e:
        print("Telegram failed:", e)

def monitor_websites():
    with app.app_context():
        while True:
            urls = URL.query.all()
            for url in urls:
                try:
                    response = requests.get(url.address, timeout=10)
                    content = response.text
                    new_hash = get_hash(content)

                    if url.content_hash != new_hash:
                        url.content_hash = new_hash
                        url.status = "Changed"
                        send_email("Website Changed", f"{url.address} has changed.")
                        send_telegram(f"🔔 {url.address} has changed.")
                    else:
                        url.status = "Unchanged"

                    url.last_checked = datetime.utcnow()
                    db.session.commit()
                except Exception as e:
                    url.status = "Error"
                    db.session.commit()
                    print(f"Error checking {url.address}: {e}")
            time.sleep(60)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        address = request.form['address']
        interval = int(request.form['interval'])
        if address:
            new_url = URL(address=address, interval=interval)
            db.session.add(new_url)
            db.session.commit()
        return redirect('/')
    urls = URL.query.all()
    return render_template('index.html', urls=urls)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    threading.Thread(target=monitor_websites, daemon=True).start()
    app.run(host='0.0.0.0', port=8080)
