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


def _request(method, path, *, json=None, params=None, timeout=None):
    url = _url(path)
    try:
        resp = requests.request(
            method, url, json=json, params=params, headers=_headers(),
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

def get_catalogo(solo_disponibles=False):
    """Catálogo agrupado por variantes: una entrada por product_id (o por sku
    para los productos sin variantes), cada una con su lista de 'variantes'.
    solo_disponibles=True pide que el sistema principal ya excluya los sin stock."""
    params = {"solo_disponibles": "true"} if solo_disponibles else None
    return _request("GET", "catalogo-mayorista", params=params) or []


def get_producto(product_id, solo_disponibles=False):
    """Detalle de un producto agrupado (todas sus variantes + descripcion_larga)
    por product_id. None si no existe (404 del sistema principal)."""
    params = {"solo_disponibles": "true"} if solo_disponibles else None
    return _request("GET", f"producto-mayorista/{product_id}", params=params)


def buscar_en_catalogo(sku):
    """Devuelve un dict plano {sku, nombre, precio_mayorista, disponible} (o
    None) buscando la variante por SKU dentro del catálogo agrupado completo.
    Se usa para resolver nombre/precio autoritativos al agregar al carrito —
    nunca confiamos en lo que manda el cliente. Busca sobre el catálogo
    completo (sin solo_disponibles) a propósito: así el carrito distingue
    «no existe» de «se quedó sin stock» y mantiene su validación.

    precio_mayorista sale de LA VARIANTE (v), no del grupo: el grupo solo
    expone el mínimo ("Desde $X" en la card) y no es el precio real de
    ninguna variante en particular si difieren entre sí (ej. Individual
    vs Set, o Chico/Mediano/Grande/Set Completo)."""
    sku = (sku or "").strip()
    if not sku:
        return None
    for grupo in get_catalogo():
        for v in grupo.get("variantes", []):
            if v.get("sku") == sku:
                nombre = grupo.get("nombre_base") or ""
                if v.get("atributo"):
                    nombre = f"{nombre} - {v['atributo']}"
                return {
                    "sku": sku,
                    "nombre": nombre,
                    "precio_mayorista": v.get("precio_mayorista"),
                    "disponible": bool(v.get("disponible")),
                }
    return None


def get_categorias(solo_disponibles=False):
    """Lista de categorías de productos activos, del sistema principal.
    solo_disponibles=True omite las que no tienen ningún producto con stock."""
    params = {"solo_disponibles": "true"} if solo_disponibles else None
    return _request("GET", "categorias-mayorista", params=params) or []


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
