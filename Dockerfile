FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libgl1 \
    chromium \
    chromium-driver \
    curl \
    unzip \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set environment variables for Selenium + Chromium
ENV CHROME_BIN=/usr/bin/chromium
ENV PATH="${CHROME_BIN}:${PATH}"

# Set working directory
WORKDIR /app

# Copy code
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose port (if your app runs on 8000 or Streamlit's default 8501)
EXPOSE 8000

# Run the app
CMD ["python", "app.py"]  # Change if using Streamlit: CMD ["streamlit", "run", "app.py"]
