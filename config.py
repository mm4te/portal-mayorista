# config.py
import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY")
    DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"

    # DB propia del portal
    DB_PATH = os.path.join(BASE_DIR, "mayoristas.db")

    # API interna de comenda-sistema
    COMENDA_API_URL = os.getenv("COMENDA_API_URL", "http://127.0.0.1:5000").rstrip("/")
    INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY")

    # Timeout (segundos) para las llamadas a la API interna
    API_TIMEOUT = 15

    PORT = int(os.getenv("PORT", "5001"))

    # Rate limiting del registro: máximo N altas por IP en la ventana (minutos)
    REGISTRO_MAX_POR_IP = 5
    REGISTRO_VENTANA_MIN = 60

    # ── Recuperación de contraseña (D1) ─────────────────────────────────────
    RESET_TOKEN_TTL_MIN = 60
    RESET_MAX_SOLICITUDES_IP = 5
    RESET_MAX_SOLICITUDES_EMAIL = 3
    RESET_SOLICITUDES_VENTANA_MIN = 60
    RESET_MAX_VALIDACIONES_IP = 10
    RESET_VALIDACIONES_VENTANA_MIN = 60
    # Sin esto (o fuera de app.debug), /recuperar no tiene forma de "enviar"
    # nada — ver services/mailer.py. Se prende a propósito solo en desarrollo.
    RESET_LOG_LINK_FALLBACK = os.getenv("RESET_LOG_LINK_FALLBACK", "false").lower() == "true"

    # Proveedor de mail real (D1.h) — ninguna cargada todavía. Su sola
    # presencia es lo que services.mailer.mail_configurado() usa para saber
    # si ya hay con qué mandar el mail de recuperación o si /recuperar tiene
    # que mostrar el mensaje de "escribinos al WhatsApp" en su lugar — el
    # modo se detecta por esto, no por una constante en el código. OJO: el
    # día que se cargue SMTP_HOST, además hay que pedir que se conecte el
    # envío real acá — mail_configurado() en True sin eso todavía haría que
    # /recuperar intente enviar y explote igual, ver services/mailer.py.
    SMTP_HOST = os.getenv("SMTP_HOST")
    SMTP_PORT = os.getenv("SMTP_PORT")
    SMTP_USER = os.getenv("SMTP_USER")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
    MAIL_REMITENTE = os.getenv("MAIL_REMITENTE")
    MAIL_REMITENTE_NOMBRE = os.getenv("MAIL_REMITENTE_NOMBRE")


def validar_config():
    faltantes = [k for k in ("SECRET_KEY", "INTERNAL_API_KEY") if not getattr(Config, k)]
    if faltantes:
        raise RuntimeError(
            f"Faltan variables de entorno: {', '.join(faltantes)}. "
            f"Copiá .env.example a .env y completalas."
        )
