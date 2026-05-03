import sqlite3

class MotorInferencia:
    def __init__(self, db_path='conocimiento.db'):
        self.db_path = db_path

    def consultar_por_dtc(self, dtc, tipo_vehiculo):
        conexion = sqlite3.connect(self.db_path)
        cursor = conexion.cursor()
        cursor.execute(
            'SELECT causa_principal, solucion_principal, causa_secundaria, '
            'solucion_secundaria, protocolo_seguridad, sintoma '
            'FROM reglas_diagnostico '
            'WHERE dtc = ? AND tipo_vehiculo = ?',
            (dtc.upper().strip(), tipo_vehiculo)
        )
        res = cursor.fetchone()
        conexion.close()
        if res:
            return {
                "encontrado"  : True,
                "causa_p"     : res[0],
                "solucion_p"  : res[1],
                "causa_s"     : res[2],
                "solucion_s"  : res[3],
                "seguridad"   : res[4],
                "sintoma"     : res[5]
            }
        return {"encontrado": False}

    def buscar_por_sintoma(self, busqueda, tipo_vehiculo):
        """
        Búsqueda inteligente por múltiples palabras clave.
        Devuelve tuplas con 7 columnas:
          0=dtc, 1=sintoma, 2=causa_principal, 3=solucion_principal,
          4=causa_secundaria, 5=solucion_secundaria, 6=protocolo_seguridad
        """
        conexion = sqlite3.connect(self.db_path)
        cursor = conexion.cursor()
        palabras = busqueda.strip().split()

        # FIX: añadimos causa_secundaria, solucion_secundaria y protocolo_seguridad
        query = (
            'SELECT dtc, sintoma, causa_principal, solucion_principal, '
            'causa_secundaria, solucion_secundaria, protocolo_seguridad '
            'FROM reglas_diagnostico '
            'WHERE tipo_vehiculo = ?'
        )
        parametros = [tipo_vehiculo]

        for palabra in palabras:
            query += ' AND (sintoma LIKE ? OR causa_principal LIKE ?)'
            parametros.extend([f"%{palabra}%", f"%{palabra}%"])

        cursor.execute(query, parametros)
        resultados = cursor.fetchall()
        conexion.close()
        return resultados

    def registrar_estadistica(self, identificador, tipo_diag, tecnologia, resultado):
        conexion = sqlite3.connect(self.db_path)
        cursor = conexion.cursor()
        cursor.execute(
            'INSERT INTO estadisticas '
            '(identificador, tipo_diagnostico, tecnologia, resultado) '
            'VALUES (?, ?, ?, ?)',
            (identificador, tipo_diag, tecnologia, resultado)
        )
        conexion.commit()
        conexion.close()

    def registrar_caso_pendiente(self, identificador, tecnologia, comentario, tipo_diag):
        self.registrar_estadistica(identificador, tipo_diag, tecnologia, "Fallo Reportado")
        conexion = sqlite3.connect(self.db_path)
        cursor = conexion.cursor()
        cursor.execute(
            'INSERT INTO casos_pendientes (dtc_o_sintoma, tecnologia, comentario_mecanico) '
            'VALUES (?, ?, ?)',
            (identificador, tecnologia, comentario)
        )
        conexion.commit()
        conexion.close()

    def borrar_reporte_pendiente(self, id_reporte):
        conexion = sqlite3.connect(self.db_path)
        cursor = conexion.cursor()
        cursor.execute('DELETE FROM casos_pendientes WHERE id = ?', (id_reporte,))
        conexion.commit()
        conexion.close()

    def actualizar_regla(self, id_regla, dtc, tec, sin, cp, sp, cs, ss, prot):
        conexion = sqlite3.connect(self.db_path)
        cursor = conexion.cursor()
        cursor.execute(
            '''UPDATE reglas_diagnostico
               SET dtc=?, tipo_vehiculo=?, sintoma=?, causa_principal=?,
                   solucion_principal=?, causa_secundaria=?, solucion_secundaria=?,
                   protocolo_seguridad=?
               WHERE id=?''',
            (dtc, tec, sin, cp, sp, cs, ss, prot, id_regla)
        )
        conexion.commit()
        conexion.close()