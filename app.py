from flask import Flask, request, redirect, url_for, render_template, send_from_directory
from flask_sqlalchemy import SQLAlchemy
import requests
import os
import smtplib
import threading
import time
from datetime import datetime
from email.mime.text import MIMEText
from dotenv import load_dotenv
from urllib.parse import urlparse
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from PIL import Image
import hashlib
import numpy as np

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

# Debug: Print environment variables
print(f"DEBUG - EMAIL_SENDER: {EMAIL_SENDER}")
print(f"DEBUG - EMAIL_PASSWORD: {EMAIL_PASSWORD}")
print(f"DEBUG - EMAIL_RECEIVER: {EMAIL_RECEIVER}")
print(f"DEBUG - TELEGRAM_TOKEN: {TELEGRAM_TOKEN}")
print(f"DEBUG - TELEGRAM_CHAT_ID: {TELEGRAM_CHAT_ID}")

# Verify environment variables
missing_vars = [var for var, value in [
    ("EMAIL_SENDER", EMAIL_SENDER),
    ("EMAIL_PASSWORD", EMAIL_PASSWORD),
    ("EMAIL_RECEIVER", EMAIL_RECEIVER),
    ("TELEGRAM_TOKEN", TELEGRAM_TOKEN),
    ("TELEGRAM_CHAT_ID", TELEGRAM_CHAT_ID)
] if not value]
if missing_vars:
    raise ValueError(f"Missing environment variables: {', '.join(missing_vars)}")

# Create screenshots directory
SCREENSHOTS_DIR = "/app/screenshots"  # Use /app/screenshots for Railway volume
if not os.path.exists(SCREENSHOTS_DIR):
    os.makedirs(SCREENSHOTS_DIR)

class URL(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    last_checked = db.Column(db.DateTime)
    status = db.Column(db.String(20))
    last_screenshot = db.Column(db.String(255))  # Path to latest screenshot

def get_screenshot_filename(url):
    """Generate a filename for the screenshot based on URL hash."""
    url_hash = hashlib.md5(url.encode()).hexdigest()
    return os.path.join(SCREENSHOTS_DIR, f"{url_hash}.png")

def take_screenshot(url):
    """Capture a screenshot of the given URL using Selenium."""
    try:
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.binary_location = os.getenv("CHROME_BIN", "/usr/bin/chromium")
        service = Service(os.getenv("CHROMEDRIVER_PATH", "/usr/lib/chromium-browser/chromedriver"))
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_window_size(1280, 720)  # Standardize window size
        driver.get(url)
        time.sleep(2)  # Wait for page to load
        screenshot_path = get_screenshot_filename(url)
        driver.save_screenshot(screenshot_path)
        driver.quit()
        return screenshot_path
    except Exception as e:
        print(f"[ERROR] Failed to take screenshot for {url}: {e}")
        return None

def compare_screenshots(img1_path, img2_path, threshold=0.1):
    """Compare two screenshots and return True if significantly different."""
    try:
        img1 = Image.open(img1_path).convert("RGB")
        img2 = Image.open(img2_path).convert("RGB")
        
        # Resize images to ensure same dimensions
        img1 = img1.resize((1280, 720))
        img2 = img2.resize((1280, 720))
        
        # Convert to numpy arrays
        arr1 = np.array(img1)
        arr2 = np.array(img2)
        
        # Calculate mean squared error
        mse = np.mean((arr1 - arr2) ** 2)
        max_mse = 255 ** 2  # Maximum possible MSE for RGB images
        difference = mse / max_mse
        
        print(f"[INFO] Screenshot comparison MSE: {mse}, Normalized: {difference}")
        return difference > threshold  # Return True if difference exceeds threshold
    except Exception as e:
        print(f"[ERROR] Failed to compare screenshots: {e}")
        return False

def send_email(subject, body):
    msg = MIMEText(body)
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECEIVER
    msg['Subject'] = subject
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.send_message(msg)
        print("[INFO] Email sent.")
    except Exception as e:
        print(f"[ERROR] Failed to send email: {e}")

def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message
        }
        requests.post(url, data=payload)
        print("[INFO] Telegram message sent.")
    except Exception as e:
        print(f"[ERROR] Failed to send Telegram message: {e}")

