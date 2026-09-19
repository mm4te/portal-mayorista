# routes/catalogo.py — catálogo mayorista (consume la API interna de comenda-sistema)
import logging

from flask import Blueprint, render_template, request, g, abort

from routes import login_required
from services import comenda_api_client
from services.comenda_api_client import ComendaAPIError

logger = logging.getLogger(__name__)

catalogo_bp = Blueprint("catalogo", __name__)


def _grupo_matchea(p, ql):
    """Búsqueda a nivel de grupo: alcanza con que matchee el nombre base o
    el SKU de CUALQUIERA de sus variantes."""
    if ql in (p.get("nombre_base") or "").lower():
        return True
    return any(ql in (v.get("sku") or "").lower() for v in p.get("variantes", []))


@catalogo_bp.route("/catalogo")
@login_required
def index():
    q = (request.args.get("q") or "").strip()
    categoria = (request.args.get("categoria") or "").strip()

    error = None
    productos = []
    categorias = []
    try:
        # solo_disponibles: el catálogo del portal muestra únicamente lo que
        # se puede comprar; los productos/variantes sin stock no se listan,
        # y ya vienen agrupados por product_id (una card por producto).
        productos = comenda_api_client.get_catalogo(solo_disponibles=True)
        categorias = comenda_api_client.get_categorias(solo_disponibles=True)
    except ComendaAPIError as e:
        error = str(e)
        logger.warning("catalogo: %s", e)

    # E1: "Sin categorizar" no se muestra en la sidebar del cliente — es la
    # categoría default de TN para productos sin categoría propia, no algo
    # que el mayorista tenga que ver como opción de filtro. Solo se oculta
    # de esta vista, no se borra nada en comenda-sistema.
    categorias = [c for c in categorias if c != "Sin categorizar"]

    # Red de seguridad: un grupo sin ninguna variante (ej. API vieja sin
    # filtrar) no debe mostrarse.
    productos = [p for p in productos if p.get("variantes")]

    if categoria and categoria.lower() != "todas":
        # Un producto puede tener varias categorías de TN a la vez (categorias
        # es un array) — alcanza con que matchee cualquiera de ellas.
        productos = [p for p in productos if categoria in (p.get("categorias") or [])]

    if q:
        ql = q.lower()
        productos = [p for p in productos if _grupo_matchea(p, ql)]

    return render_template(
        "catalogo.html",
        productos=productos, categorias=categorias,
        categoria_activa=categoria or "Todas", q=q, error=error, cliente=g.cliente,
    )


@catalogo_bp.route("/producto/<product_id>")
@login_required
def producto_detalle(product_id):
    error = None
    producto = None
    try:
        # solo_disponibles: el selector de variante del detalle solo debe
        # ofrecer lo que el cliente puede llegar a comprar.
        producto = comenda_api_client.get_producto(product_id, solo_disponibles=True)
    except ComendaAPIError as e:
        error = str(e)
        logger.warning("producto_detalle(%s): %s", product_id, e)

    if error:
        return render_template("producto_detalle.html", producto=None, error=error, cliente=g.cliente)

    if not producto or not producto.get("variantes"):
        abort(404)

    return render_template("producto_detalle.html", producto=producto, error=None, cliente=g.cliente)
