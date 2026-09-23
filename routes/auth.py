# routes/auth.py — registro, login, logout y recuperación de contraseña
import re
import secrets
import hashlib
import logging
from datetime import datetime, timedelta

from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, session, g,
    current_app,
)
from werkzeug.security import generate_password_hash, check_password_hash

from config import Config
from models import (
    get_conn, get_cliente_por_email, crear_cliente,
    crear_password_reset, validar_token_reset, consumir_password_reset,
    reset_rate_limit_permitido, reset_registrar_intento,
)
from services.comenda_api_client import avisar_cuenta_nueva
from services.mailer import enviar_email_reset, mail_configurado

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


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
        # E2: el saludo pasó a la barra superior (ver base.html), ya no hace
        # falta un flash de bienvenida en cada login.
        session["epoch"] = cli["sesion_epoch"]
        return redirect(url_for("catalogo.index"))

    return render_template("login.html", email="")


@auth_bp.route("/logout")
def logout():
    session.clear()
    # Sin flash: el landing (templates/landing.html) es standalone y no
    # renderiza mensajes flash — este quedaría en la sesión y le aparecería
    # descolgado al usuario en la primera pantalla del portal que visite
    # después. Caer en la página pública ya avisa que cerró sesión.
    return redirect(url_for("home"))


# ── Recuperación de contraseña (D1) ─────────────────────────────────────────

@auth_bp.route("/recuperar", methods=["GET", "POST"])
def recuperar():
    if g.get("cliente_id"):
        return redirect(url_for("catalogo.index"))

    # Arreglo posterior a D1: sin esto, pedir un reset sin proveedor de mail
    # configurado terminaba en un 500 — inaceptable para una función que se
    # ofrece en pantalla. Se corta ACÁ, antes de tocar rate limit o generar
    # ningún token (la maquinaria de reset queda intacta, se activa sola
    # apenas mail_configurado() empiece a dar True). El modo se detecta por
    # configuración (mail_configurado / debug / el flag de log), nunca por
    # una constante hardcodeada.
    if not (mail_configurado() or current_app.debug or Config.RESET_LOG_LINK_FALLBACK):
        return render_template("recuperar.html", sin_servicio=True)

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        ip = request.remote_addr or "0.0.0.0"

        # Respuesta genérica siempre — nunca revela si el email existe.
        # d1.a/d1.h: el intento de "enviar" (con su fallback de log detrás de
        # debug/flag, o su falla ruidosa si no hay nada configurado) solo se
        # dispara cuando la cuenta existe y no está limitada por rate limit;
        # si eso revienta, el 500 resultante es distinto de la respuesta
        # genérica — tradeoff explícito, documentado en el reporte del grupo.
        if reset_rate_limit_permitido(
            "solicitud_ip", ip, Config.RESET_MAX_SOLICITUDES_IP, Config.RESET_SOLICITUDES_VENTANA_MIN
        ):
            reset_registrar_intento("solicitud_ip", ip)
            cli = get_cliente_por_email(email) if email else None
            # D1.d: se permite pedir/usar el reset con la cuenta en cualquier
            # estado (pendiente/rechazada/suspendida incluidas) — el login
            # sigue bloqueando por estado después, sin importar la contraseña.
            if cli and reset_rate_limit_permitido(
                "solicitud_email", email, Config.RESET_MAX_SOLICITUDES_EMAIL,
                Config.RESET_SOLICITUDES_VENTANA_MIN
            ):
                reset_registrar_intento("solicitud_email", email)
                token = secrets.token_urlsafe(32)
                crear_password_reset(cli["id"], _hash_token(token), Config.RESET_TOKEN_TTL_MIN)
                link = url_for("auth.reset_validar", token=token, _external=True)
                enviar_email_reset(cli["email"], link)

        flash(
            "Si ese email tiene una cuenta con nosotros, te mandamos instrucciones "
            "para recuperar la contraseña.", "info"
        )
        return redirect(url_for("auth.login"))

    return render_template("recuperar.html")


@auth_bp.route("/reset/<token>")
def reset_validar(token):
    """Primer y único GET con el token en la URL. No renderiza nada del
    layout normal (nada de CSS de jsdelivr) — solo valida y redirige, así el
    token nunca queda expuesto como Referer de un pedido a un tercero (D1.b:
    de las dos alternativas que planteamos, esta — token en sesión del lado
    del servidor en vez de en la URL — es la que se implementó)."""
    ip = request.remote_addr or "0.0.0.0"
    if not reset_rate_limit_permitido(
        "validacion_ip", ip, Config.RESET_MAX_VALIDACIONES_IP, Config.RESET_VALIDACIONES_VENTANA_MIN
    ):
        flash("Demasiados intentos. Probá de nuevo más tarde.", "error")
        return redirect(url_for("auth.login"))
    reset_registrar_intento("validacion_ip", ip)

    token_hash = _hash_token(token)
    cliente_id = validar_token_reset(token_hash)
    if cliente_id is None:
        flash("El link de recuperación no es válido o ya venció. Pedí uno nuevo.", "error")
        return redirect(url_for("auth.recuperar"))

    session["reset_cliente_id"] = cliente_id
    session["reset_token_hash"] = token_hash
    return redirect(url_for("auth.reset_completar"))


@auth_bp.route("/reset/completar", methods=["GET", "POST"])
def reset_completar():
    cliente_id = session.get("reset_cliente_id")
    token_hash = session.get("reset_token_hash")
    if not cliente_id or not token_hash:
        flash("Tu sesión de recuperación expiró. Pedí un link nuevo.", "error")
        return redirect(url_for("auth.recuperar"))

    if request.method == "POST":
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")

        errores = []
        if len(password) < 8:  # D1.e: misma política que el registro
            errores.append("La contraseña debe tener al menos 8 caracteres.")
        if password != password2:
            errores.append("Las contraseñas no coinciden.")
        if errores:
            for e in errores:
                flash(e, "error")
            return render_template("reset_completar.html")

        ok = consumir_password_reset(cliente_id, token_hash, generate_password_hash(password))
        session.pop("reset_cliente_id", None)
        session.pop("reset_token_hash", None)
        if not ok:
            flash("El link de recuperación no es válido o ya venció. Pedí uno nuevo.", "error")
            return redirect(url_for("auth.recuperar"))

        # D1.f
        flash("Contraseña actualizada. Ya podés ingresar.", "success")
        return redirect(url_for("auth.login"))

    return render_template("reset_completar.html")
