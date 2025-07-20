FROM python:3.10

# Install system dependencies for Pillow, NumPy, Selenium, and others
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    libjpeg-dev \
    zlib1g-dev \
    libpng-dev \
    libwebp-dev \
    libfreetype6-dev \
    libopenjp2-7-dev \
    build-essential \
    libblas-dev \
    liblapack-dev \
    gfortran \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy project files explicitly, ensuring static directory is included
COPY . .
# Only copy static if it exists, otherwise create an empty directory
RUN if [ -d "static" ]; then cp -r static/ /app/static/; else mkdir -p /app/static/; fi

# Remove any existing cache to force fresh build
RUN rm -rf __pycache__ *.pyc

# Upgrade pip and install Python dependencies
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt -v

# Create screenshots directory
RUN mkdir -p screenshots

# Expose port
EXPOSE 8080

# Set environment variable for Chrome
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/lib/chromium-browser/chromedriver

# Run the app with gunicorn
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8080"]
