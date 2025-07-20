from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import requests, threading, time, smtplib, os
from email.mime.text import MIMEText
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///urls.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Telegram
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Email
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")

# Database model
class URL(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(512), nullable=False)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_checked = db.Column(db.DateTime, nullable=True)
    is_monitoring = db.Column(db.Boolean, default=True)

with app.app_context():
    db.create_all()

# Monitor thread
def monitor_websites():
    while True:
        with app.app_context():
            urls = URL.query.all()
            for url_obj in urls:
                if url_obj.is_monitoring:
                    try:
                        response = requests.get(url_obj.url, timeout=5)
                        if response.status_code != 200:
                            send_alert(url_obj.url, f"Status Code: {response.status_code}")
                    except Exception as e:
                        send_alert(url_obj.url, str(e))
                url_obj.last_checked = datetime.utcnow()
                db.session.commit()
        time.sleep(60)

def send_alert(url, message):
    full_msg = f"⚠️ Website DOWN\nURL: {url}\nIssue: {message}"
    send_telegram(full_msg)
    send_email("Website Alert", full_msg)

def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
        requests.post(url, data=data)
    except:
        pass

def send_email(subject, body):
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = EMAIL_SENDER
        msg["To"] = EMAIL_RECEIVER

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
    except:
        pass

# Routes
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        url = request.form["url"]
        if url:
            new_url = URL(url=url)
            db.session.add(new_url)
            db.session.commit()
            return redirect(url_for("index"))
    urls = URL.query.all()
    return render_template("index.html", urls=urls)

@app.route("/delete/<int:url_id>")
def delete_url(url_id):
    url = URL.query.get_or_404(url_id)
    db.session.delete(url)
    db.session.commit()
    return redirect(url_for("index"))

@app.route("/toggle/<int:url_id>")
def toggle_url(url_id):
    url = URL.query.get_or_404(url_id)
    url.is_monitoring = not url.is_monitoring
    db.session.commit()
    return redirect(url_for("index"))

# Start monitor thread
threading.Thread(target=monitor_websites, daemon=True).start()

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=8080)
