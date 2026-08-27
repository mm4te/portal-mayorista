# routes/pedidos.py — pedidos del cliente mayorista
from flask import (
    Blueprint, render_template, redirect, url_for, flash, request, abort, g
)

from routes import login_required
from models import (
    listar_pedidos_cliente, get_pedido, get_pedido_items, get_config,
    elegir_metodo_pago,
)

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


def _datos_pago():
    return {
        "efectivo_direccion": get_config("pago_efectivo_direccion", "Paso 559, CABA"),
        "transferencia": {
            "banco": get_config("pago_transferencia_banco", ""),
            "cbu": get_config("pago_transferencia_cbu", ""),
            "alias": get_config("pago_transferencia_alias", ""),
            "titular": get_config("pago_transferencia_titular", ""),
            "cuit": get_config("pago_transferencia_cuit", ""),
        },
        "contacto_comprobante": get_config("contacto_comprobante", ""),
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
        datos_pago=_datos_pago(),
    )


@pedidos_bp.route("/pedidos/<int:pedido_id>/pago", methods=["POST"])
@login_required
def elegir_pago(pedido_id):
    metodo = (request.form.get("metodo") or "").strip()
    ok, err = elegir_metodo_pago(pedido_id, g.cliente_id, metodo)
    if not ok:
        flash(err or "No se pudo registrar el método de pago.", "error")
    else:
        flash("Método de pago registrado. Seguí las instrucciones para abonar.", "success")
    return redirect(url_for("pedidos.detalle", pedido_id=pedido_id))
