# routes/api_interna.py
"""
API interna del portal, consumida por comenda-sistema (sentido inverso).

Mismo esquema de autenticación que la API interna de comenda-sistema:
header  X-Internal-Key: {INTERNAL_API_KEY}.

FASE 2 (cuentas):
  GET  /api/interno/mayoristas-pendientes
  POST /api/interno/aprobar-mayorista/<id>
  POST /api/interno/rechazar-mayorista/<id>

FASE 7 (gestión completa de cuentas):
  GET  /api/interno/mayoristas-todos?estado=todos|pendiente_aprobacion|aprobado|rechazado|suspendido
  POST /api/interno/editar-mayorista/<id>
  POST /api/interno/suspender-mayorista/<id>
  POST /api/interno/reactivar-mayorista/<id>
  POST /api/interno/eliminar-mayorista/<id>

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
import re
from functools import wraps

from flask import Blueprint, request, jsonify

from config import Config
from models import (
    ESTADOS_CLIENTE,
    listar_clientes_por_estado, actualizar_estado_cliente, get_cliente,
    listar_clientes_todos, contar_pedidos_cliente, actualizar_datos_cliente,
    eliminar_cliente, get_cliente_por_email,
    listar_pedidos_pendientes, get_pedido_con_cliente, get_pedido_items,
    registrar_verificacion_stock, marcar_pedido_confirmado,
    marcar_pedido_rechazado_sin_stock, marcar_pedido_pagado,
    ajustar_item_pedido,
)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

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


# ── Gestión completa de cuentas (FASE 7) ─────────────────────────────────────

@api_interna_bp.get("/mayoristas-todos")
@requiere_api_key
def mayoristas_todos():
    estado = request.args.get("estado", "todos")
    if estado != "todos" and estado not in ESTADOS_CLIENTE:
        return jsonify({"error": "Estado inválido"}), 400
    clientes = listar_clientes_todos(None if estado == "todos" else estado)
    resultado = []
    for c in clientes:
        d = _cliente_dict(c)
        d["total_pedidos"] = c["total_pedidos"]
        d["total_comprado"] = c["total_comprado"]
        resultado.append(d)
    return jsonify(resultado)


@api_interna_bp.post("/editar-mayorista/<int:cliente_id>")
@requiere_api_key
def editar_mayorista(cliente_id):
    data = request.get_json(silent=True) or {}
    cli = get_cliente(cliente_id)
    if cli is None:
        return jsonify({"error": "Cliente no encontrado"}), 404

    nombre_empresa = (data.get("nombre_empresa") or "").strip()
    cuit = re.sub(r"\D", "", data.get("cuit") or "")
    telefono = (data.get("telefono") or "").strip()
    email = (data.get("email") or "").strip().lower()

    if not nombre_empresa:
        return jsonify({"error": "El nombre de la empresa es obligatorio"}), 400
    if cuit and len(cuit) != 11:
        return jsonify({"error": "El CUIT debe tener 11 dígitos"}), 400
    if not _EMAIL_RE.match(email):
        return jsonify({"error": "El email no es válido"}), 400

    existente = get_cliente_por_email(email)
    if existente and existente["id"] != cliente_id:
        return jsonify({"error": "Ya existe otra cuenta con ese email"}), 400

    ok = actualizar_datos_cliente(cliente_id, nombre_empresa, cuit or None, telefono or None, email)
    if not ok:
        return jsonify({"error": "No se pudo actualizar"}), 400
    logger.info("Mayorista #%s editado", cliente_id)
    return jsonify({"ok": True})


@api_interna_bp.post("/suspender-mayorista/<int:cliente_id>")
@requiere_api_key
def suspender_mayorista(cliente_id):
    data = request.get_json(silent=True) or {}
    cli = get_cliente(cliente_id)
    if cli is None:
        return jsonify({"error": "Cliente no encontrado"}), 404
    if cli["estado"] == "suspendido":
        return jsonify({"ok": True, "estado": "suspendido", "sin_cambios": True})

    ok = actualizar_estado_cliente(cliente_id, "suspendido", aprobado_por=data.get("usuario"))
    if not ok:
        return jsonify({"error": "No se pudo actualizar"}), 400
    logger.info("Mayorista #%s suspendido por %s", cliente_id, data.get("usuario"))
    return jsonify({"ok": True, "estado": "suspendido"})


@api_interna_bp.post("/reactivar-mayorista/<int:cliente_id>")
@requiere_api_key
def reactivar_mayorista(cliente_id):
    data = request.get_json(silent=True) or {}
    cli = get_cliente(cliente_id)
    if cli is None:
        return jsonify({"error": "Cliente no encontrado"}), 404
    if cli["estado"] == "aprobado":
        return jsonify({"ok": True, "estado": "aprobado", "sin_cambios": True})

    ok = actualizar_estado_cliente(cliente_id, "aprobado", aprobado_por=data.get("usuario"))
    if not ok:
        return jsonify({"error": "No se pudo actualizar"}), 400
    logger.info("Mayorista #%s reactivado por %s", cliente_id, data.get("usuario"))
    return jsonify({"ok": True, "estado": "aprobado"})


@api_interna_bp.post("/eliminar-mayorista/<int:cliente_id>")
@requiere_api_key
def eliminar_mayorista(cliente_id):
    cli = get_cliente(cliente_id)
    if cli is None:
        return jsonify({"error": "Cliente no encontrado"}), 404

    tiene_pedidos = contar_pedidos_cliente(cliente_id)
    if tiene_pedidos > 0:
        return jsonify({
            "error": f"Tiene {tiene_pedidos} pedido(s) asociado(s). Suspendé la cuenta en su lugar."
        }), 400

    eliminar_cliente(cliente_id)
    logger.info("Mayorista #%s eliminado", cliente_id)
    return jsonify({"ok": True})


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
                "item_id": it["id"],
                "sku": it["sku"],
                "nombre_producto": it["nombre_producto"],
                "cantidad": it["cantidad"],
                "cantidad_ajustada": it["cantidad_ajustada"],
                "cantidad_efectiva": it["cantidad_ajustada"] if it["cantidad_ajustada"] is not None else it["cantidad"],
                "precio_unitario_mayorista": it["precio_unitario_mayorista"],
                "disponible_confirmado": it["disponible_confirmado"],
                "stock_disponible_verificado": it["stock_disponible_verificado"],
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
    ok, err = registrar_verificacion_stock(
        pedido_id, data.get("detalle"), usuario=data.get("verificado_por")
    )
    if not ok:
        return jsonify({"error": err}), 400
    return jsonify({"ok": True, "estado": "confirmando_stock"})


@api_interna_bp.post("/ajustar-item-pedido/<int:pedido_id>/<int:item_id>")
@requiere_api_key
def ajustar_item_pedido_route(pedido_id, item_id):
    data = request.get_json(silent=True) or {}
    ok, err, extra = ajustar_item_pedido(
        pedido_id, item_id, data.get("nueva_cantidad"),
        ajustado_por=data.get("ajustado_por"),
    )
    if not ok:
        return jsonify({"error": err}), 400
    logger.info("Pedido #%s ítem %s ajustado por %s", pedido_id, item_id, data.get("ajustado_por"))
    return jsonify({"ok": True, "subtotal": extra["subtotal"]})


@api_interna_bp.post("/marcar-pedido-confirmado/<int:pedido_id>")
@requiere_api_key
def marcar_pedido_confirmado_route(pedido_id):
    data = request.get_json(silent=True) or {}
    ok, err = marcar_pedido_confirmado(pedido_id, usuario=data.get("confirmado_por"))
    if not ok:
        return jsonify({"error": err}), 400
    logger.info("Pedido #%s confirmado (esperando pago)", pedido_id)
    return jsonify({"ok": True, "estado": "confirmado_esperando_pago"})


@api_interna_bp.post("/rechazar-pedido-sin-stock/<int:pedido_id>")
@requiere_api_key
def rechazar_pedido_sin_stock_route(pedido_id):
    data = request.get_json(silent=True) or {}
    ok, err = marcar_pedido_rechazado_sin_stock(pedido_id, usuario=data.get("rechazado_por"))
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
    ok, err = marcar_pedido_pagado(pedido_id, venta_id, usuario=data.get("pagado_por"))
    if not ok:
        return jsonify({"error": err}), 400
    logger.info("Pedido #%s marcado como pagado (venta %s)", pedido_id, venta_id)
    return jsonify({"ok": True, "estado": "pagado"})
