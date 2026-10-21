# sinonimos.py
# Análisis de la descripción de síntomas y puntuación contra las reglas.
#
# Cambios de la versión v3 (respuesta al informe de revisión funcional):
#   - Cada término que escribe el técnico se trata como un "concepto" y se
#     distingue de los términos DERIVADOS (sinónimos) que el sistema le agrega
#     (obs. 4.2: Sinónimos y trazabilidad).
#   - Normalización sin tildes ("pérdida" = "perdida") y coincidencia por palabra
#     completa, con plural simple (antes era por subcadena: "bloque" coincidía con
#     "bloqueo").
#   - Las frases consumen sus palabras: "check engine" ya no se expande también
#     como "engine" → "motor" (causa de coincidencias genéricas, obs. 4.1).
#   - Se depuraron equivalencias técnicamente no válidas.
#     PROPUESTA: pendiente de validación por el experto técnico.
#   - Puntuación ponderada: original = 1.0, sinónimo = PESO_SINONIMO, término
#     genérico (ej: "motor") pesa PESO_GENERICO y no basta por sí solo (obs. 4.1/4.3).

import re
import unicodedata
from functools import lru_cache

from config import (PESO_SINONIMO, PESO_GENERICO, UMBRAL_COINCIDENCIA,
                    MIN_CONCEPTOS_ESPECIFICOS)

# Cada clave es el término canónico; los valores son equivalentes REALES que usan
# los técnicos. No se incluyen componentes ni subtipos (ej: "bomba de agua" no
# es sinónimo de "bomba"): esos se buscan literalmente en la regla.
SINONIMOS_AUTOMOTRIZ = {
    # Batería / sistema eléctrico
    "bateria"    : ["acumulador", "pila", "battery", "batt"],
    "alternador" : ["dinamo", "generador"],
    "arranque"   : ["starter", "motor de arranque", "motor de marcha"],
    "fusible"    : ["plomo", "fuse"],

    # Motor
    "motor"      : ["engine", "propulsor"],
    "bujia"      : ["spark plug", "candela"],
    "inyector"   : ["tobera", "injector"],
    "culata"     : ["cabeza de motor", "head"],
    "correa"     : ["banda", "timing belt"],
    "turbo"      : ["turbocargador", "turbocompresor", "turbocharger"],
    "sensor"     : ["transductor", "detector"],
    "valvula"    : ["valve"],
    "bomba"      : ["pump"],
    "radiador"   : ["enfriador", "cooler"],

    # Transmisión
    "transmision": ["caja de cambios", "gearbox"],
    "embrague"   : ["clutch"],
    "diferencial": ["diff", "puente trasero"],
    "cardan"     : ["arbol de transmision", "propshaft"],

    # Frenos
    "frenos"     : ["freno", "brake", "sistema de frenado"],
    "pastilla"   : ["balata", "pad", "pastillas de freno"],
    "disco"      : ["rotor", "disco de freno"],
    "abs"        : ["sistema antibloqueo", "antilock"],

    # Suspensión / dirección
    "suspension" : [],
    "amortiguador": ["shock"],
    "resorte"    : ["muelle"],
    "direccion"  : ["steering"],
    "rotula"     : [],
    "terminal"   : ["terminales"],

    # Electrónico / comunicación
    "ecu"        : ["computadora", "modulo de control", "pcm", "ecm", "centralita"],
    "can"        : ["canbus", "can-bus", "red de comunicacion"],
    "obd"        : ["obd2", "obd-ii", "escaner", "puerto diagnostico"],

    # Síntomas generales
    "humo"       : ["fumando"],
    "ruido"      : ["ruidos", "sonido"],
    "fuga"       : ["goteo", "derrame", "leak"],
    "sobrecalentamiento": ["recalentamiento", "temperatura alta", "se calienta", "overheating"],
    "no arranca" : ["no enciende", "no prende", "no jala", "no parte"],
    "pierde potencia": ["baja potencia", "sin fuerza", "no acelera",
                        "perdida de potencia", "perdida potencia", "falta de potencia"],
    "check engine": ["testigo motor", "luz check", "luz naranja", "luz amarilla motor"],
    "consumo"    : ["gasta mucho", "alto consumo", "combustible excesivo"],
}

# Términos demasiado frecuentes en las reglas: coinciden con casi cualquiera y por
# sí solos no justifican una recomendación.
TERMINOS_GENERICOS = {
    "motor", "carro", "vehiculo", "auto", "automovil", "coche", "camioneta",
    "falla", "fallas", "problema", "problemas", "fallando",
}

# Palabras vacías (ya sin tildes).
STOPWORDS = {
    "de", "la", "el", "los", "las", "un", "una", "unos", "unas", "y", "o", "e",
    "en", "con", "por", "para", "al", "del", "se", "que", "mi", "su", "es",
    "a", "lo", "le", "me", "no", "tiene", "hay", "esta", "muy",
}

_PATRON_PALABRA = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def _sin_acentos(texto: str) -> str:
    """Minúsculas y sin tildes/diéresis (la ñ se vuelve n, igual en ambos lados)."""
    nfd = unicodedata.normalize("NFD", (texto or "").lower())
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


def _tokens(texto: str) -> list[str]:
    """Palabras normalizadas en orden, SIN quitar stopwords (se necesitan para
    reconocer frases como 'perdida de potencia')."""
    return _PATRON_PALABRA.findall(_sin_acentos(texto))


