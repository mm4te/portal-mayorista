# routes/auth.py — registro, login y logout de clientes mayoristas
import re
import logging
from datetime import datetime, timedelta

from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, session, g
)
from werkzeug.security import generate_password_hash, check_password_hash

from config import Config
from models import get_conn, get_cliente_por_email, crear_cliente
from services.comenda_api_client import avisar_cuenta_nueva

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ── Rate limiting del registro ──────────────────────────────────────────────

def _registro_permitido(ip):
    """True si la IP no superó REGISTRO_MAX_POR_IP altas en la ventana."""
    limite = (datetime.now() - timedelta(minutes=Config.REGISTRO_VENTANA_MIN)).strftime("%Y-%m-%d %H:%M:%S")
    conn = get_conn()
    try:
        n = conn.execute(
            "SELECT COUNT(*) FROM registro_intentos WHERE ip = ? AND fecha >= ?",
            (ip, limite)
        ).fetchone()[0]
        return n < Config.REGISTRO_MAX_POR_IP
    finally:
        conn.close()


def _registrar_intento(ip):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO registro_intentos (ip, fecha) VALUES (?, ?)",
            (ip, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        conn.commit()
    finally:
        conn.close()


def _limpiar_cuit(cuit):
    return re.sub(r"\D", "", cuit or "")


# ── Registro ───────────────────────────────────────────────────────────────

@auth_bp.route("/registro", methods=["GET", "POST"])
def registro():
    if g.get("cliente_id"):
        return redirect(url_for("catalogo.index"))

    if request.method == "POST":
        form = {
            "nombre_empresa": request.form.get("nombre_empresa", "").strip(),
            "cuit": request.form.get("cuit", "").strip(),
            "telefono": request.form.get("telefono", "").strip(),
            "email": request.form.get("email", "").strip().lower(),
        }
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")

        errores = []
        if not form["nombre_empresa"]:
            errores.append("El nombre de la empresa es obligatorio.")
        if not _EMAIL_RE.match(form["email"]):
            errores.append("El email no es válido.")
        cuit_digitos = _limpiar_cuit(form["cuit"])
        if cuit_digitos and len(cuit_digitos) != 11:
            errores.append("El CUIT debe tener 11 dígitos.")
        if len(password) < 8:
            errores.append("La contraseña debe tener al menos 8 caracteres.")
        if password != password2:
            errores.append("Las contraseñas no coinciden.")

        ip = request.remote_addr or "0.0.0.0"
        if not errores and not _registro_permitido(ip):
            errores.append("Demasiados registros desde esta conexión. Probá más tarde.")

        if not errores and get_cliente_por_email(form["email"]):
            errores.append("Ya existe una cuenta con ese email.")

        if errores:
            for e in errores:
                flash(e, "error")
            return render_template("registro.html", form=form)

        cliente_id = crear_cliente(
            form["nombre_empresa"], form["cuit"] or None, form["telefono"] or None,
            form["email"], generate_password_hash(password),
        )
        _registrar_intento(ip)

        # Avisar a Comenda que hay una cuenta nueva por aprobar (best-effort)
        avisar_cuenta_nueva({
            "id": cliente_id,
            "nombre_empresa": form["nombre_empresa"],
            "cuit": form["cuit"],
            "telefono": form["telefono"],
            "email": form["email"],
        })

        logger.info("Registro mayorista nuevo: %s (id=%s)", form["email"], cliente_id)
        return render_template("registro_ok.html")

    return render_template("registro.html", form={})


# ── Login / Logout ─────────────────────────────────────────────────────────

_MENSAJE_ESTADO = {
    "pendiente_aprobacion": ("Tu cuenta todavía está pendiente de aprobación. "
                             "Te contactaremos apenas esté lista.", "info"),
    "rechazado": ("Tu solicitud de cuenta fue rechazada. "
                  "Escribinos si creés que es un error.", "error"),
    "suspendido": ("Tu cuenta está suspendida. Contactate con Comenda.", "error"),
}


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if g.get("cliente_id"):
        return redirect(url_for("catalogo.index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        cli = get_cliente_por_email(email)

        if not cli or not check_password_hash(cli["password_hash"], password):
            flash("Email o contraseña incorrectos.", "error")
            return render_template("login.html", email=email)

        if cli["estado"] != "aprobado":
            msg, cat = _MENSAJE_ESTADO.get(
                cli["estado"], ("Tu cuenta no está habilitada para ingresar.", "error")
            )
            flash(msg, cat)
            return render_template("login.html", email=email)

        session.clear()
        session["cliente_id"] = cli["id"]
        flash(f"¡Hola, {cli['nombre_empresa']}!", "success")
        return redirect(url_for("catalogo.index"))

    return render_template("login.html", email="")


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("Cerraste sesión.", "success")
    return redirect(url_for("auth.login"))
