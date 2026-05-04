import sqlite3
import hashlib

def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

def inicializar_bd():
    conexion = sqlite3.connect('conocimiento.db')
    cursor = conexion.cursor()

    # ── USUARIOS ──────────────────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario  TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            rol      TEXT NOT NULL
        )
    ''')

    # ── REGLAS DE DIAGNÓSTICO ─────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reglas_diagnostico (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            dtc                  TEXT,
            tipo_vehiculo        TEXT NOT NULL,
            sintoma              TEXT,
            causa_principal      TEXT,
            solucion_principal   TEXT,
            causa_secundaria     TEXT,
            solucion_secundaria  TEXT,
            protocolo_seguridad  TEXT,
            origen               TEXT DEFAULT 'manual',  -- 'manual' o 'aprendizaje'
            veces_exitosa        INTEGER DEFAULT 0        -- cuántas veces resolvió el problema
        )
    ''')

    # ── CASOS PENDIENTES ──────────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS casos_pendientes (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            dtc_o_sintoma       TEXT,
            tecnologia          TEXT,
            comentario_mecanico TEXT,
            tipo_diagnostico    TEXT DEFAULT 'DTC',
            resuelto            INTEGER DEFAULT 0,         -- 0=pendiente, 1=resuelto
            causa_real          TEXT,                      -- lo que el admin descubre
            solucion_real       TEXT,
            fecha               TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # ── ESTADÍSTICAS ──────────────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS estadisticas (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            identificador    TEXT,
            tipo_diagnostico TEXT,   -- "DTC" o "Sintoma"
            tecnologia       TEXT,
            resultado        TEXT,   -- "Acierto 1er Intento", "Acierto 2do Intento", "Fallo Reportado"
            usuario          TEXT,   -- quién hizo el diagnóstico
            duracion_seg     INTEGER DEFAULT 0,  -- tiempo en segundos desde inicio hasta cierre
            fecha            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # ── HISTORIAL DE DIAGNÓSTICOS ─────────────────────────────
    # Detalle completo por sesión para el dashboard de validación
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS historial_diagnosticos (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario          TEXT,
            tipo_entrada     TEXT,   -- "DTC" o "Sintoma"
            entrada          TEXT,   -- el código o síntoma ingresado
            tecnologia       TEXT,
            causa_mostrada   TEXT,
            solucion_mostrada TEXT,
            resultado        TEXT,   -- "Acierto 1er Intento", "Acierto 2do Intento", "Fallo"
            fecha            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # ── USUARIOS POR DEFECTO ──────────────────────────────────
    cursor.execute("SELECT COUNT(*) FROM usuarios")
    if cursor.fetchone()[0] == 0:
        cursor.executemany(
            'INSERT INTO usuarios (usuario, password, rol) VALUES (?, ?, ?)',
            [
                ('admin',   hash_pw('admin123'),  'Administrador'),
                ('taller1', hash_pw('taller123'), 'Mecanico'),
            ]
        )

    conexion.commit()
    conexion.close()
    print("✅ Base de datos inicializada correctamente.")

if __name__ == '__main__':
    inicializar_bd()