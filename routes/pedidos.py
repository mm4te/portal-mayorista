# routes/pedidos.py
"""Pedidos del cliente: crear, ver estado, elegir método de pago (FASE 3/4/6).
Placeholder."""
from flask import Blueprint, redirect, url_for, flash

from routes import login_required

pedidos_bp = Blueprint("pedidos", __name__)


@pedidos_bp.route("/pedidos")
@login_required
def lista():
    flash("Tus pedidos aparecerán acá pronto.", "info")
    return redirect(url_for("catalogo.index"))
