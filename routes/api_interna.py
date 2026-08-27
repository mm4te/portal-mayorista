# routes/api_interna.py
"""
API interna del portal, consumida por comenda-sistema (sentido inverso).

Mismo esquema de autenticación que la API interna de comenda-sistema:
header  X-Internal-Key: {INTERNAL_API_KEY}.

FASE 2 (cuentas):
  GET  /api/interno/mayoristas-pendientes
  POST /api/interno/aprobar-mayorista/<id>
  POST /api/interno/rechazar-mayorista/<id>

FASE 4 (pedidos):
  GET  /api/interno/pedidos-pendientes-mayorista
  GET  /api/interno/pedido-mayorista/<id>
  POST /api/interno/registrar-verificacion-stock/<id>
  POST /api/interno/marcar-pedido-confirmado/<id>
  POST /api/interno/rechazar-pedido-sin-stock/<id>
  POST /api/interno/marcar-pedido-pagado/<id>
"""
import hmac
import logging
from functools import wraps

from flask import Blueprint, request, jsonify

from config import Config
from models import (
    listar_clientes_por_estado, actualizar_estado_cliente, get_cliente,
    listar_pedidos_pendientes, get_pedido_con_cliente, get_pedido_items,
    registrar_verificacion_stock, marcar_pedido_confirmado,
    marcar_pedido_rechazado_sin_stock, marcar_pedido_pagado,
)

logger = logging.getLogger(__name__)

api_interna_bp = Blueprint("api_interna", __name__, url_prefix="/api/interno")


def _key_valida(recibida):
    esperada = Config.INTERNAL_API_KEY
    if not esperada or not recibida:
        return False
    return hmac.compare_digest(str(recibida), str(esperada))


