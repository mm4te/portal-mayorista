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


def validar_config():
    faltantes = [k for k in ("SECRET_KEY", "INTERNAL_API_KEY") if not getattr(Config, k)]
    if faltantes:
        raise RuntimeError(
            f"Faltan variables de entorno: {', '.join(faltantes)}. "
            f"Copiá .env.example a .env y completalas."
        )
