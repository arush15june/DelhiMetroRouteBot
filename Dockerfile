FROM python:3-slim

WORKDIR /usr/src/app

COPY requirements.txt ./
RUN apt update && apt install gcc -y
RUN pip install --no-cache-dir -r requirements.txt
RUN addgroup --gid 1000 bot
RUN adduser --disabled-password --gecos '' --uid 1000 --gid 1000 bot

COPY . /home/bot/app 
USER bot

WORKDIR /home/bot/app

CMD [ "python", "application.py"]
