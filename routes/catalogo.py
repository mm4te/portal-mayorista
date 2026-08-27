# routes/catalogo.py — catálogo mayorista (consume la API interna de comenda-sistema)
import logging

from flask import Blueprint, render_template, request, g

from routes import login_required
from services import comenda_api_client
from services.comenda_api_client import ComendaAPIError

logger = logging.getLogger(__name__)

catalogo_bp = Blueprint("catalogo", __name__)


@catalogo_bp.route("/catalogo")
@login_required
def index():
    q = (request.args.get("q") or "").strip()

    error = None
    productos = []
    try:
        productos = comenda_api_client.get_catalogo()
    except ComendaAPIError as e:
        error = str(e)
        logger.warning("catalogo: %s", e)

    if q:
        ql = q.lower()
        productos = [
            p for p in productos
            if ql in (p.get("nombre") or "").lower()
            or ql in (p.get("sku") or "").lower()
        ]

    return render_template(
        "catalogo.html",
        productos=productos, q=q, error=error, cliente=g.cliente,
    )
