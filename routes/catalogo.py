# routes/catalogo.py
"""Catálogo de productos (FASE 3). Por ahora solo el panel del cliente."""
from flask import Blueprint, render_template, g

from routes import login_required

catalogo_bp = Blueprint("catalogo", __name__)


@catalogo_bp.route("/catalogo")
@login_required
def index():
    # FASE 3 reemplaza esto por la grilla real consumiendo la API interna.
    return render_template("dashboard.html", cliente=g.cliente)
