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

# Texto genérico que versiones anteriores guardaban como "protocolo de
# seguridad" en las reglas aprendidas. Ya no se muestra al técnico.
PROTOCOLO_GENERICO = "Verificar sistema antes de intervenir"


def etiqueta_tecnologia(tec: str) -> str:
    """Texto que se muestra en el selector (agrega 'próximamente' si aplica)."""
    return tec if TECNOLOGIAS.get(tec, False) else f"{tec}{SUFIJO_PROXIMAMENTE}"