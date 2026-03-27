import os
import logging
import base64
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import anthropic

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(**name**)

TELEGRAM_TOKEN = os.environ.get(“TELEGRAM_BOT_TOKEN”)
ANTHROPIC_API_KEY = os.environ.get(“ANTHROPIC_API_KEY”)

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

SYSTEM_PROMPT = “”“Eres un experto analizador de apuestas deportivas especializado en value betting para mercados de jugadores en fútbol.

Se te proporcionarán imágenes etiquetadas con su tipo:

- “stats”: estadísticas de jugadores de ValueStats (remates, remates a puerta, faltas, tarjetas por partido)
- “cuotas remates a puerta”: cuotas para remates a puerta (1+, 2+, 3+)
- “cuotas remates totales”: cuotas para remates totales (1+, 2+, 3+)
- “cuotas tarjetas”: cuotas para tarjetas amarillas (1+, 2+)
- “cuotas faltas”: cuotas para faltas cometidas
- “arbitro”: estadísticas del árbitro designado (tarjetas por partido, faltas pitadas, estilo)

FORMULA DE VALUE:

- Probabilidad implícita = 1 / cuota decimal
- Value = (Probabilidad estimada x cuota) - 1
- Si Value > 0 HAY VALUE
- Si Value < 0 NO HAY VALUE

RANGO DE CUOTA PREFERIDO: 1.50 a 2.00
Las apuestas dentro de este rango CON value positivo son las prioritarias.
Las apuestas fuera de este rango con value positivo también se muestran pero marcadas como secundarias.

ANALISIS DE TARJETAS AMARILLAS:
Cuando tengas la foto del árbitro crúzala con las stats de cada jugador:

- Faltas cometidas por partido del jugador x tarjetas por partido del árbitro
- Un árbitro que saca 4+ tarjetas por partido multiplica la probabilidad
- Un árbitro que saca 2 o menos tarjetas por partido la reduce
- Considera también el perfil del jugador (mediocampista agresivo = más riesgo)
- Si el árbitro es muy estricto y el jugador comete muchas faltas = value alto en tarjetas

ANALISIS DE REMATES A PUERTA:

- Usa la columna de remates a puerta por partido de las stats
- Crúzala con las cuotas de remates a puerta
- Un jugador con 1.5+ remates a puerta por partido tiene alta probabilidad en mercado 1+

ANALISIS DE REMATES TOTALES:

- Usa la columna de remates totales por partido de las stats
- Crúzala con las cuotas de remates totales
- Un jugador con 2.5+ remates por partido tiene alta probabilidad en mercado 2+

ANALISIS DE FALTAS RECIBIDAS:

- Usa la columna de faltas recibidas por partido
- Crúzala con las cuotas de faltas si están disponibles

Cuando el usuario pida el análisis final:

1. Cruza stats de cada jugador con sus cuotas disponibles
1. Si hay foto de árbitro úsala para ajustar la probabilidad de tarjetas
1. Calcula el value para cada combinación jugador + mercado
1. Clasifica en dos grupos:
   PRIORITARIAS: cuota entre 1.50 y 2.00 CON value positivo
   OTRAS CON VALUE: cuota fuera de ese rango pero con value positivo
1. Ordena cada grupo por mayor value esperado
1. Recomienda siempre del grupo prioritario si existe

FORMATO DE RESPUESTA FINAL:

ANALISIS COMPLETO DEL PARTIDO

— APUESTAS PRIORITARIAS (cuota 1.50-2.00 con value) —

1. Jugador: [nombre]
   Mercado: [mercado]
   Cuota: [cuota]
   Stats relevantes: [datos clave]
   Factor árbitro: [si aplica]
   Prob. estimada: [X]%
   Prob. implícita: [X]%
   VALUE: +[X]%
   Confianza: [Alta/Media/Baja]

— OTRAS CON VALUE (fuera de rango preferido) —

1. Jugador: [nombre]
   Mercado: [mercado]
   Cuota: [cuota]
   VALUE: +[X]%
   Confianza: [Alta/Media/Baja]

— SIN VALUE (informativo) —
[Lista breve de apuestas sin value para evitar]

MEJOR APUESTA DEL PARTIDO:
Jugador: [nombre]
Mercado: [mercado]
Cuota: [cuota]
Razonamiento: [2 líneas]

Si no hay apuestas prioritarias indícalo claramente y explica por qué.”””

user_images = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
await update.message.reply_text(
“Bienvenido al Bot de Value Betting\n\n”
“Como usarlo:\n\n”
“1. Envía las fotos una a una con su caption:\n”
“   stats\n”
“   cuotas remates a puerta\n”
“   cuotas remates totales\n”
“   cuotas tarjetas\n”
“   cuotas faltas\n”
“   arbitro\n\n”
“2. Escribe: analiza\n\n”
“3. El bot te dará las mejores apuestas priorizando cuotas entre 1.50 y 2.00 con value positivo\n\n”
“También puedes escribirle directamente sin fotos para recalcular o hacer consultas.\n\n”
“Usa /limpiar para borrar las fotos y empezar de nuevo.”
)

