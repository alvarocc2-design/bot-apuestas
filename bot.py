import os
import requests
from telegram import Bot
import time

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

bot = Bot(token=TOKEN)

def enviar_mensaje(texto):
    bot.send_message(chat_id=CHAT_ID, text=texto)

def main():
    enviar_mensaje("🔥 Bot de apuestas ACTIVO 🔥")
    
    while True:
        try:
            enviar_mensaje("Buscando oportunidades...")
            time.sleep(300)  # cada 5 min
        except Exception as e:
            print(e)
            time.sleep(60)

if __name__ == "__main__":
    main()
