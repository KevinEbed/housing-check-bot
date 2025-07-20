from flask import Flask, render_template, request, redirect
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import requests
import smtplib
from email.mime.text import MIMEText
import threading
import os
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
    last_checked = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(10), nullable=True)

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
    with app.app_context():  # Add this line
        while True:
            urls = URL.query.all()
            # Your monitoring logic here
            time.sleep(60)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        url = request.form['url']
        if url:
            new_url = URL(address=url, last_checked=None, status=None)
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
