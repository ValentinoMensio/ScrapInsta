FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    wget curl gnupg ca-certificates unzip xvfb \
    libnss3 libxss1 libasound2 libxrandr2 libxcomposite1 \
    libxdamage1 libxext6 libxfixes3 libxkbcommon0 libpango-1.0-0 \
    libatk-bridge2.0-0 libgtk-3-0 libgbm1 libx11-xcb1 fonts-liberation \
 && rm -rf /var/lib/apt/lists/*

# Google Chrome estable
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - && \
    echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" \
      > /etc/apt/sources.list.d/google-chrome.list && \
    apt-get update && apt-get install -y --no-install-recommends google-chrome-stable && \
    rm -rf /var/lib/apt/lists/*

# Usuario no-root + carpeta de perfiles
RUN useradd -m scrapinsta && mkdir -p /home/scrapinsta/.cache/ScrapInsta/profiles
USER scrapinsta
WORKDIR /home/scrapinsta/app

COPY --chown=scrapinsta:scrapinsta requirements.txt .
RUN pip install --upgrade pip setuptools wheel && pip install -r requirements.txt

COPY --chown=scrapinsta:scrapinsta . .

ENV BROWSER_PROFILES_DIR=/home/scrapinsta/.cache/ScrapInsta/profiles
ENV HEADLESS=false

CMD ["bash", "-lc", "python -m scrapinsta.interface.main"]
