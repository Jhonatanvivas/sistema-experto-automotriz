# synonyms.py
# Diccionario de sinónimos técnicos automotrices.
# Cada clave es el término canónico que se guarda en la BD.
# Los valores son variantes que los técnicos usan en el taller.

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
    "rotula"     : "rótula", "terminal": ["brazo", "terminales"],

    # Eléctrico / electrónico
    "ecu"        : ["computadora", "modulo de control", "pcm", "ecm", "centralita"],
    "can"        : ["canbus", "can-bus", "red de comunicación"],
    "obd"        : ["obd2", "obd-ii", "escaner", "escáner", "puerto diagnóstico"],

    # Híbrido / eléctrico
    "bateria alta tension": ["batería de tracción", "paquete de baterías", "hv battery", "high voltage battery"],
    "inversor"   : ["inverter", "convertidor", "unidad de potencia"],
    "bms"        : ["sistema de gestión de batería", "battery management system"],
    "motor electrico": ["motor eléctrico", "electric motor", "traction motor"],
    "cargador"   : ["cargador onboard", "obc", "on-board charger"],

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

def expandir_con_sinonimos(texto: str) -> list[str]:
    """
    Recibe un texto de búsqueda y devuelve una lista con todas las
    variantes de palabras que deben buscarse en la BD.
    """
    palabras_originales = texto.lower().strip().split()
    todas = set(palabras_originales)

    for palabra in palabras_originales:
        for canonico, variantes in SINONIMOS_AUTOMOTRIZ.items():
            # Si la palabra es el canónico, añade sus variantes
            if palabra == canonico:
                if isinstance(variantes, list):
                    todas.update(variantes)
                else:
                    todas.add(variantes)
            # Si la palabra es una variante, añade el canónico y las demás variantes
            variantes_lista = variantes if isinstance(variantes, list) else [variantes]
            if palabra in variantes_lista:
                todas.add(canonico)
                todas.update(variantes_lista)

    return list(todas)