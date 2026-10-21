# ══════════════════════════════════════════════════════════════════════════════
# config.py — Configuración central del alcance del prototipo
#
# Alcance vigente (documento v2, julio 2026):
#   El prototipo diagnostica fallas en vehículos de COMBUSTIÓN INTERNA.
#   Híbridos y eléctricos se conservan en el selector como opciones
#   deshabilitadas ("próximamente") para que la ampliación futura no exija
#   rediseñar la base de datos ni el motor de inferencia: bastará con
#   cambiar el valor de TECNOLOGIAS["Híbrido"] / ["Eléctrico"] a True y
#   cargar las reglas de conocimiento correspondientes.
# ══════════════════════════════════════════════════════════════════════════════

# Tecnología habilitada por defecto en todo el sistema
TECNOLOGIA_ACTIVA = "Combustión"

# True  = habilitada (se puede diagnosticar y crear reglas)
# False = reservada para trabajo futuro (visible pero deshabilitada)
TECNOLOGIAS = {
    "Combustión": True,
    "Híbrido":    False,
    "Eléctrico":  False,
}

SUFIJO_PROXIMAMENTE = " (próximamente)"

# Indicadores de validación del Sprint 4 (documento v2)
META_TASA_ACIERTO = 70          # % — meta de tasa de acierto
TIEMPO_MAX_INFERENCIA_S = 2.0   # s — RNF3: la inferencia no debe superar 2 s

# ── Diagnóstico por síntomas: umbral de aceptación (informe de revisión, obs. 4.1 y 4.3) ──
# El porcentaje que muestra el sistema es la "coincidencia con la regla": qué parte
# de lo que describió el técnico aparece en la regla. NO es la probabilidad de que
# el diagnóstico sea correcto.
#
# VALORES PROVISIONALES. Deben calibrarse con la matriz formal de pruebas
#   (obs. 4.7) y justificarse en el documento; no se fijaron con datos reales.
UMBRAL_COINCIDENCIA = 50        # % mínimo para recomendar; por debajo se piden más datos
MIN_CONCEPTOS_ESPECIFICOS = 2   # términos NO genéricos que la regla debe cubrir (o todos, si hay menos)
PESO_SINONIMO = 0.6             # un término cubierto solo por sinónimo vale 60 % de uno literal
PESO_GENERICO = 0.3             # términos como "motor" pesan poco y no bastan por sí solos

# Texto genérico que versiones anteriores guardaban como "protocolo de
# seguridad" en las reglas aprendidas. Ya no se muestra al técnico.
PROTOCOLO_GENERICO = "Verificar sistema antes de intervenir"


def etiqueta_tecnologia(tec: str) -> str:
    """Texto que se muestra en el selector (agrega 'próximamente' si aplica)."""
    return tec if TECNOLOGIAS.get(tec, False) else f"{tec}{SUFIJO_PROXIMAMENTE}"