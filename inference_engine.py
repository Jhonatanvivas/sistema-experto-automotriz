# ══════════════════════════════════════════════════════════════════════════════
# inference_engine.py — Motor de Inferencia
#
# Migrado de SQLite a Supabase (PostgreSQL).
# El único cambio respecto a la versión SQLite es:
#   - sqlite3.connect(...)  →  get_conn() de database.py
#   - Placeholders ?        →  %s  (estándar psycopg2)
#   - Las filas llegan como dict gracias a RealDictCursor
# ══════════════════════════════════════════════════════════════════════════════

from database import get_conn
from sinonimos import expandir_con_sinonimos


class MotorInferencia:

    # ══════════════════════════════════════════════════════════════════════════
    # CONSULTA POR DTC
    # ══════════════════════════════════════════════════════════════════════════
    def consultar_por_dtc(self, dtc, tipo_vehiculo):
        """Busca la regla exacta para un código DTC y tipo de vehículo.
        Devuelve un dict con encontrado=True/False y los campos de la regla."""
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                '''SELECT causa_principal, solucion_principal,
                          causa_secundaria, solucion_secundaria,
                          protocolo_seguridad, sintoma
                   FROM reglas_diagnostico
                   WHERE dtc = %s AND tipo_vehiculo = %s''',
                (dtc.upper().strip(), tipo_vehiculo)
            )
            res = cur.fetchone()

        if res:
            return {
                "encontrado" : True,
                "causa_p"    : res['causa_principal'],
                "solucion_p" : res['solucion_principal'],
                "causa_s"    : res['causa_secundaria'],
                "solucion_s" : res['solucion_secundaria'],
                "seguridad"  : res['protocolo_seguridad'],
                "sintoma"    : res['sintoma'],
            }
        return {"encontrado": False}

    # ══════════════════════════════════════════════════════════════════════════
    # BÚSQUEDA POR SÍNTOMA
    # ══════════════════════════════════════════════════════════════════════════
    def buscar_por_sintoma(self, busqueda, tipo_vehiculo):
        """Búsqueda de texto libre con expansión de sinónimos y % de confianza.
        Devuelve lista de dicts ordenados por confianza descendente."""
        palabras_expandidas = expandir_con_sinonimos(busqueda)
        palabras_originales = busqueda.lower().strip().split()

        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                '''SELECT dtc, sintoma, causa_principal, solucion_principal,
                          causa_secundaria, solucion_secundaria,
                          protocolo_seguridad, id
                   FROM reglas_diagnostico
                   WHERE tipo_vehiculo = %s''',
                (tipo_vehiculo,)
            )
            todas = cur.fetchall()

        if not todas:
            return []

        resultados = []
        for fila in todas:
            texto_bd = f"{fila['sintoma'] or ''} {fila['causa_principal'] or ''}".lower()
            encontradas = sum(1 for p in palabras_expandidas if p in texto_bd)
            if encontradas == 0:
                continue
            confianza = round(min(encontradas / max(len(palabras_originales), 1), 1.0) * 100)
            resultados.append({
                "dtc"        : fila['dtc'],
                "sintoma"    : fila['sintoma'],
                "causa_p"    : fila['causa_principal'],
                "solucion_p" : fila['solucion_principal'],
                "causa_s"    : fila['causa_secundaria'],
                "solucion_s" : fila['solucion_secundaria'],
                "seguridad"  : fila['protocolo_seguridad'],
                "id"         : fila['id'],
                "confianza"  : confianza,
                "encontradas": encontradas,
                "total"      : len(palabras_originales),
            })

        resultados.sort(key=lambda x: (x["confianza"], x["encontradas"]), reverse=True)
        return resultados

    # ══════════════════════════════════════════════════════════════════════════
    # ESTADÍSTICAS
    # ══════════════════════════════════════════════════════════════════════════
    def registrar_estadistica(self, identificador, tipo_diag, tecnologia,
                               resultado, usuario="", duracion_seg=0):
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                '''INSERT INTO estadisticas
                   (identificador, tipo_diagnostico, tecnologia, resultado, usuario, duracion_seg)
                   VALUES (%s, %s, %s, %s, %s, %s)''',
                (identificador, tipo_diag, tecnologia, resultado, usuario, duracion_seg)
            )
            conn.commit()

    # ══════════════════════════════════════════════════════════════════════════
    # HISTORIAL DETALLADO
    # ══════════════════════════════════════════════════════════════════════════
    def registrar_historial(self, usuario, tipo_entrada, entrada, tecnologia,
                             causa, solucion, resultado):
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                '''INSERT INTO historial_diagnosticos
                   (usuario, tipo_entrada, entrada, tecnologia,
                    causa_mostrada, solucion_mostrada, resultado)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)''',
                (usuario, tipo_entrada, entrada, tecnologia, causa, solucion, resultado)
            )
            conn.commit()

    # ══════════════════════════════════════════════════════════════════════════
    # CASOS PENDIENTES
    # ══════════════════════════════════════════════════════════════════════════
    def registrar_caso_pendiente(self, identificador, tecnologia,
                                  comentario, tipo_diag, usuario=""):
        self.registrar_estadistica(
            identificador, tipo_diag, tecnologia, "Fallo Reportado", usuario)
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                '''INSERT INTO casos_pendientes
                   (dtc_o_sintoma, tecnologia, comentario_mecanico, tipo_diagnostico)
                   VALUES (%s, %s, %s, %s)''',
                (identificador, tecnologia, comentario, tipo_diag)
            )
            conn.commit()

    def resolver_caso_pendiente(self, id_reporte, causa_real, solucion_real):
        """Marca el reporte como resuelto y genera una nueva regla automáticamente
        (módulo de aprendizaje). Devuelve True si todo fue bien."""
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM casos_pendientes WHERE id=%s", (id_reporte,))
            reporte = cur.fetchone()
            if not reporte:
                return False

            # Marcar como resuelto
            cur.execute(
                "UPDATE casos_pendientes SET resuelto=1, causa_real=%s, solucion_real=%s WHERE id=%s",
                (causa_real, solucion_real, id_reporte)
            )

            # Aprendizaje automático: insertar nueva regla
            dtc_o_sint = reporte['dtc_o_sintoma']
            tecnologia = reporte['tecnologia']
            tipo_diag  = reporte['tipo_diagnostico']

            if tipo_diag == "DTC":
                cur.execute(
                    '''INSERT INTO reglas_diagnostico
                       (dtc, tipo_vehiculo, sintoma, causa_principal, solucion_principal,
                        protocolo_seguridad, origen)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)''',
                    (dtc_o_sint, tecnologia,
                     f"Falla reportada: {reporte['comentario_mecanico']}",
                     causa_real, solucion_real,
                     "Verificar sistema antes de intervenir", "aprendizaje")
                )
            else:
                cur.execute(
                    '''INSERT INTO reglas_diagnostico
                       (dtc, tipo_vehiculo, sintoma, causa_principal, solucion_principal,
                        protocolo_seguridad, origen)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)''',
                    ("N/A", tecnologia, dtc_o_sint,
                     causa_real, solucion_real,
                     "Verificar sistema antes de intervenir", "aprendizaje")
                )
            conn.commit()
        return True

    def borrar_reporte_pendiente(self, id_reporte):
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM casos_pendientes WHERE id=%s", (id_reporte,))
            conn.commit()

    # ══════════════════════════════════════════════════════════════════════════
    # GESTIÓN DE REGLAS
    # ══════════════════════════════════════════════════════════════════════════
    def actualizar_regla(self, id_regla, dtc, tec, sin, cp, sp, cs, ss, prot):
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                '''UPDATE reglas_diagnostico
                   SET dtc=%s, tipo_vehiculo=%s, sintoma=%s,
                       causa_principal=%s, solucion_principal=%s,
                       causa_secundaria=%s, solucion_secundaria=%s,
                       protocolo_seguridad=%s
                   WHERE id=%s''',
                (dtc, tec, sin, cp, sp, cs, ss, prot, id_regla)
            )
            conn.commit()

    def registrar_exito_regla(self, id_regla):
        """Incrementa el contador de éxitos de una regla para el ranking."""
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE reglas_diagnostico SET veces_exitosa = veces_exitosa + 1 WHERE id=%s",
                (id_regla,)
            )
            conn.commit()