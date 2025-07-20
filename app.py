from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import requests
import threading
import os
from dotenv import load_dotenv
import smtplib
from email.mime.text import MIMEText


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

# Database Model
class URL(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(500), nullable=False)
    status = db.Column(db.String(10), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Monitor function
def monitor_websites():
    while True:
        with app.app_context():
            urls = URL.query.all()
            for url_obj in urls:
                try:
                    response = requests.get(url_obj.url, timeout=5)
                    new_status = 'UP' if response.status_code == 200 else 'DOWN'
                except:
                    new_status = 'DOWN'

                if url_obj.status != new_status:
                    send_telegram_message(f"{url_obj.url} is now {new_status}")
                    url_obj.status = new_status
                    db.session.commit()
        # Check every 60 seconds
        import time; time.sleep(60)

def send_telegram_message(message):
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message
        }
        try:
            requests.post(url, json=payload)
        except Exception as e:
            print("Telegram error:", e)

@app.route('/')
def index():
    urls = URL.query.order_by(URL.created_at.desc()).all()
    return render_template('index.html', urls=urls)

@app.route('/add', methods=['POST'])
def add_url():
    url = request.form['url']
    if url:
        new_url = URL(url=url)
        db.session.add(new_url)
        db.session.commit()
    return redirect('/')

@app.route('/delete/<int:url_id>')
def delete_url(url_id):
    url_obj = URL.query.get_or_404(url_id)
    db.session.delete(url_obj)
    db.session.commit()
    return redirect('/')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    threading.Thread(target=monitor_websites, daemon=True).start()
    app.run(debug=False, host='0.0.0.0', port=8000)
