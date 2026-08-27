# services/carrito.py
"""Carrito de compras en sesión. Se materializa como pedido recién al enviarlo."""
from flask import session

_KEY = "carrito"


def get_carrito():
    return session.get(_KEY, [])


def _guardar(items):
    session[_KEY] = items
    session.modified = True


def carrito_count():
    return sum(int(i["cantidad"]) for i in get_carrito())


def total_carrito():
    return sum(float(i["precio"]) * int(i["cantidad"]) for i in get_carrito())


def agregar(sku, nombre, precio, cantidad=1):
    cantidad = max(1, int(cantidad))
    items = get_carrito()
    for i in items:
        if i["sku"] == sku:
            i["cantidad"] = int(i["cantidad"]) + cantidad
            break
    else:
        items.append({
            "sku": sku,
            "nombre": nombre,
            "precio": float(precio),
            "cantidad": cantidad,
        })
    _guardar(items)


def actualizar_cantidad(sku, cantidad):
    cantidad = int(cantidad)
    items = get_carrito()
    if cantidad <= 0:
        items = [i for i in items if i["sku"] != sku]
    else:
        for i in items:
            if i["sku"] == sku:
                i["cantidad"] = cantidad
                break
    _guardar(items)


def quitar(sku):
    _guardar([i for i in get_carrito() if i["sku"] != sku])


def vaciar():
    session.pop(_KEY, None)
    session.modified = True
