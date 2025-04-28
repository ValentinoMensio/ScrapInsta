FROM python:3.9-slim


RUN apt-get update && apt-get install -y \
    wget \
    unzip \
    libgl1-mesa-glx \
    libgl1-mesa-dri \
    xvfb \
    && wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get install -y ./google-chrome-stable_current_amd64.deb \
    && rm google-chrome-stable_current_amd64.deb \
    && apt-get clean



RUN mkdir -p /data && chmod 777 /data

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

WORKDIR /app
COPY . .

# Inicia Xvfb en segundo plano y luego ejecuta el script
CMD sh -c "Xvfb :99 -screen 0 1024x768x16 & export DISPLAY=:99 && python src/main.py"