def requiere_api_key(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not _key_valida(request.headers.get("X-Internal-Key")):
            logger.warning("api_interna: sin API key válida desde %s", request.remote_addr)
            return jsonify({"error": "No autorizado"}), 401
        return f(*args, **kwargs)
    return wrapper


def _cliente_dict(c):
    return {
        "id": c["id"],
        "nombre_empresa": c["nombre_empresa"],
        "cuit": c["cuit"],
        "telefono": c["telefono"],
        "email": c["email"],
        "estado": c["estado"],
        "fecha_registro": c["fecha_registro"],
        "fecha_aprobacion": c["fecha_aprobacion"],
    }


@api_interna_bp.get("/mayoristas-pendientes")
@requiere_api_key
def mayoristas_pendientes():
    pendientes = listar_clientes_por_estado("pendiente_aprobacion")
    return jsonify([_cliente_dict(c) for c in pendientes])


@api_interna_bp.post("/aprobar-mayorista/<int:cliente_id>")
@requiere_api_key
def aprobar_mayorista(cliente_id):
    data = request.get_json(silent=True) or {}
    cli = get_cliente(cliente_id)
    if cli is None:
        return jsonify({"error": "Cliente no encontrado"}), 404
    if cli["estado"] == "aprobado":
        return jsonify({"ok": True, "estado": "aprobado", "sin_cambios": True})

    ok = actualizar_estado_cliente(
        cliente_id, "aprobado", aprobado_por=data.get("aprobado_por")
    )
    if not ok:
        return jsonify({"error": "No se pudo actualizar"}), 400
    logger.info("Mayorista #%s aprobado por %s", cliente_id, data.get("aprobado_por"))
    return jsonify({"ok": True, "estado": "aprobado"})


@api_interna_bp.post("/rechazar-mayorista/<int:cliente_id>")
@requiere_api_key
def rechazar_mayorista(cliente_id):
    data = request.get_json(silent=True) or {}
    cli = get_cliente(cliente_id)
    if cli is None:
        return jsonify({"error": "Cliente no encontrado"}), 404

    ok = actualizar_estado_cliente(
        cliente_id, "rechazado",
        aprobado_por=data.get("aprobado_por"),
        motivo_rechazo=(data.get("motivo") or "").strip() or None,
    )
    if not ok:
        return jsonify({"error": "No se pudo actualizar"}), 400
    logger.info("Mayorista #%s rechazado por %s", cliente_id, data.get("aprobado_por"))
    return jsonify({"ok": True, "estado": "rechazado"})


# ── Pedidos ─────────────────────────────────────────────────────────────────

def _pedido_dict(p, items):
    return {
        "id": p["id"],
        "numero": p["numero"],
        "estado": p["estado"],
        "subtotal": p["subtotal"],
        "fecha_creacion": p["fecha_creacion"],
        "fecha_confirmacion": p["fecha_confirmacion"],
        "metodo_pago_elegido": p["metodo_pago_elegido"],
        "venta_sistema_id": p["venta_sistema_id"],
        "cliente": {
            "nombre_empresa": p["nombre_empresa"],
            "cuit": p["cuit"],
            "telefono": p["telefono"],
            "email": p["email"],
        },
        "items": [
            {
                "sku": it["sku"],
                "nombre_producto": it["nombre_producto"],
                "cantidad": it["cantidad"],
                "precio_unitario_mayorista": it["precio_unitario_mayorista"],
                "disponible_confirmado": it["disponible_confirmado"],
            }
            for it in items
        ],
    }


@api_interna_bp.get("/pedidos-pendientes-mayorista")
@requiere_api_key
def pedidos_pendientes_mayorista():
    pedidos = listar_pedidos_pendientes()
    return jsonify([
        _pedido_dict(p, get_pedido_items(p["id"])) for p in pedidos
    ])


@api_interna_bp.get("/pedido-mayorista/<int:pedido_id>")
@requiere_api_key
def pedido_mayorista(pedido_id):
    p = get_pedido_con_cliente(pedido_id)
    if p is None:
        return jsonify({"error": "Pedido no encontrado"}), 404
    return jsonify(_pedido_dict(p, get_pedido_items(pedido_id)))


@api_interna_bp.post("/registrar-verificacion-stock/<int:pedido_id>")
@requiere_api_key
def registrar_verificacion_stock_route(pedido_id):
    data = request.get_json(silent=True) or {}
    ok, err = registrar_verificacion_stock(pedido_id, data.get("detalle"))
    if not ok:
        return jsonify({"error": err}), 400
    return jsonify({"ok": True, "estado": "confirmando_stock"})


@api_interna_bp.post("/marcar-pedido-confirmado/<int:pedido_id>")
@requiere_api_key
def marcar_pedido_confirmado_route(pedido_id):
    ok, err = marcar_pedido_confirmado(pedido_id)
    if not ok:
        return jsonify({"error": err}), 400
    logger.info("Pedido #%s confirmado (esperando pago)", pedido_id)
    return jsonify({"ok": True, "estado": "confirmado_esperando_pago"})


@api_interna_bp.post("/rechazar-pedido-sin-stock/<int:pedido_id>")
@requiere_api_key
def rechazar_pedido_sin_stock_route(pedido_id):
    ok, err = marcar_pedido_rechazado_sin_stock(pedido_id)
    if not ok:
        return jsonify({"error": err}), 400
    logger.info("Pedido #%s rechazado por falta de stock", pedido_id)
    return jsonify({"ok": True, "estado": "rechazado_sin_stock"})


@api_interna_bp.post("/marcar-pedido-pagado/<int:pedido_id>")
@requiere_api_key
def marcar_pedido_pagado_route(pedido_id):
    data = request.get_json(silent=True) or {}
    venta_id = data.get("venta_sistema_id") or data.get("venta_id")
    if venta_id is None:
        return jsonify({"error": "Falta venta_sistema_id"}), 400
    ok, err = marcar_pedido_pagado(pedido_id, venta_id)
    if not ok:
        return jsonify({"error": err}), 400
    logger.info("Pedido #%s marcado como pagado (venta %s)", pedido_id, venta_id)
    return jsonify({"ok": True, "estado": "pagado"})
