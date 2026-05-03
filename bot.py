# bot.py

import os
import glob
import yt_dlp
from groq import Groq
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

# ==============================
# 🔑 CONFIGURACIÓN
# ==============================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

client = Groq(api_key=GROQ_API_KEY)

# ✅ FFmpeg disponible siempre
os.environ["PATH"] += r";C:\ffmpeg"

# ==============================
# 📥 DESCARGAR AUDIO
# ==============================

def descargar_video(url):
    for f in glob.glob("video.*"):
        os.remove(f)

    ydl_opts = {
        'outtmpl': 'video.%(ext)s',
        'format': 'bestaudio/best',
        'quiet': False,
        'ffmpeg_location': '/usr/bin',  # ✅ Ruta de ffmpeg en Railway
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '96',
        }],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    archivos = glob.glob("video.*")
    if not archivos:
        raise FileNotFoundError("No se encontró el archivo descargado")

    return archivos[0]

# ==============================
# 🧠 TRANSCRIBIR CON GROQ
# ==============================

from pydub import AudioSegment
import math

def transcribir(ruta_audio):
    # Carga el audio
    audio = AudioSegment.from_mp3(ruta_audio)
    duracion_ms = len(audio)
    chunk_ms = 10 * 60 * 1000  # 10 minutos por parte
    total_partes = math.ceil(duracion_ms / chunk_ms)
    
    transcripcion_completa = ""
    
    for i in range(total_partes):
        inicio = i * chunk_ms
        fin = min((i + 1) * chunk_ms, duracion_ms)
        parte = audio[inicio:fin]
        
        parte_path = f"parte_{i}.mp3"
        parte.export(parte_path, format="mp3")
        
        with open(parte_path, "rb") as f:
            resultado = client.audio.transcriptions.create(
                file=(parte_path, f),
                model="whisper-large-v3-turbo",
                response_format="text"
            )
        transcripcion_completa += resultado + " "
        os.remove(parte_path)
    
    return transcripcion_completa.strip()

# ==============================
# ✨ RESUMIR CON GROQ
# ==============================

def resumir(texto):
    partes = [texto[i:i+8000] for i in range(0, len(texto), 8000)]
    resumenes = []

    for parte in partes:
        prompt_parte = "Resume brevemente este fragmento en 3 puntos clave:\n\n" + parte
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt_parte}]
        )
        resumenes.append(response.choices[0].message.content)

    texto_resumenes = " ".join(resumenes)
    prompt_final = "Basándote en estos resúmenes parciales, crea un resumen final estructurado:\n\n- Idea principal\n- Problemas clave\n- Soluciones\n- Frases clave\n\nResúmenes:\n" + texto_resumenes

    resumen_final = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt_final}]
    )

    return resumen_final.choices[0].message.content
# ==============================
# 🧹 LIMPIAR ARCHIVOS
# ==============================

def limpiar_archivos():
    for f in glob.glob("video.*"):
        try:
            os.remove(f)
        except:
            pass

# ==============================
# 🤖 MANEJAR MENSAJES
# ==============================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()

    if not url.startswith("http"):
        await update.message.reply_text("📎 Envíame un link de TikTok o YouTube.")
        return

    if "tiktok.com" not in url and "youtube.com" not in url and "youtu.be" not in url:
        await update.message.reply_text("⚠️ Solo acepto links de TikTok o YouTube.")
        return

    await update.message.reply_text("⏳ Descargando audio...")

    try:
        archivo = descargar_video(url)
        await update.message.reply_text("🧠 Transcribiendo con IA...")

        texto = transcribir(archivo)

        if not texto.strip():
            await update.message.reply_text("⚠️ No se detectó voz en el video.")
            return

        await update.message.reply_text("✨ Resumiendo...")
        resultado = resumir(texto)
        await update.message.reply_text(resultado)

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")
    finally:
        limpiar_archivos()

# ==============================
# 🚀 INICIAR BOT
# ==============================

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🤖 Bot corriendo...")
    app.run_polling()

if __name__ == "__main__":
    main()