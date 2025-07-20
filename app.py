from flask import Flask, request, redirect, render_template
from flask_sqlalchemy import SQLAlchemy
import threading
import requests
import os
import smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv
import time

# Load environment variables
load_dotenv()
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Flask Setup
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///urls.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class URL(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    address = db.Column(db.String(255), nullable=False)
    monitoring = db.Column(db.Boolean, default=True)

with app.app_context():
    db.create_all()

def send_telegram_alert(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
        requests.post(url, data=payload)
    except Exception as e:
        print(f"Telegram Error: {e}")

def send_email_alert(subject, body):
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = EMAIL_SENDER
        msg["To"] = EMAIL_RECEIVER
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
    except Exception as e:
        print(f"Email Error: {e}")

def monitor_website(url_id):
    with app.app_context():
        url_obj = db.session.get(URL, url_id)
        while url_obj and url_obj.monitoring:
            try:
                response = requests.get(url_obj.address, timeout=10)
                if response.status_code != 200:
                    msg = f"Website {url_obj.address} returned status {response.status_code}"
                    send_email_alert("Website Alert", msg)
                    send_telegram_alert(msg)
            except requests.RequestException:
                msg = f"Website {url_obj.address} is DOWN!"
                send_email_alert("Website Alert", msg)
                send_telegram_alert(msg)

            time.sleep(60)
            db.session.refresh(url_obj)

@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        address = request.form.get("url")
        if address:
            new_url = URL(address=address)
            db.session.add(new_url)
            db.session.commit()
            threading.Thread(target=monitor_website, args=(new_url.id,), daemon=True).start()
        return redirect("/")
    
    urls = URL.query.all()
    return render_template("index.html", urls=urls)

@app.route("/stop/<int:url_id>")
def stop_monitoring(url_id):
    url = db.session.get(URL, url_id)
    if url:
        url.monitoring = False
        db.session.commit()
    return redirect("/")


if __name__ == "__main__":
     app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
