from flask import Flask, request, render_template, redirect
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import requests, threading, time, os, smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv

# Load .env file
load_dotenv()
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///db.sqlite3"
db = SQLAlchemy(app)

class URL(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    link = db.Column(db.String(200), nullable=False)
    interval = db.Column(db.Integer, nullable=False)
    monitoring = db.Column(db.Boolean, default=False)

with app.app_context():
    db.create_all()

def send_email(subject, body):
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECEIVER

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.send_message(msg)

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print("Telegram error:", e)

def monitor_website(url_obj):
    while url_obj.monitoring:
        try:
            response = requests.get(url_obj.link, timeout=10)
            if response.status_code != 200:
                raise Exception(f"Status: {response.status_code}")
        except Exception as e:
            alert_msg = f"Website down: {url_obj.link}\nError: {e}"
            send_email("Website Down Alert", alert_msg)
            send_telegram(alert_msg)
        time.sleep(url_obj.interval * 60)

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        link = request.form["link"]
        interval = int(request.form["interval"])
        url = URL(link=link, interval=interval, monitoring=True)
        db.session.add(url)
        db.session.commit()
        threading.Thread(target=monitor_website, args=(url,), daemon=True).start()
        return redirect("/")
    urls = URL.query.all()
    return render_template("index.html", urls=urls)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)), debug=True)
