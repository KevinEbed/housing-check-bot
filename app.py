from flask import Flask, render_template, request, redirect
from apscheduler.schedulers.background import BackgroundScheduler
import requests, hashlib, os
from dotenv import load_dotenv
from datetime import datetime
import smtplib
from email.mime.text import MIMEText

# Load environment variables
load_dotenv()
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

app = Flask(__name__)
scheduler = BackgroundScheduler()
scheduler.start()

# Store URL and its hash
urls = {}

def send_email(subject, body):
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECEIVER

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    requests.post(url, data=data)

def monitor_website(url_id):
    url = urls.get(url_id)
    if not url:
        return

    try:
        response = requests.get(url["link"], timeout=10)
        new_hash = hashlib.sha256(response.content).hexdigest()

        if url["hash"] and new_hash != url["hash"]:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            subject = f"Website Updated: {url['link']}"
            body = f"Change detected at {timestamp}."
            send_email(subject, body)
            send_telegram(subject)

        url["hash"] = new_hash

    except Exception as e:
        print(f"Error monitoring {url['link']}: {e}")

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        link = request.form.get("link")
        interval = int(request.form.get("interval", 60))
        url_id = len(urls) + 1
        urls[url_id] = {"link": link, "hash": None}
        scheduler.add_job(lambda: monitor_website(url_id), "interval", seconds=interval, id=str(url_id))
        return redirect("/")

    return render_template("index.html", urls=urls)

@app.route("/stop/<int:url_id>")
def stop(url_id):
    try:
        scheduler.remove_job(str(url_id))
        urls.pop(url_id, None)
    except Exception as e:
        print(f"Failed to stop monitoring: {e}")
    return redirect("/")

if __name__ == "__main__":
    app.run(debug=True, port=8080, host="0.0.0.0")
