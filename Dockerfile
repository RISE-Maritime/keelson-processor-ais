FROM python:3.12-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y \
    git \
    libsm6\
    libxext6\
    && rm -rf /var/lib/apt/lists/*

COPY . .

COPY requirements.txt requirements.txt

RUN pip3 install opencv-python
RUN pip3 install --no-cache-dir -r requirements.txt


ENTRYPOINT ["python", "bin/main.py"]

CMD ["-r", "rise"]