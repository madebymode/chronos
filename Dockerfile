# Use the lightweight Alpine-based Python image
FROM python:3.9-alpine

# Set up the working directory
WORKDIR /app

# Copy requirements.txt and main.py to the working directory
COPY requirements.txt main.py ./

# Install required packages, set timezone, and set up cron
RUN apk add --no-cache tzdata && \
    pip install --no-cache-dir -r requirements.txt && \
    ln -snf /usr/share/zoneinfo/America/New_York /etc/localtime && \
    echo "America/New_York" > /etc/timezone && \
    echo '0 9 * * * python /app/main.py' > /etc/crontabs/root && \
    chmod 0644 /etc/crontabs/root

# Start crond in the foreground
CMD ["crond", "-f", "-d", "8"]
