# ══════════════════════════════════════════════════════════════════════════════
# inference_engine.py — Motor de Inferencia (encadenamiento hacia adelante)
#
# Base de conocimiento: PostgreSQL (Supabase). Alcance v2: combustión interna.
#
# Cambios de la versión v2 respecto a la versión anterior:
#   - validar_dtc(): validación de formato del código (Sprint 3).
#   - consultar_por_dtc(): devuelve además id, origen y veces_exitosa para el
#     módulo de explicación, y prioriza las reglas generadas por el módulo de
#     aprendizaje (antes, una regla aprendida para un DTC ya existente quedaba
#     oculta detrás de la regla original).
#   - buscar_por_sintoma(): devuelve las palabras que coincidieron (explicación),
#     ignora palabras vacías y signos de puntuación.
#   - Las reglas aprendidas ya no guardan un "protocolo de seguridad" genérico.
# ══════════════════════════════════════════════════════════════════════════════

import re

from database import get_conn
from sinonimos import expandir_con_sinonimos, tokenizar

# Formato OBD-II: letra de sistema (P, B, C, U) + 4 caracteres hexadecimales,
# donde el segundo es 0-3. Ejemplos válidos: P0300, P0171, U0100.
_PATRON_DTC = re.compile(r"^[PBCU][0-3][0-9A-F]{3}$")


def validar_dtc(codigo: str) -> bool:
    """True si el texto tiene formato de código DTC OBD-II (ej. P0300)."""
    return bool(_PATRON_DTC.match((codigo or "").upper().strip()))


class MotorInferencia:

    # ══════════════════════════════════════════════════════════════════════════
    # CONSULTA POR DTC
    # ══════════════════════════════════════════════════════════════════════════
    def consultar_por_dtc(self, dtc, tipo_vehiculo):
        """Busca la regla para un código DTC y tipo de vehículo.

        Si existen varias reglas para el mismo par (dtc, tipo), gana la más
        reciente generada por el módulo de aprendizaje; si no hay ninguna,
        la regla más reciente en general. Devuelve un dict con
        encontrado=True/False y los campos de la regla."""
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                '''SELECT id, causa_principal, solucion_principal,
                          causa_secundaria, solucion_secundaria,
                          protocolo_seguridad, sintoma, origen, veces_exitosa
                   FROM reglas_diagnostico
                   WHERE dtc = %s AND tipo_vehiculo = %s
                   ORDER BY (COALESCE(origen, 'manual') = 'aprendizaje') DESC, id DESC
                   LIMIT 1''',
                (dtc.upper().strip(), tipo_vehiculo)
            )
            res = cur.fetchone()

        if res:
            return {
                "encontrado"    : True,
                "id"            : res['id'],
                "causa_p"       : res['causa_principal'],
                "solucion_p"    : res['solucion_principal'],
                "causa_s"       : res['causa_secundaria'],
                "solucion_s"    : res['solucion_secundaria'],
                "seguridad"     : res['protocolo_seguridad'],
                "sintoma"       : res['sintoma'],
                "origen"        : res['origen'] or 'manual',
                "veces_exitosa" : res['veces_exitosa'] or 0,
            }
        return {"encontrado": False}

    # ══════════════════════════════════════════════════════════════════════════
    # BÚSQUEDA POR SÍNTOMA
    # ══════════════════════════════════════════════════════════════════════════
    def buscar_por_sintoma(self, busqueda, tipo_vehiculo):
        """Búsqueda de texto libre con expansión de sinónimos y % de confianza.
        Devuelve lista de dicts ordenados por confianza descendente."""
        palabras_expandidas = expandir_con_sinonimos(busqueda)
        palabras_originales = tokenizar(busqueda)

        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                '''SELECT dtc, sintoma, causa_principal, solucion_principal,
                          causa_secundaria, solucion_secundaria,
                          protocolo_seguridad, id, origen, veces_exitosa
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
            coincidencias = sorted(p for p in palabras_expandidas if p in texto_bd)
            encontradas = len(coincidencias)
            if encontradas == 0:
                continue
            confianza = round(min(encontradas / max(len(palabras_originales), 1), 1.0) * 100)
            resultados.append({
                "dtc"           : fila['dtc'],
                "sintoma"       : fila['sintoma'],
                "causa_p"       : fila['causa_principal'],
                "solucion_p"    : fila['solucion_principal'],
                "causa_s"       : fila['causa_secundaria'],
                "solucion_s"    : fila['solucion_secundaria'],
                "seguridad"     : fila['protocolo_seguridad'],
                "id"            : fila['id'],
                "origen"        : fila['origen'] or 'manual',
                "veces_exitosa" : fila['veces_exitosa'] or 0,
                "confianza"     : confianza,
                "encontradas"   : encontradas,
                "coincidencias" : coincidencias,
                "total"         : len(palabras_originales),
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
        (módulo de aprendizaje asistido). Devuelve True si todo fue bien."""
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

            # Aprendizaje: insertar nueva regla (sin protocolo de seguridad genérico)
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
                     None, "aprendizaje")
                )
            else:
                cur.execute(
                    '''INSERT INTO reglas_diagnostico
                       (dtc, tipo_vehiculo, sintoma, causa_principal, solucion_principal,
                        protocolo_seguridad, origen)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)''',
                    ("N/A", tecnologia, dtc_o_sint,
                     causa_real, solucion_real,
                     None, "aprendizaje")
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
