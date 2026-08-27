# models.py — base de datos propia del portal (mayoristas.db)
"""
Esquema de la app portal-mayorista. NO tiene nada de negocio.db: acá solo viven
los usuarios mayoristas, sus pedidos y carritos. El stock y las ventas reales
son responsabilidad exclusiva de comenda-sistema (vía services/comenda_api_client).

Mismo patrón que comenda-sistema: sqlite3 plano, get_conn() con Row factory,
init_db() con CREATE IF NOT EXISTS + migraciones incrementales seguras.
"""
import sqlite3
from datetime import datetime

from config import Config

DB_PATH = Config.DB_PATH

# Estados válidos (se validan en la capa de servicio/rutas, no con CHECK en SQLite
# para poder agregar estados sin migración destructiva).
ESTADOS_CLIENTE = ("pendiente_aprobacion", "aprobado", "rechazado", "suspendido")
ESTADOS_PEDIDO = (
    "carrito", "enviado", "confirmando_stock", "confirmado_esperando_pago",
    "pagado", "rechazado_sin_stock", "cancelado",
)


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # ── Clientes mayoristas ─────────────────────────────────────────────────
    c.execute('''CREATE TABLE IF NOT EXISTS clientes_mayoristas (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre_empresa   TEXT NOT NULL,
        cuit             TEXT,
        telefono         TEXT,
        email            TEXT UNIQUE NOT NULL,
        password_hash    TEXT NOT NULL,
        estado           TEXT NOT NULL DEFAULT 'pendiente_aprobacion',
        fecha_registro   TEXT NOT NULL,
        fecha_aprobacion TEXT,
        aprobado_por     TEXT,
        motivo_rechazo   TEXT
    )''')

    # ── Pedidos mayoristas ──────────────────────────────────────────────────
    c.execute('''CREATE TABLE IF NOT EXISTS pedidos_mayoristas (
        id                   INTEGER PRIMARY KEY AUTOINCREMENT,
        cliente_mayorista_id INTEGER NOT NULL,
        numero               TEXT UNIQUE,
        estado               TEXT NOT NULL DEFAULT 'carrito',
        subtotal             REAL NOT NULL DEFAULT 0,
        fecha_creacion       TEXT NOT NULL,
        fecha_confirmacion   TEXT,
        metodo_pago_elegido  TEXT,
        venta_sistema_id     INTEGER,
        FOREIGN KEY (cliente_mayorista_id) REFERENCES clientes_mayoristas(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS pedido_mayorista_items (
        id                        INTEGER PRIMARY KEY AUTOINCREMENT,
        pedido_id                 INTEGER NOT NULL,
        sku                       TEXT NOT NULL,
        nombre_producto           TEXT NOT NULL,
        cantidad                  INTEGER NOT NULL DEFAULT 1,
        precio_unitario_mayorista REAL NOT NULL DEFAULT 0,
        disponible_confirmado     INTEGER,
        FOREIGN KEY (pedido_id) REFERENCES pedidos_mayoristas(id) ON DELETE CASCADE
    )''')

    # Migraciones incrementales (mismo patrón que comenda-sistema/models.py)
    _cols_items = [r[1] for r in c.execute("PRAGMA table_info(pedido_mayorista_items)").fetchall()]
    for col, defn in [
        # Mejora 1: si Comenda ajusta la cantidad ante falta de stock parcial.
        ("cantidad_ajustada",            "INTEGER"),
        # Última cantidad disponible informada al verificar stock (para el form de ajuste).
        ("stock_disponible_verificado",  "INTEGER"),
    ]:
        if col not in _cols_items:
            c.execute(f"ALTER TABLE pedido_mayorista_items ADD COLUMN {col} {defn}")

    # ── Historial / auditoría de pedidos ───────────────────────────────────
    c.execute('''CREATE TABLE IF NOT EXISTS pedido_mayorista_historial (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        pedido_id INTEGER NOT NULL,
        evento    TEXT NOT NULL,
        detalle   TEXT,
        usuario   TEXT,
        fecha     TEXT NOT NULL,
        FOREIGN KEY (pedido_id) REFERENCES pedidos_mayoristas(id) ON DELETE CASCADE
    )''')

    # ── Configuración del portal (datos bancarios, dirección de retiro, etc.) ─
    c.execute('''CREATE TABLE IF NOT EXISTS configuracion (
        clave TEXT PRIMARY KEY,
        valor TEXT
    )''')

    # ── Rate limiting del registro ──────────────────────────────────────────
    c.execute('''CREATE TABLE IF NOT EXISTS registro_intentos (
        id    INTEGER PRIMARY KEY AUTOINCREMENT,
        ip    TEXT NOT NULL,
        fecha TEXT NOT NULL
    )''')

    c.execute("CREATE INDEX IF NOT EXISTS idx_cli_may_estado ON clientes_mayoristas(estado)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_ped_may_cliente ON pedidos_mayoristas(cliente_mayorista_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_ped_may_estado ON pedidos_mayoristas(estado)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_ped_items_pedido ON pedido_mayorista_items(pedido_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_ped_hist_pedido ON pedido_mayorista_historial(pedido_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_registro_intentos_ip ON registro_intentos(ip, fecha)")

    # ── Seeds de configuración (FASE 6: datos de pago) ──────────────────────
    _SEEDS = {
        "pago_efectivo_direccion": "Paso 559, CABA",
        "pago_transferencia_banco": "",
        "pago_transferencia_cbu": "",
        "pago_transferencia_alias": "",
        "pago_transferencia_titular": "",
        "pago_transferencia_cuit": "",
        "contacto_comprobante": "",
    }
    for k, v in _SEEDS.items():
        c.execute("INSERT OR IGNORE INTO configuracion (clave, valor) VALUES (?, ?)", (k, v))

    conn.commit()
    conn.close()