def monitor_websites():
    with app.app_context():
        while True:
            try:
                urls = URL.query.all()
                for url_obj in urls:
                    if url_obj.is_active:
                        # Check HTTP status
                        try:
                            response = requests.get(url_obj.url, timeout=5)
                            status = "Up" if response.status_code == 200 else f"Down ({response.status_code})"
                        except Exception as e:
                            status = "Down"
                            print(f"[ERROR] Failed to check {url_obj.url}: {e}")
                        
                        # Take screenshot
                        new_screenshot = take_screenshot(url_obj.url)
                        
                        # Compare with previous screenshot
                        visual_change = False
                        if new_screenshot and url_obj.last_screenshot and os.path.exists(url_obj.last_screenshot):
                            visual_change = compare_screenshots(url_obj.last_screenshot, new_screenshot)
                        
                        # Send alerts if status or visuals changed
                        if url_obj.status != status or visual_change:
                            alert = f"URL: {url_obj.url}\nStatus: {status}"
                            if visual_change:
                                alert += "\nVisual change detected!"
                            send_email("Website Status Alert", alert)
                            send_telegram(alert)
                        
                        # Update database
                        url_obj.status = status
                        url_obj.last_checked = datetime.utcnow()
                        if new_screenshot:
                            # Save previous screenshot path temporarily
                            old_screenshot = url_obj.last_screenshot
                            url_obj.last_screenshot = new_screenshot
                            # Delete old screenshot if it exists
                            if old_screenshot and os.path.exists(old_screenshot):
                                try:
                                    os.remove(old_screenshot)
                                except Exception as e:
                                    print(f"[ERROR] Failed to delete old screenshot: {e}")
                        
                        try:
                            db.session.commit()
                        except Exception as e:
                            db.session.rollback()
                            print(f"[ERROR] Database commit failed: {e}")
                        
                        time.sleep(1)  # Delay between requests
            except Exception as e:
                print(f"[ERROR] Monitor thread error: {e}")
            time.sleep(60)

@app.route('/')
def index():
    try:
        urls = URL.query.all()
        return render_template('index.html', urls=urls)
    except Exception as e:
        print(f"[ERROR] Index route error: {e}")
        return "Failed to load URLs", 500

@app.route('/add', methods=['POST'])
def add():
    url = request.form.get('url')
    if not url:
        return "Missing URL", 400
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return "Invalid URL", 400
    try:
        new_url = URL(url=url)
        db.session.add(new_url)
        db.session.commit()
        return redirect(url_for('index'))
    except Exception as e:
        db.session.rollback()
        print(f"[ERROR] Failed to add URL: {e}")
        return "Failed to add URL", 500

@app.route('/toggle/<int:url_id>')
def toggle(url_id):
    try:
        url_obj = URL.query.get_or_404(url_id)
        url_obj.is_active = not url_obj.is_active
        db.session.commit()
        return redirect(url_for('index'))
    except Exception as e:
        db.session.rollback()
        print(f"[ERROR] Failed to toggle URL: {e}")
        return "Failed to toggle URL", 500

@app.route('/delete/<int:url_id>')
def delete(url_id):
    try:
        url_obj = URL.query.get_or_404(url_id)
        # Delete associated screenshot
        if url_obj.last_screenshot and os.path.exists(url_obj.last_screenshot):
            try:
                os.remove(url_obj.last_screenshot)
            except Exception as e:
                print(f"[ERROR] Failed to delete screenshot: {e}")
        db.session.delete(url_obj)
        db.session.commit()
        return redirect(url_for('index'))
    except Exception as e:
        db.session.rollback()
        print(f"[ERROR] Failed to delete URL: {e}")
        return "Failed to delete URL", 500

@app.route('/screenshots/<path:filename>')
def serve_screenshot(filename):
    try:
        return send_from_directory(SCREENSHOTS_DIR, filename)
    except Exception as e:
        print(f"[ERROR] Failed to serve screenshot: {e}")
        return "Screenshot not found", 404

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    threading.Thread(target=monitor_websites, daemon=True).start()
    app.run(host="0.0.0.0", port=8080, debug=True)
