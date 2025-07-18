import requests
from bs4 import BeautifulSoup
import smtplib
import os

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
URL = "https://www.stwdo.de/wohnen/aktuelle-wohnangebote"
KEYWORD = "Wohnheim"  # or any text that appears when new offers are up

def check_website():
    response = requests.get(URL)
    soup = BeautifulSoup(response.text, 'html.parser')
    return KEYWORD.lower() in soup.text.lower()

def send_telegram(message):
    telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    requests.post(telegram_url, data=payload)

def send_email(subject, body):
    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.starttls()
    server.login(os.getenv("EMAIL_SENDER"), os.getenv("EMAIL_PASSWORD"))
    message = f"Subject: {subject}\n\n{body}"
    server.sendmail(os.getenv("EMAIL_SENDER"), os.getenv("EMAIL_RECEIVER"), message)
    server.quit()

if check_website():
    msg = "⚠️ New dorm offers are now live at TU Dortmund: " + URL
    send_telegram(msg)
    send_email("🏠 Dorm Alert", msg)