# ── Índice de grupos de sinónimos (se construye una vez al importar) ──────────
_GRUPOS: list[list[str]] = []          # cada grupo: [canónico, variante, ...] normalizados
_INDICE: dict[str, list[int]] = {}     # término normalizado -> índices de grupos
for _canon, _vars in SINONIMOS_AUTOMOTRIZ.items():
    _grupo = []
    for _t in [_canon] + list(_vars):
        _n = " ".join(_tokens(_t))
        if _n and _n not in _grupo:
            _grupo.append(_n)
    _GRUPOS.append(_grupo)
    for _n in _grupo:
        _INDICE.setdefault(_n, []).append(len(_GRUPOS) - 1)

_MAX_FRASE = max((len(t.split()) for t in _INDICE), default=1)


def _formas(token: str) -> list[str]:
    """El token y su singular simple, para buscarlo en el índice."""
    formas = [token]
    if token.endswith("es") and len(token) > 4:
        formas.append(token[:-2])
    if token.endswith("s") and len(token) > 3:
        formas.append(token[:-1])
    return formas


def _concepto(original: str) -> dict:
    """Arma el concepto: término del técnico + sinónimos derivados."""
    sinonimos: list[str] = []
    for forma in _formas(original):
        for idx in _INDICE.get(forma, []):
            for t in _GRUPOS[idx]:
                if t != original and t not in sinonimos:
                    sinonimos.append(t)
    return {
        "original": original,
        "sinonimos": sinonimos,
        "generico": original in TERMINOS_GENERICOS,
    }


def analizar_consulta(texto: str) -> list[dict]:
    """Descompone la descripción del técnico en conceptos.

    Primero reconoce las frases del diccionario (la más larga gana) y consume sus
    palabras; después toma las palabras sueltas que no son stopwords. Cada concepto
    es {"original", "sinonimos", "generico"}."""
    toks = _tokens(texto)
    usado = [False] * len(toks)
    conceptos: list[dict] = []
    vistos: set[str] = set()

    # 1) Frases del diccionario, de la más larga a la más corta
    for n in range(min(_MAX_FRASE, len(toks)), 1, -1):
        for i in range(len(toks) - n + 1):
            if any(usado[i:i + n]):
                continue
            frase = " ".join(toks[i:i + n])
            if frase in _INDICE and frase not in vistos:
                vistos.add(frase)
                for j in range(i, i + n):
                    usado[j] = True
                conceptos.append(_concepto(frase))

    # 2) Palabras sueltas
    for i, t in enumerate(toks):
        if usado[i] or t in STOPWORDS or t in vistos:
            continue
        vistos.add(t)
        conceptos.append(_concepto(t))

    return conceptos


@lru_cache(maxsize=2048)
def _patron(termino: str):
    # Palabra(s) completa(s), con plural simple (s / es) al final
    return re.compile(r"(?<![a-z0-9])" + re.escape(termino) + r"(?:es|s)?(?![a-z0-9])")


def _aparece(termino: str, texto_norm: str) -> bool:
    return bool(_patron(termino).search(texto_norm))


def puntuar_regla(conceptos: list[dict], texto_regla: str):
    """Compara los conceptos con el texto de una regla.

    Devuelve None si la regla no se relaciona (ningún concepto específico cubierto).
    Si no, un dict con:
      coincidencia      % ponderado (original=1, sinónimo=PESO_SINONIMO, genérico=PESO_GENERICO)
      originales        términos del técnico que aparecen en la regla
      derivados         [(sinónimo, original)] equivalencias que sí aplicaron
      sin_cobertura     términos del técnico que la regla no menciona
      especificos_*     cuántos conceptos no genéricos hay / se cubrieron
      suficiente        coincidencia >= UMBRAL y cobertura mínima de conceptos específicos
    """
    texto = _sin_acentos(texto_regla)
    suma = total = 0.0
    originales, derivados, sin_cobertura = [], [], []
    n_esp = cub_esp = 0

    for c in conceptos:
        peso = PESO_GENERICO if c["generico"] else 1.0
        total += peso
        if not c["generico"]:
            n_esp += 1
        if _aparece(c["original"], texto):
            credito = 1.0
            originales.append(c["original"])
        else:
            sin = next((s for s in c["sinonimos"] if _aparece(s, texto)), None)
            if sin:
                credito = PESO_SINONIMO
                derivados.append((sin, c["original"]))
            else:
                credito = 0.0
                sin_cobertura.append(c["original"])
        suma += peso * credito
        if credito > 0 and not c["generico"]:
            cub_esp += 1

    if suma == 0 or (n_esp > 0 and cub_esp == 0):
        return None   # sin relación real (solo coincidencias genéricas)

    coincidencia = round(suma / total * 100) if total else 0
    minimo = min(MIN_CONCEPTOS_ESPECIFICOS, n_esp)
    return {
        "coincidencia": coincidencia,
        "originales": originales,
        "derivados": derivados,
        "sin_cobertura": sin_cobertura,
        "especificos_total": n_esp,
        "especificos_cubiertos": cub_esp,
        "suficiente": n_esp > 0 and cub_esp >= minimo and coincidencia >= UMBRAL_COINCIDENCIA,
    }