async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
await update.message.reply_text(
“COMO USAR EL BOT:\n\n”
“Paso 1 - Envía cada foto con su caption:\n”
“Foto stats ValueStats → caption: stats\n”
“Foto cuotas → caption: cuotas remates a puerta\n”
“Foto cuotas → caption: cuotas remates totales\n”
“Foto cuotas → caption: cuotas tarjetas\n”
“Foto árbitro → caption: arbitro\n\n”
“Paso 2 - Escribe: analiza\n\n”
“También puedes escribir directamente:\n”
“En Winamax veo a Haraslin tiro a puerta a 1.95, hay value?\n\n”
“El bot priorizará cuotas entre 1.50 y 2.00 con value positivo.”
)

async def limpiar(update: Update, context: ContextTypes.DEFAULT_TYPE):
user_id = update.message.from_user.id
user_images[user_id] = []
await update.message.reply_text(“Fotos borradas. Puedes empezar de nuevo.”)

async def recibir_foto(update: Update, context: ContextTypes.DEFAULT_TYPE):
user_id = update.message.from_user.id
caption = update.message.caption or “sin etiqueta”

```
if user_id not in user_images:
    user_images[user_id] = []

try:
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    image_bytes = await file.download_as_bytearray()
    image_base64 = base64.b64encode(image_bytes).decode("utf-8")

    user_images[user_id].append({
        "tipo": caption,
        "data": image_base64
    })

    total = len(user_images[user_id])
    await update.message.reply_text(
        f"Foto guardada: {caption}\n"
        f"Total fotos recibidas: {total}\n\n"
        f"Cuando tengas todas escribe: analiza"
    )

except Exception as e:
    logger.error(f"Error foto: {e}")
    await update.message.reply_text(f"Error al guardar la foto: {str(e)}")
```

async def analizar(update: Update, context: ContextTypes.DEFAULT_TYPE):
user_id = update.message.from_user.id
mensaje_original = update.message.text
mensaje = mensaje_original.lower().strip()

```
tiene_fotos = user_id in user_images and len(user_images[user_id]) > 0

# CASO 1: Tiene fotos + escribe analiza
if tiene_fotos and mensaje == "analiza":
    waiting_msg = await update.message.reply_text(
        f"Analizando {len(user_images[user_id])} fotos con IA... un momento"
    )
    try:
        content = []
        for img in user_images[user_id]:
            content.append({"type": "text", "text": f"Imagen tipo: {img['tipo']}"})
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": img["data"]}
            })
        content.append({
            "type": "text",
            "text": "Analiza todas las imágenes, cruza las estadísticas con las cuotas y dime cuál es la mejor apuesta del partido. Prioriza apuestas con cuota entre 1.50 y 2.00 que tengan value positivo."
        })
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}]
        )
        await waiting_msg.delete()
        await update.message.reply_text(response.content[0].text)
        user_images[user_id] = []
        await update.message.reply_text("Fotos borradas. Puedes empezar un nuevo analisis.")
    except Exception as e:
        logger.error(f"Error analisis: {e}")
        await waiting_msg.delete()
        await update.message.reply_text(f"Error al analizar: {str(e)}")
    return

# CASO 2: Tiene fotos + escribe texto libre (recalcular, añadir info, etc)
if tiene_fotos and mensaje != "analiza":
    waiting_msg = await update.message.reply_text(
        f"Analizando fotos + tu mensaje... un momento"
    )
    try:
        content = []
        for img in user_images[user_id]:
            content.append({"type": "text", "text": f"Imagen tipo: {img['tipo']}"})
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": img["data"]}
            })
        content.append({"type": "text", "text": mensaje_original})
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}]
        )
        await waiting_msg.delete()
        await update.message.reply_text(response.content[0].text)
        user_images[user_id] = []
        await update.message.reply_text("Fotos borradas. Puedes empezar un nuevo analisis.")
    except Exception as e:
        logger.error(f"Error: {e}")
        await waiting_msg.delete()
        await update.message.reply_text(f"Error: {str(e)}")
    return

# CASO 3: Sin fotos + texto libre (consulta directa o recalculo)
waiting_msg = await update.message.reply_text("Analizando... un momento")
try:
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": mensaje_original}]
    )
    await waiting_msg.delete()
    await update.message.reply_text(response.content[0].text)
except Exception as e:
    logger.error(f"Error: {e}")
    await waiting_msg.delete()
    await update.message.reply_text(f"Error: {str(e)}")
```

def main():
app = Application.builder().token(TELEGRAM_TOKEN).build()
app.add_handler(CommandHandler(“start”, start))
app.add_handler(CommandHandler(“ayuda”, ayuda))
app.add_handler(CommandHandler(“limpiar”, limpiar))
app.add_handler(MessageHandler(filters.PHOTO, recibir_foto))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, analizar))
logger.info(“Bot iniciado…”)
app.run_polling(drop_pending_updates=True)

if **name** == “**main**”:
main()
