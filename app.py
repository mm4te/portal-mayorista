# app.py — Portal Mayorista (servicio independiente, puerto 5001)
import os
import time
import logging
from urllib.parse import quote

from flask import Flask, g, redirect, url_for, send_from_directory, render_template
from flask_wtf.csrf import CSRFProtect

# El negocio opera en Argentina (misma decisión que comenda-sistema).
os.environ.setdefault("TZ", "America/Argentina/Buenos_Aires")
if hasattr(time, "tzset"):
    time.tzset()

from config import Config, validar_config
from models import init_db
from routes import cargar_cliente
from routes.auth import auth_bp
from routes.catalogo import catalogo_bp
from routes.carrito import carrito_bp
from routes.pedidos import pedidos_bp
from routes.api_interna import api_interna_bp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

csrf = CSRFProtect()


def wa_url(telefono, mensaje=None):
    # wa.me exige solo dígitos, con 54 9 adelante (celular AR) — sin el
    # 0/15 que la gente usa al escribir el número a mano.
    digitos = "".join(ch for ch in str(telefono) if ch.isdigit())
    url = f"https://wa.me/549{digitos}"
    if mensaje:
        url += f"?text={quote(mensaje)}"
    return url


def create_app():
    validar_config()
    init_db()

    app = Flask(__name__)
    app.secret_key = Config.SECRET_KEY
    app.config["WTF_CSRF_TIME_LIMIT"] = 3600

    csrf.init_app(app)

    app.before_request(cargar_cliente)

    @app.template_filter("pesos")
    def formato_pesos(valor):
        try:
            return f"{float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        except (ValueError, TypeError):
            return str(valor)

    @app.template_filter("wa_link")
    def formato_wa_link(telefono):
        return wa_url(telefono)

    @app.context_processor
    def _inject_carrito():
        from services.carrito import carrito_count
        try:
            return {"carrito_count": carrito_count()}
        except Exception:
            return {"carrito_count": 0}

    @app.context_processor
    def _inject_anuncio():
        from models import get_anuncio_franja
        try:
            return {"anuncio_franja_texto": get_anuncio_franja()}
        except Exception:
            return {"anuncio_franja_texto": ""}

    @app.context_processor
    def _inject_whatsapp():
        from models import get_contacto_whatsapp
        try:
            return {"contacto_whatsapp": get_contacto_whatsapp()}
        except Exception:
            return {"contacto_whatsapp": ""}

    @app.context_processor
    def _inject_direccion():
        # F2: mismo dato que ya se usa para el pago en efectivo — una sola
        # fuente para no tener la dirección cargada dos veces.
        from models import get_config
        try:
            return {"contacto_direccion": get_config("pago_efectivo_direccion", "")}
        except Exception:
            return {"contacto_direccion": ""}

    @app.context_processor
    def _inject_contacto_footer():
        from models import get_config
        try:
            return {
                "contacto_email": get_config("contacto_email", ""),
                "contacto_horarios": get_config("contacto_horarios", ""),
            }
        except Exception:
            return {"contacto_email": "", "contacto_horarios": ""}

    app.register_blueprint(auth_bp)
    app.register_blueprint(catalogo_bp)
    app.register_blueprint(carrito_bp)
    app.register_blueprint(pedidos_bp)
    app.register_blueprint(api_interna_bp)

    # La API interna se autentica por API key, no por sesión de navegador.
    csrf.exempt(api_interna_bp)

    @app.route("/")
    def home():
        if g.get("cliente_id"):
            return redirect(url_for("catalogo.index"))

        from models import get_config, get_minimo_compra
        from services.comenda_api_client import get_destacados

        monto_minimo, unidades_minimo = get_minimo_compra()

        skus_csv = get_config("landing_skus_destacados", "")
        skus = [s.strip() for s in skus_csv.split(",") if s.strip()]
        try:
            destacados = get_destacados(skus) if skus else []
        except Exception:
            # Red de seguridad final: la home es pública, no puede caerse
            # por esta sección bajo ninguna circunstancia.
            destacados = []

        hero_foto_existe = os.path.isfile(os.path.join(app.static_folder, "landing", "hero.jpg"))
        local_foto_existe = os.path.isfile(os.path.join(app.static_folder, "landing", "local.jpg"))

        # contacto_whatsapp/email/direccion/horarios ya llegan por los
        # context_processors de más abajo — no hace falta repetirlos acá.
        whatsapp = get_config("contacto_whatsapp", "")
        return render_template(
            "landing.html",
            monto_minimo=monto_minimo,
            unidades_minimo=unidades_minimo,
            destacados=destacados,
            hero_foto_existe=hero_foto_existe,
            hero_foto_url=url_for("static", filename="landing/hero.jpg", _external=True) if hero_foto_existe else "",
            local_foto_existe=local_foto_existe,
            landing_url=url_for("home", _external=True),
            redes_instagram=get_config("redes_instagram", ""),
            quienes_somos_texto=get_config("quienes_somos_texto", ""),
            debug_mode=Config.DEBUG,
            whatsapp_bubble_link=wa_url(
                whatsapp, "Hola, quiero consultar por la venta mayorista"
            ) if whatsapp else "",
        )

    @app.route("/robots.txt")
    def robots_txt():
        return send_from_directory(app.static_folder, "robots.txt")

    @app.route("/sitemap.xml")
    def sitemap_xml():
        return send_from_directory(app.static_folder, "sitemap.xml")

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=Config.DEBUG, host="0.0.0.0", port=Config.PORT)
