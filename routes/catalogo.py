# routes/catalogo.py — catálogo mayorista (consume la API interna de comenda-sistema)
import logging
import re
import unicodedata

from flask import Blueprint, render_template, request, g, abort

from routes import login_required
from services import comenda_api_client
from services.comenda_api_client import ComendaAPIError

logger = logging.getLogger(__name__)

catalogo_bp = Blueprint("catalogo", __name__)


def _normalizar(texto):
    """Minúsculas y sin diacríticos: "Almohadón" y "Almohadon" tienen que
    ser la misma palabra (el catálogo tiene las dos grafías)."""
    descompuesto = unicodedata.normalize("NFD", texto or "")
    return "".join(ch for ch in descompuesto if not unicodedata.combining(ch)).lower()


def _grupo_matchea(p, q):
    """Búsqueda a nivel de grupo (una card). Matchea si:
      · el SKU de CUALQUIERA de sus variantes empieza con lo buscado, o
      · cada palabra buscada es el comienzo de alguna palabra del nombre
        ("knot" → "Almohadón Knot"; "alm kn" también).

    ESPEJO de coincide() en templates/catalogo.html — si se cambia una, se
    cambia la otra. Con JS manda la del cliente (ver index()); esta es la
    que ve quien navega sin JS."""
    qn = _normalizar(q).strip()
    if not qn:
        return True
    if any(_normalizar(v.get("sku")).startswith(qn) for v in p.get("variantes", [])):
        return True
    palabras = [w for w in re.split(r"[^a-z0-9]+", _normalizar(p.get("nombre_base"))) if w]
    tokens = [t for t in re.split(r"[^a-z0-9]+", qn) if t]
    return bool(tokens) and all(any(w.startswith(t) for w in palabras) for t in tokens)


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

    # La búsqueda por texto NO saca productos de la lista: se renderizan
    # todos los de la categoría y los que no matchean van con `hidden`.
    # Una sola fuente de verdad según haya JS o no:
    #   · sin JS → manda este `hidden`, calculado acá (el form hace GET).
    #   · con JS → el filtro en vivo de catalogo.html recalcula todo al
    #     cargar a partir del valor del input, así que ?q= en la URL nunca
    #     deja la grilla recortada: borrar letras vuelve a mostrar lo que el
    #     servidor habría filtrado, porque sigue estando en el DOM.
    # OJO: esto depende de que el catálogo renderice TODOS los productos en
    # una sola página. Si algún día se pagina, el filtro del cliente deja de
    # ver el resto del catálogo y la búsqueda tiene que volver al servidor.
    coincide = [_grupo_matchea(p, q) for p in productos]

    return render_template(
        "catalogo.html",
        productos=productos, coincide=coincide, n_coinciden=sum(coincide),
        categorias=categorias,
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
