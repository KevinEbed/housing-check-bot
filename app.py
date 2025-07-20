from flask import Flask, render_template, request, redirect
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import requests
import smtplib
from email.mime.text import MIMEText
import threading
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Flask setup
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///urls.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# SQLAlchemy model
class URL(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(300), nullable=False)
    status = db.Column(db.String(10), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<URL {self.url}>"

# Send Telegram alert
def send_telegram_message(message):
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            data = {
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message
            }
            requests.post(url, data=data)
        except Exception as e:
            print("Telegram Error:", e)

# Send email alert
def send_email(subject, body):
    if EMAIL_SENDER and EMAIL_PASSWORD and EMAIL_RECEIVER:
        try:
            msg = MIMEText(body)
            msg['Subject'] = subject
            msg['From'] = EMAIL_SENDER
            msg['To'] = EMAIL_RECEIVER

            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.login(EMAIL_SENDER, EMAIL_PASSWORD)
                server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
        except Exception as e:
            print("Email Error:", e)

# Monitor URLs in a background thread
def monitor_websites():
    while True:
        urls = URL.query.all()
        for url_obj in urls:
            try:
                response = requests.get(url_obj.url, timeout=5)
                new_status = "UP" if response.status_code == 200 else "DOWN"
            except:
                new_status = "DOWN"

            if url_obj.status != new_status:
                message = f"{url_obj.url} is now {new_status}"
                send_telegram_message(message)
                send_email("Website Status Alert", message)
                if new_status == "DOWN":
                    # Remove URL from DB if DOWN
                    db.session.delete(url_obj)
                    db.session.commit()
                    continue
                else:
                    url_obj.status = new_status
                    db.session.commit()
        import time
        time.sleep(60)

# Flask Routes
@app.route('/')
def index():
    urls = URL.query.order_by(URL.created_at.desc()).all()
    return render_template('index.html', urls=urls)

@app.route('/add', methods=['POST'])
def add_url():
    url = request.form.get('url')
    if url:
        try:
            response = requests.get(url, timeout=5)
            status = "UP" if response.status_code == 200 else "DOWN"
        except:
            status = "DOWN"
        new_url = URL(url=url, status=status)
        db.session.add(new_url)
        db.session.commit()
    return redirect('/')

@app.route('/delete/<int:url_id>')
def delete_url(url_id):
    url_obj = URL.query.get_or_404(url_id)
    db.session.delete(url_obj)
    db.session.commit()
    return redirect('/')

# Start monitoring in a background thread
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    monitor_thread = threading.Thread(target=monitor_websites)
    monitor_thread.daemon = True
    monitor_thread.start()
    app.run(host='0.0.0.0', port=8080)
