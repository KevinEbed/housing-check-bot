from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone
import requests, threading, time, os
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

class URL(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(2048), nullable=False)
    last_checked = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    status = db.Column(db.String(100), default="Not Checked")

db.create_all()

def monitor_websites():
    while True:
        urls = URL.query.all()
        for url_obj in urls:
            try:
                response = requests.get(url_obj.url, timeout=10)
                url_obj.status = "Up" if response.status_code == 200 else f"Down: {response.status_code}"
            except Exception as e:
                url_obj.status = f"Down: {e}"
                send_email(url_obj.url)
                send_telegram_message(url_obj.url)
            url_obj.last_checked = datetime.now(timezone.utc)
            db.session.commit()
        time.sleep(300)  # every 5 mins

def send_email(url):
    subject = f"Website Down: {url}"
    body = f"The website {url} appears to be down."
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECEIVER

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
        print("Email sent")
    except Exception as e:
        print(f"Email failed: {e}")

def send_telegram_message(url):
    message = f"🚨 The website {url} appears to be DOWN!"
    telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        response = requests.post(telegram_url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message
        })
        if response.status_code == 200:
            print("Telegram sent")
        else:
            print(f"Telegram failed: {response.text}")
    except Exception as e:
        print(f"Telegram error: {e}")

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        url = request.form.get("url")
        if url:
            new_url = URL(url=url)
            db.session.add(new_url)
            db.session.commit()
        return redirect(url_for("index"))
    urls = URL.query.all()
    return render_template("index.html", urls=urls)

@app.route("/delete/<int:url_id>", methods=["POST"])
def delete(url_id):
    url_obj = URL.query.get_or_404(url_id)
    db.session.delete(url_obj)
    db.session.commit()
    return redirect(url_for("index"))

# Start the monitoring thread
threading.Thread(target=monitor_websites, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
