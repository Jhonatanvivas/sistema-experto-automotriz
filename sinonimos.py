# sinonimos.py
# Diccionario de sinónimos técnicos automotrices (vehículos de combustión interna).
# Cada clave es el término canónico que se guarda en la BD.
# Los valores son variantes que los técnicos usan en el taller.
#
# Nota de alcance (v2): se retiraron los términos exclusivos de vehículos
# híbridos y eléctricos (batería de alta tensión, inversor, BMS, motor
# eléctrico, cargador onboard). Quedan como trabajo futuro junto con la
# habilitación de esas tecnologías en config.py.

import re

SINONIMOS_AUTOMOTRIZ = {
    # Batería / sistema eléctrico
    "bateria"    : ["acumulador", "pila", "batería", "battery", "batt"],
    "alternador" : ["dinamo", "generador", "cargador"],
    "arranque"   : ["starter", "motor de arranque", "marcha", "motor de marcha"],
    "fusible"    : ["plomo", "fuse", "fusibles"],

    # Motor
    "motor"      : ["engine", "bloque", "propulsor"],
    "bujia"      : ["bujía", "chispa", "spark plug", "candela"],
    "inyector"   : ["tobera", "injector", "inyectores"],
    "culata"     : ["tapa de motor", "cabeza de motor", "head"],
    "correa"     : ["banda", "cadena de distribución", "timing belt", "distribución"],
    "turbo"      : ["turbocargador", "turbocompresor", "turbocharger"],
    "sensor"     : ["sonda", "transductor", "detector"],
    "valvula"    : ["válvula", "valve"],
    "bomba"      : ["pump", "bomba de agua", "bomba de aceite", "bomba de combustible"],
    "radiador"   : ["enfriador", "cooler", "sistema de enfriamiento"],

    # Transmisión
    "transmision": ["caja", "caja de cambios", "gearbox", "transmisión"],
    "embrague"   : ["clutch", "plato de presión", "disco de embrague"],
    "diferencial": ["diff", "puente trasero"],
    "cardán"     : ["cardan", "árbol de transmisión", "propshaft"],

    # Frenos
    "frenos"     : ["freno", "brake", "sistema de frenado"],
    "pastilla"   : ["balata", "pad", "pastillas de freno"],
    "disco"      : ["rotor", "disco de freno"],
    "abs"        : ["sistema antibloqueo", "antilock"],

    # Suspensión / dirección
    "suspension" : ["suspensión", "amortiguador", "shock", "muelle", "resorte"],
    "direccion"  : ["dirección", "steering", "volante", "caja de dirección"],
    "rotula"     : ["rótula"],
    "terminal"   : ["brazo", "terminales"],

    # Electrónico / comunicación
    "ecu"        : ["computadora", "modulo de control", "pcm", "ecm", "centralita"],
    "can"        : ["canbus", "can-bus", "red de comunicación"],
    "obd"        : ["obd2", "obd-ii", "escaner", "escáner", "puerto diagnóstico"],

    # Síntomas generales
    "humo"       : ["vapor", "escape humo", "fumando"],
    "ruido"      : ["sonido", "ruidos", "golpeteo", "tiquiteo", "chirrido", "zumbido", "vibración"],
    "fuga"       : ["goteo", "derrame", "escape", "leak"],
    "sobrecalentamiento": ["recalentamiento", "temperatura alta", "se calienta", "overheating"],
    "no arranca" : ["no enciende", "no prende", "no jala", "no da", "no parte", "motor no gira"],
    "pierde potencia": ["baja potencia", "sin fuerza", "no acelera", "lento", "jalonea"],
    "check engine": ["testigo motor", "luz check", "luz naranja", "luz amarilla motor"],
    "consumo"    : ["gasta mucho", "alto consumo", "combustible excesivo"],
}

# Palabras vacías: no aportan información técnica y, al buscarse como
# subcadena ("de" aparece en casi cualquier texto), inflaban la confianza.
# Nota: "no" se filtra como palabra suelta (es subcadena de decenas de palabras,
# p. ej. "diagnóstico"), pero las frases que lo contienen ("no arranca",
# "no enciende") sí se reconocen completas en expandir_con_sinonimos().
STOPWORDS = {
    "de", "la", "el", "los", "las", "un", "una", "unos", "unas", "y", "o", "e",
    "en", "con", "por", "para", "al", "del", "se", "que", "mi", "su", "es",
    "a", "lo", "le", "me", "no",
}

_PATRON_PALABRA = re.compile(r"[a-záéíóúüñ0-9]+(?:-[a-záéíóúüñ0-9]+)*")


def _normalizar(texto: str) -> list[str]:
    """Minúsculas y sin signos de puntuación (conserva guiones internos)."""
    return _PATRON_PALABRA.findall(texto.lower())


def tokenizar(texto: str) -> list[str]:
    """Palabras significativas del texto: sin puntuación, sin stopwords y
    sin repetidos (se conserva el orden de aparición)."""
    vistas, resultado = set(), []
    for p in _normalizar(texto):
        if p in STOPWORDS or p in vistas:
            continue
        vistas.add(p)
        resultado.append(p)
    return resultado


def expandir_con_sinonimos(texto: str) -> list[str]:
    """
    Recibe un texto de búsqueda y devuelve una lista con todas las
    variantes de palabras que deben buscarse en la BD.

    Reconoce tanto palabras sueltas ("batería") como frases completas
    ("no arranca", "pierde potencia"): las frases se buscan en el texto
    completo, porque una frase nunca coincide con una palabra individual.
    """
    tokens = tokenizar(texto)
    tokens_set = set(tokens)
    texto_completo = " " + " ".join(_normalizar(texto)) + " "
    todas = set(tokens)

    for canonico, variantes in SINONIMOS_AUTOMOTRIZ.items():
        grupo = [canonico] + (variantes if isinstance(variantes, list) else [variantes])
        for termino in grupo:
            if " " in termino:
                activo = f" {termino} " in texto_completo
            else:
                activo = termino in tokens_set
            if activo:
                todas.update(grupo)   # canónico + todas las variantes
                break

    return list(todas)
