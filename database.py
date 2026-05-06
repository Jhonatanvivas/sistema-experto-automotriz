# ══════════════════════════════════════════════════════════════════════════════
# database.py — Capa de acceso a datos
#
# MIGRACIÓN SQLite → Supabase (PostgreSQL)
#
# Por qué migramos:
#   SQLite guarda el archivo .db en el servidor de Streamlit Cloud.
#   Ese servidor es efímero: se reinicia por inactividad, mantenimiento
#   o caídas, y al reiniciar borra todo el filesystem. Con Supabase los
#   datos viven en un servidor PostgreSQL externo que nunca se borra.
#
# Cómo funciona:
#   Leemos la URL de conexión desde st.secrets (archivo secrets.toml en
#   Streamlit Cloud). Nunca ponemos credenciales en el código fuente.
# ══════════════════════════════════════════════════════════════════════════════

import hashlib
import streamlit as st
import psycopg2
from psycopg2.extras import RealDictCursor  # devuelve filas como dict, no como tuplas


# ── Conexión ──────────────────────────────────────────────────────────────────

def get_conn():
    """Abre y devuelve una conexión a Supabase (PostgreSQL).

    La URL se lee de st.secrets["DATABASE_URL"], que en Streamlit Cloud
    se configura en el panel de la app → Settings → Secrets.
    Formato: postgresql://usuario:password@host:puerto/nombre_bd
    """
    return psycopg2.connect(
        st.secrets["DATABASE_URL"],
        cursor_factory=RealDictCursor   # filas como diccionarios
    )


def hash_pw(pw: str) -> str:
    """SHA-256 de la contraseña. Nunca guardamos texto plano en la BD."""
    return hashlib.sha256(pw.encode()).hexdigest()


# ── Inicialización de tablas ──────────────────────────────────────────────────

def inicializar_bd():
    """Crea las tablas si no existen y carga los usuarios por defecto.

    Se llama una sola vez al arrancar la app. Como usamos
    CREATE TABLE IF NOT EXISTS, es seguro llamarla en cada reinicio:
    no borra ni sobreescribe datos existentes.
    """
    conn = get_conn()
    cur  = conn.cursor()

    # ── USUARIOS ──────────────────────────────────────────────────────────────
    cur.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id       SERIAL PRIMARY KEY,
            usuario  TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            rol      TEXT NOT NULL
        )
    ''')

    # ── REGLAS DE DIAGNÓSTICO ─────────────────────────────────────────────────
    cur.execute('''
        CREATE TABLE IF NOT EXISTS reglas_diagnostico (
            id                   SERIAL PRIMARY KEY,
            dtc                  TEXT,
            tipo_vehiculo        TEXT NOT NULL,
            sintoma              TEXT,
            causa_principal      TEXT,
            solucion_principal   TEXT,
            causa_secundaria     TEXT,
            solucion_secundaria  TEXT,
            protocolo_seguridad  TEXT,
            origen               TEXT DEFAULT 'manual',
            veces_exitosa        INTEGER DEFAULT 0
        )
    ''')

    # ── CASOS PENDIENTES ──────────────────────────────────────────────────────
    cur.execute('''
        CREATE TABLE IF NOT EXISTS casos_pendientes (
            id                  SERIAL PRIMARY KEY,
            dtc_o_sintoma       TEXT,
            tecnologia          TEXT,
            comentario_mecanico TEXT,
            tipo_diagnostico    TEXT DEFAULT 'DTC',
            resuelto            INTEGER DEFAULT 0,
            causa_real          TEXT,
            solucion_real       TEXT,
            fecha               TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # ── ESTADÍSTICAS ──────────────────────────────────────────────────────────
    cur.execute('''
        CREATE TABLE IF NOT EXISTS estadisticas (
            id               SERIAL PRIMARY KEY,
            identificador    TEXT,
            tipo_diagnostico TEXT,
            tecnologia       TEXT,
            resultado        TEXT,
            usuario          TEXT,
            duracion_seg     INTEGER DEFAULT 0,
            fecha            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # ── HISTORIAL DE DIAGNÓSTICOS ─────────────────────────────────────────────
    cur.execute('''
        CREATE TABLE IF NOT EXISTS historial_diagnosticos (
            id                SERIAL PRIMARY KEY,
            usuario           TEXT,
            tipo_entrada      TEXT,
            entrada           TEXT,
            tecnologia        TEXT,
            causa_mostrada    TEXT,
            solucion_mostrada TEXT,
            resultado         TEXT,
            fecha             TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # ── USUARIOS POR DEFECTO ──────────────────────────────────────────────────
    # Solo los insertamos si la tabla está vacía, para no duplicar en cada reinicio
    cur.execute("SELECT COUNT(*) FROM usuarios")
    total = cur.fetchone()
    # RealDictCursor devuelve dict; accedemos por clave
    if (total['count'] if 'count' in total else list(total.values())[0]) == 0:
        cur.execute(
            "INSERT INTO usuarios (usuario, password, rol) VALUES (%s, %s, %s)",
            ('admin', hash_pw('admin123'), 'Administrador')
        )
        cur.execute(
            "INSERT INTO usuarios (usuario, password, rol) VALUES (%s, %s, %s)",
            ('taller1', hash_pw('taller123'), 'Mecanico')
        )

    conn.commit()
    cur.close()
    conn.close()
    print("✅ Base de datos Supabase inicializada correctamente.")


if __name__ == '__main__':
    inicializar_bd()