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
