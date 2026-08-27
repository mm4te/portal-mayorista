# routes/carrito.py — carrito de compras y envío de pedido
import logging

from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, g, jsonify
)

from routes import login_required
from services import carrito as cart
from services import comenda_api_client
from services.comenda_api_client import ComendaAPIError
from models import crear_pedido_enviado

logger = logging.getLogger(__name__)

carrito_bp = Blueprint("carrito", __name__)


def _payload():
    """Lee sku/cantidad tanto de JSON como de form (los endpoints del carrito
    se usan vía fetch, pero aceptar form no cuesta nada)."""
    data = request.get_json(silent=True) or request.form or {}
    sku = (str(data.get("sku") or "")).strip()
    try:
        cantidad = int(data.get("cantidad", 1))
    except (TypeError, ValueError):
        cantidad = 1
    return sku, cantidad


def _estado_carrito(extra=None):
    resp = {
        "ok": True,
        "total_items": cart.carrito_count(),
        "total": cart.total_carrito(),
    }
    if extra:
        resp.update(extra)
    return jsonify(resp)


@carrito_bp.route("/carrito")
@login_required
def ver():
    return render_template(
        "carrito.html",
        items=cart.get_carrito(),
        total=cart.total_carrito(),
    )


@carrito_bp.route("/carrito/agregar", methods=["POST"])
@login_required
def agregar():
    sku, cantidad = _payload()
    cantidad = max(1, min(99, cantidad))
    if not sku:
        return jsonify({"ok": False, "error": "Producto inválido."}), 400

    # Nombre y precio autoritativos: se resuelven contra el catálogo del
    # sistema principal, no desde el cliente (evita manipulación de precios).
    try:
        prod = comenda_api_client.buscar_en_catalogo(sku)
    except ComendaAPIError as e:
        logger.warning("agregar al carrito: %s", e)
        return jsonify({"ok": False, "error": "No se pudo contactar al sistema. Probá de nuevo."}), 502

    if not prod:
        return jsonify({"ok": False, "error": "El producto ya no está en el catálogo."}), 404
    if not prod.get("disponible"):
        return jsonify({"ok": False, "error": f"«{prod['nombre']}» está sin stock."}), 409

    cart.agregar(sku, prod["nombre"], prod["precio_mayorista"], cantidad)
    return _estado_carrito({"nombre": prod["nombre"]})


@carrito_bp.route("/carrito/actualizar", methods=["POST"])
@login_required
def actualizar():
    sku, cantidad = _payload()
    if not sku:
        return jsonify({"ok": False, "error": "Ítem inválido."}), 400
    cantidad = max(0, min(99, cantidad))
    cart.actualizar_cantidad(sku, cantidad)
    sub = next(
        (i["precio"] * i["cantidad"] for i in cart.get_carrito() if i["sku"] == sku), 0
    )
    return _estado_carrito({"item_subtotal": sub, "removido": cantidad <= 0})


@carrito_bp.route("/carrito/quitar", methods=["POST"])
@login_required
def quitar():
    sku, _ = _payload()
    cart.quitar(sku)
    return _estado_carrito({"removido": True})


@carrito_bp.route("/carrito/enviar", methods=["POST"])
@login_required
def enviar():
    items = cart.get_carrito()
    if not items:
        flash("Tu carrito está vacío.", "error")
        return redirect(url_for("catalogo.index"))

    try:
        pedido_id, numero, subtotal = crear_pedido_enviado(g.cliente_id, items)
    except Exception as e:
        logger.error("enviar pedido falló: %s", e, exc_info=True)
        flash("No se pudo enviar el pedido. Probá de nuevo.", "error")
        return redirect(url_for("carrito.ver"))

    cart.vaciar()

    # Avisar a Comenda para que revise y confirme stock (best-effort).
    comenda_api_client.avisar_pedido_nuevo({
        "pedido_id": pedido_id,
        "numero": numero,
        "cliente_empresa": g.cliente["nombre_empresa"],
        "subtotal": subtotal,
        "items": [{"sku": i["sku"], "cantidad": int(i["cantidad"])} for i in items],
    })

    flash(f"Pedido {numero} enviado. Vamos a revisar el stock y te avisamos.", "success")
    return redirect(url_for("pedidos.detalle", pedido_id=pedido_id))
