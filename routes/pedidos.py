# routes/pedidos.py — pedidos del cliente mayorista
from flask import Blueprint, render_template, abort, g

from routes import login_required
from models import listar_pedidos_cliente, get_pedido, get_pedido_items

pedidos_bp = Blueprint("pedidos", __name__)

# Etiquetas legibles para el cliente
ESTADO_LABEL = {
    "carrito": "En carrito",
    "enviado": "Enviado — pendiente de revisión",
    "confirmando_stock": "Revisando stock",
    "confirmado_esperando_pago": "Confirmado — elegí método de pago",
    "pagado": "Pagado",
    "rechazado_sin_stock": "Rechazado por falta de stock",
    "cancelado": "Cancelado",
}


@pedidos_bp.route("/pedidos")
@login_required
def lista():
    pedidos = listar_pedidos_cliente(g.cliente_id)
    return render_template("pedidos_lista.html", pedidos=pedidos, estado_label=ESTADO_LABEL)


@pedidos_bp.route("/pedidos/<int:pedido_id>")
@login_required
def detalle(pedido_id):
    pedido = get_pedido(pedido_id, cliente_id=g.cliente_id)
    if pedido is None:
        abort(404)
    items = get_pedido_items(pedido_id)
    return render_template(
        "pedido_detalle.html",
        pedido=pedido, items=items, estado_label=ESTADO_LABEL,
    )