# ── Helpers de configuración ────────────────────────────────────────────────

def get_config(clave, default=None):
    conn = get_conn()
    try:
        row = conn.execute("SELECT valor FROM configuracion WHERE clave = ?", (clave,)).fetchone()
    finally:
        conn.close()
    return row["valor"] if row and row["valor"] is not None else default


def get_configs(prefijo=None):
    conn = get_conn()
    try:
        if prefijo:
            rows = conn.execute(
                "SELECT clave, valor FROM configuracion WHERE clave LIKE ?", (prefijo + "%",)
            ).fetchall()
        else:
            rows = conn.execute("SELECT clave, valor FROM configuracion").fetchall()
    finally:
        conn.close()
    return {r["clave"]: r["valor"] for r in rows}


def set_config(clave, valor):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO configuracion (clave, valor) VALUES (?, ?) "
            "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
            (clave, valor)
        )
        conn.commit()
    finally:
        conn.close()


# ── Clientes mayoristas ─────────────────────────────────────────────────────

def get_cliente_por_email(email):
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM clientes_mayoristas WHERE LOWER(email) = LOWER(?)", (email,)
        ).fetchone()
    finally:
        conn.close()


def get_cliente(cliente_id):
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM clientes_mayoristas WHERE id = ?", (cliente_id,)
        ).fetchone()
    finally:
        conn.close()


