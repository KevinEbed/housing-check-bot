from flask import Flask, render_template, request, redirect
from flask_sqlalchemy import SQLAlchemy
import requests, threading, time, os, smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv

# Load .env variables
load_dotenv()

EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///urls.db'
db = SQLAlchemy(app)

# DB Model
class URL(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    link = db.Column(db.String(500), nullable=False)
    interval = db.Column(db.Integer, nullable=False)
    monitoring = db.Column(db.Boolean, default=False)

# Monitor function
def monitor_url(url_id):
    url = URL.query.get(url_id)
    while url and url.monitoring:
        try:
            response = requests.get(url.link, timeout=10)
            if response.status_code != 200:
                send_alert(f"⚠️ {url.link} is DOWN. Status code: {response.status_code}")
        except Exception as e:
            send_alert(f"🚨 {url.link} is UNREACHABLE.\nError: {str(e)}")
        time.sleep(url.interval)
        url = URL.query.get(url_id)  # Refresh from DB

# Alert function
def send_alert(message):
    # Send Telegram
    try:
        telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(telegram_url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message})
    except:
        pass

    # Send Email
    try:
        msg = MIMEText(message)
        msg['Subject'] = "🔔 Website Monitor Alert"
        msg['From'] = EMAIL_SENDER
        msg['To'] = EMAIL_RECEIVER

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.send_message(msg)
    except:
        pass

# Routes
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        new_url = URL(
            link=request.form['link'],
            interval=int(request.form['interval']),
            monitoring=False
        )
        db.session.add(new_url)
        db.session.commit()
    urls = URL.query.all()
    return render_template('index.html', urls=urls)

@app.route('/start/<int:url_id>')
def start_monitoring(url_id):
    url = URL.query.get(url_id)
    if url and not url.monitoring:
        url.monitoring = True
        db.session.commit()
        threading.Thread(target=monitor_url, args=(url_id,), daemon=True).start()
    return redirect('/')

@app.route('/stop/<int:url_id>')
def stop_monitoring(url_id):
    url = URL.query.get(url_id)
    if url:
        url.monitoring = False
        db.session.commit()
    return redirect('/')

@app.route('/delete/<int:url_id>')
def delete_url(url_id):
    url = URL.query.get(url_id)
    if url:
        db.session.delete(url)
        db.session.commit()
    return redirect('/')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=8080)
