FROM python:3-slim

WORKDIR /usr/src/app


COPY requirements.txt ./
RUN apt update && apt install gcc -y
RUN pip install --no-cache-dir -r requirements.txt
RUN useradd -ms /bin/sh bot
USER bot

COPY . .

CMD [ "python", "./application.py"]