def crear_cliente(nombre_empresa, cuit, telefono, email, password_hash):
    conn = get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO clientes_mayoristas
               (nombre_empresa, cuit, telefono, email, password_hash, estado, fecha_registro)
               VALUES (?, ?, ?, ?, ?, 'pendiente_aprobacion', ?)""",
            (nombre_empresa, cuit, telefono, email, password_hash,
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def listar_clientes_por_estado(estado):
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM clientes_mayoristas WHERE estado = ? ORDER BY fecha_registro DESC",
            (estado,)
        ).fetchall()
    finally:
        conn.close()


def actualizar_estado_cliente(cliente_id, nuevo_estado, aprobado_por=None, motivo_rechazo=None):
    conn = get_conn()
    try:
        fecha_aprob = datetime.now().strftime("%Y-%m-%d %H:%M:%S") if nuevo_estado == "aprobado" else None
        cur = conn.execute(
            """UPDATE clientes_mayoristas
               SET estado = ?,
                   fecha_aprobacion = COALESCE(?, fecha_aprobacion),
                   aprobado_por = COALESCE(?, aprobado_por),
                   motivo_rechazo = ?
               WHERE id = ?""",
            (nuevo_estado, fecha_aprob, aprobado_por, motivo_rechazo, cliente_id)
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ── Numeración de pedidos ───────────────────────────────────────────────────

def siguiente_numero_pedido(conn=None):
    """PEDMAY-<año>-<secuencia 5 dígitos>, secuencia reiniciada por año."""
    propia = conn is None
    if propia:
        conn = get_conn()
    try:
        anio = datetime.now().year
        prefijo = f"PEDMAY-{anio}-"
        row = conn.execute(
            "SELECT numero FROM pedidos_mayoristas WHERE numero LIKE ? ORDER BY numero DESC LIMIT 1",
            (prefijo + "%",)
        ).fetchone()
        ultimo = int(row["numero"].rsplit("-", 1)[1]) if row else 0
        return f"{prefijo}{ultimo + 1:05d}"
    finally:
        if propia:
            conn.close()


# ── Pedidos ─────────────────────────────────────────────────────────────────

def crear_pedido_enviado(cliente_id, items):
    """Crea un pedido (estado='enviado') con sus ítems, en una sola transacción.

    items: [{'sku', 'nombre', 'precio', 'cantidad'}]
    Devuelve (pedido_id, numero, subtotal).
    """
    conn = get_conn()
    conn.isolation_level = None
    try:
        conn.execute("BEGIN IMMEDIATE")
        numero = siguiente_numero_pedido(conn)
        subtotal = sum(float(i["precio"]) * int(i["cantidad"]) for i in items)
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cur = conn.execute(
            """INSERT INTO pedidos_mayoristas
               (cliente_mayorista_id, numero, estado, subtotal, fecha_creacion)
               VALUES (?, ?, 'enviado', ?, ?)""",
            (cliente_id, numero, subtotal, fecha)
        )
        pedido_id = cur.lastrowid

        for i in items:
            conn.execute(
                """INSERT INTO pedido_mayorista_items
                   (pedido_id, sku, nombre_producto, cantidad, precio_unitario_mayorista)
                   VALUES (?, ?, ?, ?, ?)""",
                (pedido_id, i["sku"], i["nombre"], int(i["cantidad"]), float(i["precio"]))
            )

        conn.execute("COMMIT")
        return pedido_id, numero, subtotal
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        conn.close()


def listar_pedidos_cliente(cliente_id):
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM pedidos_mayoristas WHERE cliente_mayorista_id = ? "
            "ORDER BY id DESC",
            (cliente_id,)
        ).fetchall()
    finally:
        conn.close()


def get_pedido(pedido_id, cliente_id=None):
    """Trae el pedido. Si se pasa cliente_id, exige que sea del dueño (o None)."""
    conn = get_conn()
    try:
        if cliente_id is not None:
            return conn.execute(
                "SELECT * FROM pedidos_mayoristas WHERE id = ? AND cliente_mayorista_id = ?",
                (pedido_id, cliente_id)
            ).fetchone()
        return conn.execute(
            "SELECT * FROM pedidos_mayoristas WHERE id = ?", (pedido_id,)
        ).fetchone()
    finally:
        conn.close()


def get_pedido_items(pedido_id):
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM pedido_mayorista_items WHERE pedido_id = ? ORDER BY id",
            (pedido_id,)
        ).fetchall()
    finally:
        conn.close()


# ── Gestión de pedidos (consumida por la API interna, desde comenda-sistema) ──

# Estados que el sistema principal todavía tiene que atender.
ESTADOS_PENDIENTES = ("enviado", "confirmando_stock", "confirmado_esperando_pago")

# Cantidad efectiva de un ítem = la ajustada si existe, si no la original.
_CANT_EFECTIVA = "COALESCE(cantidad_ajustada, cantidad)"


def _log_historial(conn, pedido_id, evento, detalle=None, usuario=None):
    conn.execute(
        "INSERT INTO pedido_mayorista_historial (pedido_id, evento, detalle, usuario, fecha) "
        "VALUES (?, ?, ?, ?, ?)",
        (pedido_id, evento, detalle, usuario or None,
         datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )


def _recalcular_subtotal(conn, pedido_id):
    total = conn.execute(
        f"SELECT COALESCE(SUM({_CANT_EFECTIVA} * precio_unitario_mayorista), 0) "
        "FROM pedido_mayorista_items WHERE pedido_id = ?",
        (pedido_id,)
    ).fetchone()[0]
    conn.execute(
        "UPDATE pedidos_mayoristas SET subtotal = ? WHERE id = ?", (total, pedido_id)
    )
    return total


def get_pedido_historial(pedido_id):
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM pedido_mayorista_historial WHERE pedido_id = ? ORDER BY id",
            (pedido_id,)
        ).fetchall()
    finally:
        conn.close()


def listar_pedidos_pendientes():
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT p.*, c.nombre_empresa, c.cuit, c.telefono, c.email "
            "FROM pedidos_mayoristas p "
            "JOIN clientes_mayoristas c ON c.id = p.cliente_mayorista_id "
            "WHERE p.estado IN ({}) "
            "ORDER BY p.id".format(",".join("?" * len(ESTADOS_PENDIENTES))),
            ESTADOS_PENDIENTES
        ).fetchall()
    finally:
        conn.close()


def get_pedido_con_cliente(pedido_id):
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT p.*, c.nombre_empresa, c.cuit, c.telefono, c.email "
            "FROM pedidos_mayoristas p "
            "JOIN clientes_mayoristas c ON c.id = p.cliente_mayorista_id "
            "WHERE p.id = ?",
            (pedido_id,)
        ).fetchone()
    finally:
        conn.close()


def registrar_verificacion_stock(pedido_id, detalle, usuario=None):
    """detalle: [{'sku', 'disponible', 'stock_actual'}]. Marca disponible_confirmado
    y stock_disponible_verificado por ítem y pasa el pedido a 'confirmando_stock'.
    Solo aplica en 'enviado' / 'confirmando_stock'."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT estado FROM pedidos_mayoristas WHERE id = ?", (pedido_id,)
        ).fetchone()
        if row is None:
            return False, "Pedido no encontrado"
        if row["estado"] not in ("enviado", "confirmando_stock"):
            return False, f"El pedido está en estado '{row['estado']}'"
        faltantes = []
        for d in (detalle or []):
            sku = d.get("sku")
            val = 1 if d.get("disponible") else 0
            conn.execute(
                "UPDATE pedido_mayorista_items "
                "SET disponible_confirmado = ?, stock_disponible_verificado = ? "
                "WHERE pedido_id = ? AND sku = ?",
                (val, d.get("stock_actual"), pedido_id, sku)
            )
            if not val:
                faltantes.append(sku)
        conn.execute(
            "UPDATE pedidos_mayoristas SET estado = 'confirmando_stock' WHERE id = ?",
            (pedido_id,)
        )
        msg = "Stock OK" if not faltantes else f"Sin stock: {', '.join(faltantes)}"
        _log_historial(conn, pedido_id, "verificacion_stock", msg, usuario)
        conn.commit()
        return True, None
    finally:
        conn.close()


