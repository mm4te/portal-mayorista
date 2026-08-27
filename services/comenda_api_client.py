# services/comenda_api_client.py
"""
Cliente HTTP de la API interna que expone comenda-sistema.

Todas las llamadas van con el header X-Internal-Key: {INTERNAL_API_KEY}.
El portal NUNCA toca negocio.db directo — este módulo es el único punto de
contacto con el stock y las ventas del sistema principal.
"""
import logging

import requests

from config import Config

logger = logging.getLogger(__name__)


class ComendaAPIError(Exception):
    """Falla de comunicación o respuesta de error de la API interna."""


def _headers():
    return {"X-Internal-Key": Config.INTERNAL_API_KEY or ""}


def _url(path):
    return f"{Config.COMENDA_API_URL}/api/interno/{path.lstrip('/')}"


def _request(method, path, *, json=None, timeout=None):
    url = _url(path)
    try:
        resp = requests.request(
            method, url, json=json, headers=_headers(),
            timeout=timeout or Config.API_TIMEOUT,
        )
    except requests.RequestException as e:
        logger.error("comenda_api %s %s: %s", method, url, e)
        raise ComendaAPIError(f"No se pudo contactar al sistema principal: {e}") from e

    if resp.status_code == 401:
        raise ComendaAPIError("API key interna inválida (401)")
    if resp.status_code >= 400:
        detalle = ""
        try:
            detalle = resp.json().get("error", "")
        except Exception:
            detalle = resp.text[:200]
        raise ComendaAPIError(f"Error {resp.status_code} del sistema principal: {detalle}")

    if resp.status_code == 204 or not resp.content:
        return None
    return resp.json()


# ── Endpoints ───────────────────────────────────────────────────────────────

def get_catalogo():
    """Lista de productos activos con precio mayorista y disponibilidad."""
    return _request("GET", "catalogo-mayorista") or []


def buscar_en_catalogo(sku):
    """Devuelve el dict del producto (o None) buscándolo en el catálogo por SKU.
    Se usa para resolver nombre/precio autoritativos al agregar al carrito."""
    sku = (sku or "").strip()
    for p in get_catalogo():
        if p.get("sku") == sku:
            return p
    return None


def get_categorias():
    """Lista de categorías de productos activos, del sistema principal."""
    return _request("GET", "categorias-mayorista") or []


def stock_disponible(sku):
    """{'sku', 'disponible', 'existe'}"""
    return _request("GET", f"stock-disponible/{sku}")


def confirmar_pedido(items):
    """items: [{'sku','cantidad'}] -> {'todo_disponible', 'detalle': [...]}"""
    return _request("POST", "confirmar-pedido-mayorista", json={"items": items})


def crear_venta(payload):
    """Crea la venta real en negocio.db. -> {'venta_id', 'creada'}"""
    return _request("POST", "crear-venta-mayorista", json=payload)


def avisar_cuenta_nueva(cliente):
    """Notifica al sistema principal que hay una cuenta mayorista por aprobar.
    Best-effort: si falla, no bloquea el registro."""
    try:
        _request("POST", "aviso-mayorista-nuevo", json=cliente, timeout=5)
        return True
    except ComendaAPIError as e:
        logger.warning("avisar_cuenta_nueva falló (no crítico): %s", e)
        return False


def avisar_pedido_nuevo(pedido):
    """Notifica al sistema principal que un mayorista envió un pedido para
    revisión de stock. Best-effort: si falla, no bloquea el envío."""
    try:
        _request("POST", "aviso-pedido-mayorista", json=pedido, timeout=5)
        return True
    except ComendaAPIError as e:
        logger.warning("avisar_pedido_nuevo falló (no crítico): %s", e)
        return False
