from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
import os
import requests
import threading
import time
import smtplib
from email.mime.text import MIMEText

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///urls.db'
db = SQLAlchemy(app)

# Email & Telegram config
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

class URL(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    address = db.Column(db.String(255), nullable=False)
    interval = db.Column(db.Integer, default=60)
    status = db.Column(db.String(10), default='UP')

# Ensure DB is created
with app.app_context():
    db.create_all()

def send_email_alert(url):
    msg = MIMEText(f"🚨 Website down: {url}")
    msg["Subject"] = "Website Monitor Alert"
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECEIVER
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.send_message(msg)
    except Exception as e:
        print(f"Email send error: {e}")

def send_telegram_alert(url):
    try:
        requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                     params={"chat_id": TELEGRAM_CHAT_ID, "text": f"🚨 Website down: {url}"})
    except Exception as e:
        print(f"Telegram send error: {e}")

def monitor_url(url_id):
    with app.app_context():
        url_obj = URL.query.get(url_id)
        while True:
            try:
                response = requests.get(url_obj.address, timeout=10)
                url_obj.status = 'UP' if response.status_code == 200 else 'DOWN'
            except:
                url_obj.status = 'DOWN'
                send_email_alert(url_obj.address)
                send_telegram_alert(url_obj.address)
            db.session.commit()
            time.sleep(url_obj.interval)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        address = request.form['address']
        interval = int(request.form['interval'])
        new_url = URL(address=address, interval=interval)
        db.session.add(new_url)
        db.session.commit()
        threading.Thread(target=monitor_url, args=(new_url.id,), daemon=True).start()
        return redirect(url_for('index'))
    urls = URL.query.all()
    return render_template('index.html', urls=urls)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