def ajustar_item_pedido(pedido_id, item_id, nueva_cantidad, ajustado_por=None):
    """Reduce la cantidad solicitada de un ítem (falta de stock parcial),
    recalcula el subtotal del pedido y lo deja como disponible. Auditable."""
    try:
        nueva_cantidad = int(nueva_cantidad)
    except (TypeError, ValueError):
        return False, "Cantidad inválida", None
    if nueva_cantidad < 1:
        return False, "La cantidad debe ser al menos 1", None

    conn = get_conn()
    try:
        ped = conn.execute(
            "SELECT estado FROM pedidos_mayoristas WHERE id = ?", (pedido_id,)
        ).fetchone()
        if ped is None:
            return False, "Pedido no encontrado", None
        if ped["estado"] not in ("enviado", "confirmando_stock"):
            return False, f"No se puede ajustar un pedido en estado '{ped['estado']}'", None

        it = conn.execute(
            "SELECT * FROM pedido_mayorista_items WHERE id = ? AND pedido_id = ?",
            (item_id, pedido_id)
        ).fetchone()
        if it is None:
            return False, "Ítem no encontrado", None

        cant_original = it["cantidad"]
        if nueva_cantidad > cant_original:
            return False, "Solo se puede reducir la cantidad, no aumentarla", None

        disp_ver = it["stock_disponible_verificado"]
        if disp_ver is not None and nueva_cantidad > disp_ver:
            return False, f"Solo hay {disp_ver} disponibles de {it['sku']}", None

        conn.execute(
            "UPDATE pedido_mayorista_items "
            "SET cantidad_ajustada = ?, disponible_confirmado = 1 WHERE id = ?",
            (nueva_cantidad, item_id)
        )
        nuevo_subtotal = _recalcular_subtotal(conn, pedido_id)
        _log_historial(
            conn, pedido_id, "ajuste_cantidad",
            f"{it['sku']}: {cant_original} → {nueva_cantidad}", ajustado_por
        )
        conn.commit()
        return True, None, {"subtotal": nuevo_subtotal}
    finally:
        conn.close()


