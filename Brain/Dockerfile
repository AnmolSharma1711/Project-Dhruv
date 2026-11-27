FROM python:3.11-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 HOME=/tmp
RUN apt-get update && apt-get install -y --no-install-recommends pulseaudio-utils ca-certificates libglib2.0-0 libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --only-binary=:all: -r requirements.txt
COPY voice/ voice/
USER 1000:1000
CMD ["python", "-m", "voice"]
