# services/carrito.py
"""Carrito de compras en sesión. Se materializa como pedido recién al enviarlo."""
import math

from flask import session

from models import get_minimo_compra

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


def _fmt_monto(valor):
    # Sin decimales, separador de miles con punto — mismo estilo que el
    # resto de los montos del portal, pero redondeando siempre para arriba:
    # mostrar de menos haría que sumar "lo que falta" no alcance el mínimo.
    return f"{math.ceil(valor):,}".replace(",", ".")


# F4: el mínimo de compra se valida acá (no en las rutas) para que el
# carrito (mensaje siempre visible + botón deshabilitado) y el endpoint de
# enviar (validación de servidor, no salteable con el JS) usen exactamente
# el mismo cálculo y el mismo texto.
def estado_minimo():
    monto_minimo, unidades_minimo = get_minimo_compra()
    falta_monto = max(0.0, monto_minimo - total_carrito())
    falta_unidades = max(0, unidades_minimo - carrito_count())
    cumple = falta_monto <= 0 and falta_unidades <= 0

    if cumple:
        mensaje = "Llegaste al mínimo de compra: ya podés enviar tu pedido."
    elif falta_monto > 0 and falta_unidades > 0:
        unidad_txt = "unidad" if falta_unidades == 1 else "unidades"
        mensaje = (
            f"Te faltan ${_fmt_monto(falta_monto)} y {falta_unidades} {unidad_txt} "
            "para alcanzar el mínimo de compra."
        )
    elif falta_monto > 0:
        mensaje = f"Te faltan ${_fmt_monto(falta_monto)} para alcanzar el mínimo de compra."
    else:
        verbo = "falta" if falta_unidades == 1 else "faltan"
        unidad_txt = "unidad" if falta_unidades == 1 else "unidades"
        mensaje = f"Te {verbo} {falta_unidades} {unidad_txt} para alcanzar el mínimo de compra."

    return {"cumple": cumple, "mensaje": mensaje}
