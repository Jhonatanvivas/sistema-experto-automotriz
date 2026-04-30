import sqlite3

def inicializar_bd():
    conexion = sqlite3.connect('conocimiento.db')
    cursor = conexion.cursor()

    cursor.execute('CREATE TABLE IF NOT EXISTS usuarios (id INTEGER PRIMARY KEY AUTOINCREMENT, usuario TEXT UNIQUE NOT NULL, password TEXT NOT NULL, rol TEXT NOT NULL)')

    cursor.execute('''CREATE TABLE IF NOT EXISTS reglas_diagnostico (
        id INTEGER PRIMARY KEY AUTOINCREMENT, dtc TEXT, tipo_vehiculo TEXT NOT NULL, sintoma TEXT,
        causa_principal TEXT, solucion_principal TEXT, causa_secundaria TEXT, solucion_secundaria TEXT, protocolo_seguridad TEXT)''')

    cursor.execute('CREATE TABLE IF NOT EXISTS casos_pendientes (id INTEGER PRIMARY KEY AUTOINCREMENT, dtc_o_sintoma TEXT, tecnologia TEXT, comentario_mecanico TEXT, fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')

    # --- MODIFICADO (Puntos 8 y 10): Tabla de Estadísticas Avanzada para Matriz ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS estadisticas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            identificador TEXT,
            tipo_diagnostico TEXT, -- "DTC" o "Sintoma"
            tecnologia TEXT,
            resultado TEXT, -- "Acierto 1er Intento", "Acierto 2do Intento", "Fallo"
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute("SELECT COUNT(*) FROM usuarios")
    if cursor.fetchone()[0] == 0:
        cursor.executemany('INSERT INTO usuarios (usuario, password, rol) VALUES (?, ?, ?)', [('admin', 'admin123', 'Administrador'), ('taller1', 'taller123', 'Mecanico')])

    conexion.commit()
    conexion.close()
    print("✅ Base de datos reconstruida con Matriz de Validación.")

if __name__ == '__main__':
    inicializar_bd()