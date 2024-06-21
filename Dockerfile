# Use the lightweight Alpine-based Python image
FROM python:3.11-alpine3.20 as builder

# Set up the working directory
WORKDIR /app

# Copy requirements.txt and main.py to the working directory
COPY requirements.txt main.py ./

# Install required packages, PyInstaller, and binutils
RUN apk add --no-cache binutils && \
    pip install --no-cache-dir -r requirements.txt pyinstaller

# Create a standalone binary of your Python script
RUN pyinstaller --onefile --noconfirm --clean main.py

# Start a new stage so we can get rid of the Python install,
# resulting in a smaller final image
FROM alpine:3.20

# Copy the standalone binary from the builder stage to /dist in final image
COPY --from=builder /app/dist/main /dist/main

# Set timezone and set up cron
RUN apk add --no-cache tzdata && \
    ln -snf /usr/share/zoneinfo/America/New_York /etc/localtime && \
    echo "America/New_York" > /etc/timezone && \
    echo '0 9 * * * /dist/main' > /etc/crontabs/root && \
    chmod 0644 /etc/crontabs/root

# Start crond in the foreground
CMD ["crond", "-f", "-d", "8"]
