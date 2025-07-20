FROM python:3.10

# Install Chromium and ChromeDriver
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy project files
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create screenshots directory
RUN mkdir -p screenshots

# Expose port
EXPOSE 8080

# Set environment variable for Chrome
ENV CHROME_BIN=/usr/bin/chromium

# Run the app
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8080"]
