import sqlite3

class MotorInferencia:
    def __init__(self, db_path='conocimiento.db'):
        self.db_path = db_path

    def consultar_por_dtc(self, dtc, tipo_vehiculo):
        conexion = sqlite3.connect(self.db_path)
        cursor = conexion.cursor()
        cursor.execute('SELECT causa_principal, solucion_principal, causa_secundaria, solucion_secundaria, protocolo_seguridad, sintoma FROM reglas_diagnostico WHERE dtc = ? AND tipo_vehiculo = ?', (dtc.upper().strip(), tipo_vehiculo))
        res = cursor.fetchone()
        conexion.close()
        if res: return {"encontrado": True, "causa_p": res[0], "solucion_p": res[1], "causa_s": res[2], "solucion_s": res[3], "seguridad": res[4], "sintoma": res[5]}
        return {"encontrado": False}

    # --- MODIFICADO (Punto 4): Buscador inteligente por múltiples palabras clave ---
    def buscar_por_sintoma(self, busqueda, tipo_vehiculo):
        conexion = sqlite3.connect(self.db_path)
        cursor = conexion.cursor()
        palabras = busqueda.split() # Divide "bateria no carga" en ["bateria", "no", "carga"]
        
        # Construye una consulta dinámica que busque TODAS las palabras
        query = 'SELECT dtc, sintoma, causa_principal, solucion_principal FROM reglas_diagnostico WHERE tipo_vehiculo = ? '
        parametros = [tipo_vehiculo]
        
        for palabra in palabras:
            query += ' AND (sintoma LIKE ? OR causa_principal LIKE ?)'
            parametros.extend([f"%{palabra}%", f"%{palabra}%"])
            
        cursor.execute(query, parametros)
        resultados = cursor.fetchall()
        conexion.close()
        return resultados

    # --- MODIFICADO (Puntos 8 y 10): Estadísticas exactas ---
    def registrar_estadistica(self, identificador, tipo_diag, tecnologia, resultado):
        conexion = sqlite3.connect(self.db_path)
        cursor = conexion.cursor()
        cursor.execute('INSERT INTO estadisticas (identificador, tipo_diagnostico, tecnologia, resultado) VALUES (?, ?, ?, ?)', 
                       (identificador, tipo_diag, tecnologia, resultado))
        conexion.commit()
        conexion.close()

    def registrar_caso_pendiente(self, identificador, tecnologia, comentario, tipo_diag):
        self.registrar_estadistica(identificador, tipo_diag, tecnologia, "Fallo Reportado") # Guarda el fallo
        conexion = sqlite3.connect(self.db_path)
        cursor = conexion.cursor()
        cursor.execute('INSERT INTO casos_pendientes (dtc_o_sintoma, tecnologia, comentario_mecanico) VALUES (?, ?, ?)', (identificador, tecnologia, comentario))
        conexion.commit()
        conexion.close()

    def borrar_reporte_pendiente(self, id_reporte):
        conexion = sqlite3.connect(self.db_path)
        cursor = conexion.cursor()
        cursor.execute('DELETE FROM casos_pendientes WHERE id = ?', (id_reporte,))
        conexion.commit()
        conexion.close()
        
    # --- NUEVO (Punto 5 y 6): Función para actualizar registros editados ---
    def actualizar_regla(self, id_regla, dtc, tec, sin, cp, sp, cs, ss, prot):
        conexion = sqlite3.connect(self.db_path)
        cursor = conexion.cursor()
        cursor.execute('''UPDATE reglas_diagnostico 
            SET dtc=?, tipo_vehiculo=?, sintoma=?, causa_principal=?, solucion_principal=?, causa_secundaria=?, solucion_secundaria=?, protocolo_seguridad=?
            WHERE id=?''', (dtc, tec, sin, cp, sp, cs, ss, prot, id_regla))
        conexion.commit()
        conexion.close()