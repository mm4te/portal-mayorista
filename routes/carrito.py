# routes/carrito.py — carrito de compras y envío de pedido
import logging

from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, g
)

from routes import login_required
from services import carrito as cart
from services import comenda_api_client
from services.comenda_api_client import ComendaAPIError
from models import crear_pedido_enviado

logger = logging.getLogger(__name__)

carrito_bp = Blueprint("carrito", __name__)


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
    sku = (request.form.get("sku") or "").strip()
    try:
        cantidad = int(request.form.get("cantidad", 1))
    except ValueError:
        cantidad = 1

    if not sku:
        flash("Producto inválido.", "error")
        return redirect(url_for("catalogo.index"))

    # Nombre y precio autoritativos: se resuelven contra el catálogo del
    # sistema principal, no desde el formulario (evita manipulación de precios).
    try:
        prod = comenda_api_client.buscar_en_catalogo(sku)
    except ComendaAPIError as e:
        flash(f"No se pudo verificar el producto: {e}", "error")
        return redirect(url_for("catalogo.index"))

    if not prod:
        flash("El producto ya no está disponible en el catálogo.", "error")
        return redirect(url_for("catalogo.index"))
    if not prod.get("disponible"):
        flash(f"«{prod['nombre']}» está sin stock.", "error")
        return redirect(url_for("catalogo.index"))

    cart.agregar(sku, prod["nombre"], prod["precio_mayorista"], cantidad)
    flash(f"«{prod['nombre']}» agregado al carrito.", "success")
    return redirect(request.referrer or url_for("catalogo.index"))


@carrito_bp.route("/carrito/actualizar", methods=["POST"])
@login_required
def actualizar():
    sku = (request.form.get("sku") or "").strip()
    try:
        cantidad = int(request.form.get("cantidad", 1))
    except ValueError:
        cantidad = 1
    cart.actualizar_cantidad(sku, cantidad)
    return redirect(url_for("carrito.ver"))


@carrito_bp.route("/carrito/quitar", methods=["POST"])
@login_required
def quitar():
    cart.quitar((request.form.get("sku") or "").strip())
    return redirect(url_for("carrito.ver"))


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
