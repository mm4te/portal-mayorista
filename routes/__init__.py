# routes/__init__.py
from functools import wraps

from flask import session, redirect, url_for, flash, g

from models import get_cliente


def cargar_cliente():
    """before_request: expone g.cliente / g.cliente_id a partir de la sesión."""
    g.cliente = None
    g.cliente_id = session.get("cliente_id")
    if g.cliente_id:
        cli = get_cliente(g.cliente_id)
        # sesion_epoch: la sesión es una cookie firmada del lado del cliente,
        # no hay tabla de sesiones — si no coincide con el epoch actual de la
        # cuenta es porque se reseteó la contraseña (D1.c) después de que se
        # emitió esta cookie, así que se trata como sesión inválida.
        epoch_ok = cli is not None and session.get("epoch") == cli["sesion_epoch"]
        if cli is None or cli["estado"] != "aprobado" or not epoch_ok:
            # La cuenta dejó de estar aprobada (suspendida, etc.) o la sesión
            # quedó vieja → cerrar sesión.
            session.clear()
            g.cliente_id = None
        else:
            g.cliente = cli


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not g.get("cliente_id"):
            flash("Iniciá sesión para continuar.", "error")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return wrapper
