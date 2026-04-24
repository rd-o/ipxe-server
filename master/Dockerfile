FROM debian:12

RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-opencv \
    libgl1 \
    libglib2.0-0 \
    v4l-utils \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir --break-system-packages flask

WORKDIR /app
COPY master.py .
COPY main.sh .

VOLUME ["/app/videos"]

CMD ["python3", "master.py"]
