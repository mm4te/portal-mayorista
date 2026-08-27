# routes/carrito.py
"""Carrito de compras (FASE 3). Placeholder."""
from flask import Blueprint, redirect, url_for, flash

from routes import login_required

carrito_bp = Blueprint("carrito", __name__)


@carrito_bp.route("/carrito")
@login_required
def ver():
    flash("El carrito estará disponible pronto.", "info")
    return redirect(url_for("catalogo.index"))