def marcar_pedido_confirmado(pedido_id, usuario=None):
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT estado FROM pedidos_mayoristas WHERE id = ?", (pedido_id,)
        ).fetchone()
        if row is None:
            return False, "Pedido no encontrado"
        if row["estado"] not in ("enviado", "confirmando_stock"):
            return False, f"El pedido está en estado '{row['estado']}'"
        conn.execute(
            "UPDATE pedidos_mayoristas SET estado = 'confirmado_esperando_pago', "
            "fecha_confirmacion = ? WHERE id = ?",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), pedido_id)
        )
        _log_historial(conn, pedido_id, "confirmado", "Pedido confirmado, esperando pago", usuario)
        conn.commit()
        return True, None
    finally:
        conn.close()


def marcar_pedido_rechazado_sin_stock(pedido_id, usuario=None):
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT estado FROM pedidos_mayoristas WHERE id = ?", (pedido_id,)
        ).fetchone()
        if row is None:
            return False, "Pedido no encontrado"
        if row["estado"] in ("pagado", "cancelado"):
            return False, f"El pedido está en estado '{row['estado']}'"
        conn.execute(
            "UPDATE pedidos_mayoristas SET estado = 'rechazado_sin_stock' WHERE id = ?",
            (pedido_id,)
        )
        _log_historial(conn, pedido_id, "rechazado_sin_stock", "Rechazado por falta de stock", usuario)
        conn.commit()
        return True, None
    finally:
        conn.close()


def marcar_pedido_pagado(pedido_id, venta_sistema_id, usuario=None):
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT estado FROM pedidos_mayoristas WHERE id = ?", (pedido_id,)
        ).fetchone()
        if row is None:
            return False, "Pedido no encontrado"
        if row["estado"] == "pagado":
            return True, None  # idempotente
        if row["estado"] != "confirmado_esperando_pago":
            return False, f"El pedido está en estado '{row['estado']}'"
        conn.execute(
            "UPDATE pedidos_mayoristas SET estado = 'pagado', venta_sistema_id = ? WHERE id = ?",
            (venta_sistema_id, pedido_id)
        )
        _log_historial(conn, pedido_id, "pagado", f"Venta #{venta_sistema_id} generada", usuario)
        conn.commit()
        return True, None
    finally:
        conn.close()


def elegir_metodo_pago(pedido_id, cliente_id, metodo):
    """El cliente elige (o cambia) efectivo/transferencia. El estado sigue en
    'confirmado_esperando_pago' hasta que Comenda confirme el pago."""
    if metodo not in ("efectivo", "transferencia"):
        return False, "Método inválido"
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT estado, metodo_pago_elegido FROM pedidos_mayoristas "
            "WHERE id = ? AND cliente_mayorista_id = ?",
            (pedido_id, cliente_id)
        ).fetchone()
        if row is None:
            return False, "Pedido no encontrado"
        if row["estado"] != "confirmado_esperando_pago":
            return False, "El pedido ya no admite cambios en el método de pago"
        anterior = row["metodo_pago_elegido"]
        conn.execute(
            "UPDATE pedidos_mayoristas SET metodo_pago_elegido = ? WHERE id = ?",
            (metodo, pedido_id)
        )
        if anterior and anterior != metodo:
            _log_historial(conn, pedido_id, "cambio_metodo_pago",
                           f"{anterior} → {metodo}", "cliente")
        elif not anterior:
            _log_historial(conn, pedido_id, "metodo_pago_elegido", metodo, "cliente")
        conn.commit()
        return True, None
    finally:
        conn.close()
