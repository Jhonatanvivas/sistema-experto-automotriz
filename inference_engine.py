import sqlite3
from sinonimos import expandir_con_sinonimos

class MotorInferencia:
    def __init__(self, db_path='conocimiento.db'):
        self.db_path = db_path

    # ══════════════════════════════════════════════════════════
    # CONSULTA POR DTC
    # ══════════════════════════════════════════════════════════
    def consultar_por_dtc(self, dtc, tipo_vehiculo):
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute(
                '''SELECT causa_principal, solucion_principal,
                          causa_secundaria, solucion_secundaria,
                          protocolo_seguridad, sintoma
                   FROM reglas_diagnostico
                   WHERE dtc = ? AND tipo_vehiculo = ?''',
                (dtc.upper().strip(), tipo_vehiculo)
            )
            res = cur.fetchone()
        if res:
            return {
                "encontrado" : True,
                "causa_p"    : res[0],
                "solucion_p" : res[1],
                "causa_s"    : res[2],
                "solucion_s" : res[3],
                "seguridad"  : res[4],
                "sintoma"    : res[5],
            }
        return {"encontrado": False}

    # ══════════════════════════════════════════════════════════
    # BÚSQUEDA POR SÍNTOMA con sinónimos y % de confianza
    # ══════════════════════════════════════════════════════════
    def buscar_por_sintoma(self, busqueda, tipo_vehiculo):
        """
        Devuelve lista de dicts ordenados por confianza descendente.
        Cada dict tiene:
          dtc, sintoma, causa_principal, solucion_principal,
          causa_secundaria, solucion_secundaria, protocolo_seguridad,
          confianza (0-100), palabras_encontradas, total_palabras
        """
        palabras_expandidas = expandir_con_sinonimos(busqueda)
        palabras_originales = busqueda.lower().strip().split()

        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute(
                '''SELECT dtc, sintoma, causa_principal, solucion_principal,
                          causa_secundaria, solucion_secundaria,
                          protocolo_seguridad, id
                   FROM reglas_diagnostico
                   WHERE tipo_vehiculo = ?''',
                (tipo_vehiculo,)
            )
            todas = cur.fetchall()

        if not todas:
            return []

        resultados = []
        for fila in todas:
            texto_bd = f"{fila[1] or ''} {fila[2] or ''}".lower()
            encontradas = sum(1 for p in palabras_expandidas if p in texto_bd)
            if encontradas == 0:
                continue
            confianza = round(min(encontradas / max(len(palabras_originales), 1), 1.0) * 100)
            resultados.append({
                "dtc"          : fila[0],
                "sintoma"      : fila[1],
                "causa_p"      : fila[2],
                "solucion_p"   : fila[3],
                "causa_s"      : fila[4],
                "solucion_s"   : fila[5],
                "seguridad"    : fila[6],
                "id"           : fila[7],
                "confianza"    : confianza,
                "encontradas"  : encontradas,
                "total"        : len(palabras_originales),
            })

        # Ordena por confianza desc, luego por coincidencias desc
        resultados.sort(key=lambda x: (x["confianza"], x["encontradas"]), reverse=True)
        return resultados

    # ══════════════════════════════════════════════════════════
    # ESTADÍSTICAS
    # ══════════════════════════════════════════════════════════
    def registrar_estadistica(self, identificador, tipo_diag, tecnologia,
                               resultado, usuario="", duracion_seg=0):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                '''INSERT INTO estadisticas
                   (identificador, tipo_diagnostico, tecnologia, resultado, usuario, duracion_seg)
                   VALUES (?, ?, ?, ?, ?, ?)''',
                (identificador, tipo_diag, tecnologia, resultado, usuario, duracion_seg)
            )

    # ══════════════════════════════════════════════════════════
    # HISTORIAL DETALLADO
    # ══════════════════════════════════════════════════════════
    def registrar_historial(self, usuario, tipo_entrada, entrada, tecnologia,
                             causa, solucion, resultado):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                '''INSERT INTO historial_diagnosticos
                   (usuario, tipo_entrada, entrada, tecnologia,
                    causa_mostrada, solucion_mostrada, resultado)
                   VALUES (?, ?, ?, ?, ?, ?, ?)''',
                (usuario, tipo_entrada, entrada, tecnologia, causa, solucion, resultado)
            )

    # ══════════════════════════════════════════════════════════
    # CASOS PENDIENTES
    # ══════════════════════════════════════════════════════════
    def registrar_caso_pendiente(self, identificador, tecnologia,
                                  comentario, tipo_diag, usuario=""):
        self.registrar_estadistica(
            identificador, tipo_diag, tecnologia, "Fallo Reportado", usuario)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                '''INSERT INTO casos_pendientes
                   (dtc_o_sintoma, tecnologia, comentario_mecanico, tipo_diagnostico)
                   VALUES (?, ?, ?, ?)''',
                (identificador, tecnologia, comentario, tipo_diag)
            )

    def resolver_caso_pendiente(self, id_reporte, causa_real, solucion_real):
        """
        Marca el reporte como resuelto y activa el aprendizaje automático:
        genera una nueva regla en reglas_diagnostico con origen='aprendizaje'.
        """
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            # Obtener datos del reporte
            cur.execute("SELECT * FROM casos_pendientes WHERE id=?", (id_reporte,))
            reporte = cur.fetchone()
            if not reporte:
                return False

            # Marcar como resuelto
            conn.execute(
                "UPDATE casos_pendientes SET resuelto=1, causa_real=?, solucion_real=? WHERE id=?",
                (causa_real, solucion_real, id_reporte)
            )

            # Aprendizaje: insertar nueva regla automáticamente
            # reporte: id, dtc_o_sintoma, tecnologia, comentario, tipo_diag, resuelto, causa_real, solucion_real, fecha
            dtc_o_sint = reporte[1]
            tecnologia = reporte[2]
            tipo_diag  = reporte[4]

            if tipo_diag == "DTC":
                conn.execute(
                    '''INSERT INTO reglas_diagnostico
                       (dtc, tipo_vehiculo, sintoma, causa_principal, solucion_principal,
                        protocolo_seguridad, origen)
                       VALUES (?, ?, ?, ?, ?, ?, ?)''',
                    (dtc_o_sint, tecnologia,
                     f"Falla reportada: {reporte[3]}",
                     causa_real, solucion_real,
                     "Verificar sistema antes de intervenir", "aprendizaje")
                )
            else:
                conn.execute(
                    '''INSERT INTO reglas_diagnostico
                       (dtc, tipo_vehiculo, sintoma, causa_principal, solucion_principal,
                        protocolo_seguridad, origen)
                       VALUES (?, ?, ?, ?, ?, ?, ?)''',
                    ("N/A", tecnologia,
                     dtc_o_sint,
                     causa_real, solucion_real,
                     "Verificar sistema antes de intervenir", "aprendizaje")
                )
        return True

    def borrar_reporte_pendiente(self, id_reporte):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM casos_pendientes WHERE id=?", (id_reporte,))

    # ══════════════════════════════════════════════════════════
    # GESTIÓN DE REGLAS
    # ══════════════════════════════════════════════════════════
    def actualizar_regla(self, id_regla, dtc, tec, sin, cp, sp, cs, ss, prot):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                '''UPDATE reglas_diagnostico
                   SET dtc=?, tipo_vehiculo=?, sintoma=?,
                       causa_principal=?, solucion_principal=?,
                       causa_secundaria=?, solucion_secundaria=?,
                       protocolo_seguridad=?
                   WHERE id=?''',
                (dtc, tec, sin, cp, sp, cs, ss, prot, id_regla)
            )

    def registrar_exito_regla(self, id_regla):
        """Incrementa el contador de veces que una regla resolvió el problema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE reglas_diagnostico SET veces_exitosa = veces_exitosa + 1 WHERE id=?",
                (id_regla,)
            )