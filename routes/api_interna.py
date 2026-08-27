# routes/api_interna.py
"""
API interna del portal, consumida por comenda-sistema (sentido inverso).

Mismo esquema de autenticación que la API interna de comenda-sistema:
header  X-Internal-Key: {INTERNAL_API_KEY}.

FASE 2:
  GET  /api/interno/mayoristas-pendientes
  POST /api/interno/aprobar-mayorista/<id>
  POST /api/interno/rechazar-mayorista/<id>

(FASE 5 agregará: pedidos-pendientes-mayorista, marcar-pedido-confirmado/<id>,
 marcar-pedido-pagado/<id>.)
"""
import hmac
import logging
from functools import wraps

from flask import Blueprint, request, jsonify

from config import Config
from models import (
    listar_clientes_por_estado, actualizar_estado_cliente, get_cliente,
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
