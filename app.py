# app.py — Portal Mayorista (servicio independiente, puerto 5001)
import os
import time
import logging

from flask import Flask, g, redirect, url_for
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
        return redirect(url_for("auth.login"))

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=Config.DEBUG, host="0.0.0.0", port=Config.PORT)
