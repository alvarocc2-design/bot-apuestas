import os
import logging
import asyncio
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import anthropic

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

SYSTEM_PROMPT = """Eres un experto analizador de apuestas deportivas especializado en value betting para mercados de jugadores en fútbol.

Tu trabajo es:
1. Analizar las estadísticas del jugador proporcionadas
2. Estimar la probabilidad REAL de que ocurra el evento apostado
3. Comparar con la probabilidad implícita de la cuota
4. Determinar si hay VALUE (valor esperado positivo)

FORMULA DE VALUE:
- Probabilidad implícita de la cuota = 1 / cuota decimal
- Value = (Probabilidad estimada x cuota) - 1
- Si Value > 0 HAY VALUE
- Si Value < 0 NO HAY VALUE

MERCADOS QUE ANALIZAS:
- Tarjetas amarillas
- Remates a puerta
- Remates totales
- Faltas cometidas
- Faltas recibidas

FORMATO DE RESPUESTA:
ANALISIS DE VALUE BET

Jugador: [nombre]
Mercado: [mercado analizado]
Cuota: [cuota] Prob. implicita: [X]%

ESTADISTICAS ANALIZADAS:
[resume las stats mas relevantes]

ANALISIS:
[2-3 lineas de razonamiento]

PROBABILIDAD ESTIMADA: [X]%
VALUE CALCULADO: [resultado]

HAY VALUE Edge de +[X]% / SIN VALUE
Confianza: [Alta/Media/Baja]
[Recomendacion final]

Se directo y honesto. Si las estadisticas son insuficientes dilo claramente."""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Bienvenido al Bot de Value Betting\n\n"
        "Envíame las estadísticas de un jugador junto con la cuota y te diré si hay value.\n\n"
        "Usa /ayuda para ver el formato."
    )

async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Envíame los datos así:\n\n"
        "Jugador: Gavi\n"
        "Mercado: Tarjeta amarilla\n"
        "Cuota: 2.80\n"
        "Stats:\n"
        "- 7 amarillas en 18 partidos\n"
        "- 2.1 faltas cometidas por partido\n"
        "- Árbitro estricto hoy\n\n"
        "Puedes pegar los datos directamente de ValueStats"
    )

async def analizar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    if user_message.startswith("/"):
        return

    waiting_msg = await update.message.reply_text("Analizando con IA... un momento")

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}]
        )
        analysis = response.content[0].text
        await waiting_msg.delete()
        await update.message.reply_text(analysis)

    except Exception as e:
        logger.error(f"Error: {e}")
        await waiting_msg.delete()
        await update.message.reply_text(f"Error al analizar: {str(e)}")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ayuda", ayuda))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, analizar))
    logger.info("Bot iniciado...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
