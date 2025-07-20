from flask import Flask, render_template, request, redirect
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone
import requests
import threading
import os
import smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///urls.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Database model
class URL(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(2083), nullable=False)
    last_status = db.Column(db.String(10))
    last_checked = db.Column(db.DateTime)

with app.app_context():
    db.create_all()

# Function to send email alerts
def send_email_alert(url):
    msg = MIMEText(f"Alert: {url} is DOWN!")
    msg['Subject'] = "Website Down Alert"
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECEIVER

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(EMAIL_SENDER, EMAIL_PASSWORD)
            smtp.send_message(msg)
        print(f"[EMAIL] Alert sent for {url}")
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")

# Function to send Telegram alerts
def send_telegram_alert(url):
    message = f"🚨 ALERT: {url} is DOWN!"
    telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    
    try:
        response = requests.post(telegram_url, data=data)
        if response.status_code == 200:
            print(f"[TELEGRAM] Alert sent for {url}")
        else:
            print(f"[TELEGRAM ERROR] {response.text}")
    except Exception as e:
        print(f"[TELEGRAM EXCEPTION] {e}")

# Monitor thread function
def monitor_websites():
    with app.app_context():
        while True:
            urls = URL.query.all()
            for url_obj in urls:
                try:
                    response = requests.get(url_obj.url, timeout=5)
                    status = "UP" if response.status_code == 200 else "DOWN"
                except:
                    status = "DOWN"

                if url_obj.last_status != status and status == "DOWN":
                    send_email_alert(url_obj.url)
                    send_telegram_alert(url_obj.url)

                url_obj.last_status = status
                url_obj.last_checked = datetime.now(timezone.utc)
                db.session.commit()

            # Delay between checks
            threading.Event().wait(60)

# Routes
@app.route('/')
def index():
    urls = URL.query.all()
    return render_template('index.html', urls=urls)

@app.route('/add', methods=['POST'])
def add_url():
    new_url = request.form['url']
    url_obj = URL(url=new_url, last_status="Unknown", last_checked=datetime.now(timezone.utc))
    db.session.add(url_obj)
    db.session.commit()
    return redirect('/')

@app.route('/delete/<int:url_id>')
def delete_url(url_id):
    url_obj = URL.query.get(url_id)
    db.session.delete(url_obj)
    db.session.commit()
    return redirect('/')

# Run monitor in background thread
monitor_thread = threading.Thread(target=monitor_websites)
monitor_thread.daemon = True
monitor_thread.start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
