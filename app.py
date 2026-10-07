# ══════════════════════════════════════════════════════════════════════════════
# EXPERT-AUTO POPAYÁN — Sistema Experto de Diagnóstico Automotriz
# Desarrollado con Python + Streamlit + Supabase
#
# ALCANCE VIGENTE (documento v2): diagnóstico de fallas en vehículos de
# COMBUSTIÓN INTERNA. Híbridos y eléctricos quedan visibles pero deshabilitados
# ("próximamente") como trabajo futuro; ver config.py.
#
# Este archivo es el punto de entrada principal de la aplicación.
# Aquí vive toda la interfaz de usuario: login, diagnóstico, administración
# y el dashboard de validación del Sprint 4.
#
# La lógica del motor de inferencia está separada en inference_engine.py
# para mantener el código limpio y modular.
# ══════════════════════════════════════════════════════════════════════════════

# — Librerías estándar de Python —
import streamlit as st      # el framework que convierte este script en una app web
import hashlib              # para cifrar contraseñas con SHA-256
import time                 # medir duración de los diagnósticos en segundos
import io                   # manejo de flujos de bytes (para el PDF en memoria)
import pandas as pd         # manipulación de tablas y datos del dashboard
import plotly.express as px         # gráficas interactivas rápidas
import plotly.graph_objects as go   # gráficas con más control manual
from datetime import datetime, timedelta  # fechas y cálculo de rangos temporales
from fpdf import FPDF                     # generación del reporte PDF descargable
from inference_engine import MotorInferencia, validar_dtc  # motor de reglas + validación de DTC
from config import (TECNOLOGIAS, TECNOLOGIA_ACTIVA, etiqueta_tecnologia,
                    META_TASA_ACIERTO, TIEMPO_MAX_INFERENCIA_S, PROTOCOLO_GENERICO)  # alcance v2
from database import get_conn, inicializar_bd  # conexión y tablas en Supabase

# Inicializamos la BD una sola vez al arrancar.
# Con Supabase esto es seguro: usa CREATE TABLE IF NOT EXISTS,
# así que si las tablas ya existen no hace nada.
# st.cache_resource evita repetirlo en CADA interacción del usuario (Streamlit
# re-ejecuta todo el script en cada clic), lo que ahorraba latencia innecesaria.
@st.cache_resource(show_spinner=False)
def _preparar_bd():
    inicializar_bd()
    return True

_preparar_bd()


# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURACIÓN GLOBAL DE LA PÁGINA
# Esto es lo primero que Streamlit necesita ejecutar antes de cualquier otra cosa
# ══════════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Expert-Auto Popayán",  # título en la pestaña del navegador
    page_icon="⚙️",
    layout="wide",                     # usamos todo el ancho de pantalla
    initial_sidebar_state="expanded"   # la barra lateral arranca visible
)

# — Estilos visuales personalizados —
# Inyectamos CSS directamente en el HTML que genera Streamlit.
# Esto nos da control sobre colores, bordes y tipografía que Streamlit
# no expone por defecto. El tema oscuro es intencional: los talleres
# suelen trabajar con poca luz y el alto contraste ayuda a leer en pantalla.
st.markdown("""
<style>
    /* Tarjetas de métricas numéricas del dashboard */
    [data-testid="metric-container"] {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border: 1px solid #0f3460;
        border-radius: 12px;
        padding: 16px;
    }
    [data-testid="metric-container"] label { color: #a0a0b0 !important; font-size: 13px !important; }
    [data-testid="metric-container"] [data-testid="stMetricValue"] {
        color: #4CAF50 !important; font-size: 2rem !important; font-weight: 800 !important;
    }
    /* Pestañas más legibles */
    .stTabs [data-baseweb="tab"] { font-weight: 600; font-size: 14px; }
    /* Barra de confianza del diagnóstico por síntoma */
    .conf-bar { height: 10px; border-radius: 5px; margin-top: 4px; }
    /* Etiquetas que distinguen reglas manuales de las aprendidas automáticamente */
    .badge-aprendizaje {
        background: #0f3460; color: #4CAF50; padding: 2px 8px;
        border-radius: 20px; font-size: 11px; font-weight: 700;
    }
    .badge-manual {
        background: #1a1a2e; color: #888; padding: 2px 8px;
        border-radius: 20px; font-size: 11px;
    }
    /* RNF1 (usabilidad en taller): botones grandes y fáciles de pulsar */
    .stButton button, .stDownloadButton button,
    [data-testid="stFormSubmitButton"] button {
        min-height: 3rem; font-size: 1.05rem; font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# ESTADO DE SESIÓN
# Streamlit re-ejecuta todo el script cada vez que el usuario interactúa.
# session_state es el único lugar donde podemos guardar información entre
# esas re-ejecuciones sin perderla. Lo inicializamos una sola vez al arrancar.
# ══════════════════════════════════════════════════════════════════════════════
if 'logueado' not in st.session_state:
    st.session_state.update({
        'logueado'       : False,   # ¿hay alguien autenticado?
        'rol'            : None,    # "Administrador" o "Mecanico"
        'user'           : None,    # nombre de usuario activo

        # — Flujo de diagnóstico por DTC —
        # paso_diag controla en qué etapa del árbol de decisión estamos:
        # 0 = sin iniciar, 1 = mostrando causa 1, 2 = causa 2, 3 = reporte
        'paso_diag'      : 0,
        'dtc_actual'     : '',      # el código que el técnico ingresó
        'dtc_inicio'     : 0,       # timestamp Unix del momento en que empezó el diagnóstico

        # — Flujo de diagnóstico por síntomas —
        # igual que DTC pero con su propio estado independiente
        'paso_sint'      : 0,       # -1 = sin resultados, 1 = causa 1, 2 = causa 2, 3 = reporte
        'sint_actual'    : '',      # texto del síntoma ingresado
        'sint_res'       : None,    # el dict con la regla más probable que devolvió el motor
        'sint_inicio'    : 0,
        'sint_t_inf'     : 0.0,     # segundos que tardó la inferencia (RNF3)

        # — PDF generado —
        # Guardamos los bytes del PDF aquí para que sobrevivan al st.rerun().
        # Sin esto, el PDF se regenera después del reset y explota si los datos ya no están.
        'pdf_bytes'      : None,
        'pdf_filename'   : '',
        'diag_mensaje'   : '',      # mensaje de éxito que se muestra junto al botón de descarga
    })

# Instanciamos el motor de inferencia una sola vez.
# Este objeto abre conexiones a la BD y ejecuta las consultas de búsqueda.
motor = MotorInferencia()


# ══════════════════════════════════════════════════════════════════════════════
# FUNCIONES DE UTILIDAD
# Pequeñas piezas reutilizables que usamos en varios puntos de la app
# ══════════════════════════════════════════════════════════════════════════════

def hash_pw(pw):
    """Convierte una contraseña en texto plano a su hash SHA-256.
    Nunca guardamos contraseñas en claro en la BD."""
    return hashlib.sha256(pw.encode()).hexdigest()

def login(u, p):
    """Verifica credenciales contra la base de datos.
    Primero busca con contraseña hasheada; si no coincide, intenta
    texto plano (compatibilidad con registros legacy del sistema anterior)."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT rol FROM usuarios WHERE usuario=%s AND password=%s", (u, hash_pw(p)))
        res = cur.fetchone()
        if not res:  # fallback para usuarios creados antes del hash
            cur.execute("SELECT rol FROM usuarios WHERE usuario=%s AND password=%s", (u, p))
            res = cur.fetchone()
    return res['rol'] if res else None  # devuelve el rol o None si falla

def cargar_reglas():
    """Trae todas las reglas de diagnóstico de la BD como un DataFrame.
    Las ordena por veces_exitosa para que las reglas más efectivas
    aparezcan primero en la tabla del admin."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute('''SELECT id, dtc, tipo_vehiculo, sintoma,
                      causa_principal, solucion_principal,
                      causa_secundaria, solucion_secundaria,
                      protocolo_seguridad, origen, veces_exitosa
               FROM reglas_diagnostico
               ORDER BY veces_exitosa DESC, id DESC''')
        rows = cur.fetchall()
    if rows:
        df = pd.DataFrame([dict(r) for r in rows])
    else:
        df = pd.DataFrame(columns=['id','dtc','tipo_vehiculo','sintoma',
            'causa_principal','solucion_principal','causa_secundaria',
            'solucion_secundaria','protocolo_seguridad','origen','veces_exitosa'])
    return df

def reset_sint():
    """Limpia todo el estado del flujo de síntomas para empezar desde cero.
    Se llama cuando el técnico quiere hacer un diagnóstico nuevo."""
    st.session_state.update({'paso_sint':0,'sint_actual':'','sint_res':None,'sint_inicio':0,'sint_t_inf':0.0})

def reset_diag():
    """Igual que reset_sint pero para el flujo de DTC."""
    st.session_state.update({'paso_diag':0,'dtc_actual':'','dtc_inicio':0})

def _hay_precaucion(texto) -> bool:
    """True si la regla trae una precaución útil para mostrar.
    Ignora vacíos y el texto genérico que guardaba el módulo de aprendizaje
    en versiones anteriores."""
    t = ("" if texto is None else str(texto)).strip()
    return bool(t) and t.lower() not in (
        PROTOCOLO_GENERICO.lower(), "none", "nan", "sigue los protocolos estándar")

def duracion_desde(ts):
    """Calcula cuántos segundos pasaron desde que empezó el diagnóstico.
    Esto alimenta la estadística de 'tiempo promedio de diagnóstico'."""
    return int(time.time() - ts) if ts else 0


# ══════════════════════════════════════════════════════════════════════════════
# GENERADOR DE REPORTES PDF
# ══════════════════════════════════════════════════════════════════════════════

def _pdf_texto(val) -> str:
    """Sanitiza cualquier valor antes de mandarlo a FPDF.

    FPDF usa la codificación latin-1 internamente. Si le pasamos None,
    texto vacío, o caracteres unicode fuera de ese rango (tildes, ñ, comillas
    tipográficas), lanza FPDFException. Esta función previene eso.
    """
    # Primero nos aseguramos de que no llegue nada vacío o nulo
    if val is None or str(val).strip() in ("", "None", "nan"):
        return "No especificado"
    texto = str(val)

    # Reemplazamos caracteres especiales por sus equivalentes ASCII seguros.
    # Helvetica (la fuente que usamos) no renderiza unicode fuera de latin-1.
    replacements = {
        "\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"',
        "\u2013": "-", "\u2014": "-", "\u2026": "...",
        # vocales con tilde → sin tilde (el PDF es técnico, no literario)
        "\u00e1": "a", "\u00e9": "e", "\u00ed": "i",
        "\u00f3": "o", "\u00fa": "u", "\u00f1": "n",
        "\u00c1": "A", "\u00c9": "E", "\u00cd": "I",
        "\u00d3": "O", "\u00da": "U", "\u00d1": "N",
        "\u00fc": "u", "\u00e4": "a", "\u00f6": "o",
    }
    for orig, rep in replacements.items():
        texto = texto.replace(orig, rep)

    # Último recurso: forzar encoding latin-1, descartando lo que no entre
    try:
        texto.encode('latin-1')
    except (UnicodeEncodeError, Exception):
        texto = texto.encode('latin-1', errors='replace').decode('latin-1')

    return texto.strip() or "No especificado"


def generar_pdf_diagnostico(datos: dict) -> bytes:
    """Construye el reporte PDF del diagnóstico y lo devuelve como bytes.

    Recibe un diccionario con los datos del caso (técnico, fecha, causa,
    solución, etc.) y genera un PDF estructurado en dos secciones:
    información general y resultado del diagnóstico.

    Devuelve bytes para que Streamlit pueda ofrecerlo como descarga directa
    sin necesidad de escribir archivos en disco.
    """
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)  # salta página automáticamente si se llena

    # Calculamos el ancho útil de la página una sola vez.
    # En A4 son 210mm; con márgenes de ~10mm a cada lado quedan ~190mm.
    # Usamos esta variable en vez de hardcodear "190" para que funcione
    # aunque cambiemos los márgenes en el futuro.
    ANCHO = pdf.w - pdf.l_margin - pdf.r_margin   # ≈ 190mm
    LABEL_W = 52   # ancho fijo de la columna de etiquetas (ej: "Tecnico:", "Fecha:")

    # — Encabezado con fondo oscuro —
    pdf.set_fill_color(30, 30, 50)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(ANCHO, 13, "EXPERT-AUTO POPAYAN", ln=True, align="C", fill=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(ANCHO, 8, "Reporte de Diagnostico Automotriz", ln=True, align="C", fill=True)
    pdf.ln(4)  # espacio vertical

    # — Sección: Información General —
    pdf.set_text_color(0, 0, 0)
    pdf.set_fill_color(240, 240, 250)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(ANCHO, 9, "INFORMACION GENERAL", ln=True, fill=True)

    # Lista de campos que vamos a imprimir en formato "Etiqueta: Valor"
    campos = [
        ("Tecnico",          datos.get("usuario",    "---")),
        ("Fecha / Hora",     datos.get("fecha",      "---")),
        ("Tipo de vehiculo", datos.get("tecnologia", "---")),
        ("Metodo",           datos.get("metodo",     "---")),
        ("Entrada",          datos.get("entrada",    "---")),
        ("Duracion",         datos.get("duracion",   "---")),
    ]
    for label, val in campos:
        # Imprimimos la etiqueta en negrita con ancho fijo
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(LABEL_W, 7, f"{label}:", border=0)
        # multi_cell con ancho EXPLÍCITO (ANCHO - LABEL_W) evita el error
        # "Not enough horizontal space". El ancho 0 en FPDF significa
        # "desde X actual hasta el borde", lo cual falla si X > 0.
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(ANCHO - LABEL_W, 7, _pdf_texto(val))

    pdf.ln(3)

    # — Sección: Resultado del Diagnóstico —
    pdf.set_fill_color(240, 240, 250)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(ANCHO, 9, "RESULTADO DEL DIAGNOSTICO", ln=True, fill=True)

    secciones = [
        ("Causa identificada",  datos.get("causa",     "---")),
        ("Solucion aplicada",   datos.get("solucion",  "---")),
    ]
    # La precaución ya no es obligatoria (v2): solo se imprime si la regla la tiene
    if _hay_precaucion(datos.get("seguridad")):
        secciones.append(("Precauciones", datos.get("seguridad")))
    secciones.append(("Conclusion", datos.get("resultado", "---")))
    for label, val in secciones:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(ANCHO, 7, f"{label}:", ln=True)
        pdf.set_font("Helvetica", "", 9)          # fuente 9pt = más texto cabe horizontalmente
        pdf.set_fill_color(250, 250, 255)
        pdf.multi_cell(ANCHO, 6, _pdf_texto(val), border=1, fill=True)
        pdf.ln(2)

    # — Pie de página —
    pdf.ln(4)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 6,
        "Documento generado automaticamente por Expert-Auto Popayan | "
        "Universidad Nacional Abierta y a Distancia",
        ln=True, align="C")

    # pdf.output() devuelve bytearray; lo convertimos a bytes para st.download_button
    return bytes(pdf.output())


# ══════════════════════════════════════════════════════════════════════════════
# COMPONENTE VISUAL: BARRA DE CONFIANZA
# Se usa en el modo de diagnóstico por síntomas para mostrarle al técnico
# cuán seguro está el sistema de su recomendación
# ══════════════════════════════════════════════════════════════════════════════
def mostrar_confianza(pct: int):
    """Renderiza una barra de progreso coloreada con el porcentaje de confianza.
    Verde >= 70%, Amarillo >= 40%, Rojo < 40%.
    El porcentaje lo calcula el motor de inferencia según cuántas palabras
    del síntoma ingresado coincidieron con las reglas de la BD."""
    color = "#4CAF50" if pct >= 70 else "#FFC107" if pct >= 40 else "#F44336"
    label = "Alta" if pct >= 70 else "Media" if pct >= 40 else "Baja"
    st.markdown(f"""
    <div style='margin-bottom:12px;'>
        <span style='font-size:13px;color:#aaa;'>Confianza del diagnóstico: </span>
        <b style='color:{color};font-size:15px;'>{pct}% — {label}</b>
        <div style='background:#333;border-radius:5px;height:8px;margin-top:4px;'>
            <div style='width:{pct}%;background:{color};height:8px;border-radius:5px;'></div>
        </div>
    </div>
    """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# COMPONENTES: PRECAUCIÓN OPCIONAL Y MÓDULO DE EXPLICACIÓN
# ══════════════════════════════════════════════════════════════════════════════
def mostrar_precaucion(texto):
    """Muestra una precaución solo si la regla tiene una definida.
    (En la v1 se mostraba siempre un protocolo de alta tensión; con el alcance
    reducido a combustión interna ya no es obligatorio.)"""
    if _hay_precaucion(texto):
        st.warning(f"⚠️ **Precaución:** {texto}")


def mostrar_explicacion(metodo: str, entrada: str, tipo_v: str, res: dict, t_inf: float):
    """Módulo de explicación (documento v2): le dice al técnico POR QUÉ el sistema
    llegó a esa conclusión: qué hechos recibió, qué regla se activó, de dónde
    viene esa regla y cuánto tardó la inferencia (RNF3: máx. 2 s)."""
    if res.get("origen") == "aprendizaje":
        origen = "aprendida por el sistema a partir de un caso resuelto por el experto"
    else:
        origen = "cargada manualmente en la base de conocimiento"
    confirmada = int(res.get("veces_exitosa") or 0)
    ruta_s = "sí" if res.get("causa_s") else "no (solo ruta principal)"
    estado_t = "✅ dentro del límite" if t_inf <= TIEMPO_MAX_INFERENCIA_S else "⚠️ supera el límite"

    with st.expander("🧠 ¿Por qué este diagnóstico?"):
        if metodo == "DTC":
            st.markdown(
                f"**1. Hechos de entrada:** código `{entrada}` · tecnología *{tipo_v}*\n\n"
                f"**2. Regla activada (ID {res.get('id')}):** SI el DTC es `{entrada}` "
                f"Y la tecnología es *{tipo_v}* ENTONCES la causa más probable es: "
                f"*{res.get('causa_p')}*\n\n"
                f"**3. Síntoma asociado en la base de conocimiento:** "
                f"{res.get('sintoma') or 'No especificado'}"
            )
        else:
            palabras = ", ".join(f"`{c}`" for c in res.get("coincidencias", [])) or "—"
            st.markdown(
                f"**1. Hechos de entrada:** \"{entrada}\" · tecnología *{tipo_v}*\n\n"
                f"**2. Términos reconocidos (incluye sinónimos técnicos) que coinciden con la regla:** "
                f"{palabras}\n\n"
                f"**3. Regla activada (ID {res.get('id')}):** síntoma registrado: "
                f"*{res.get('sintoma') or 'No especificado'}* "
                f"(DTC asociado: {res.get('dtc') or 'N/A'}). "
                f"Confianza: {res.get('confianza')}%."
            )
        st.markdown(
            f"**Origen de la regla:** {origen}.  \n"
            f"**Veces confirmada como exitosa:** {confirmada}.  \n"
            f"**Ruta secundaria disponible:** {ruta_s}.  \n"
            f"**Tiempo de inferencia:** {t_inf:.2f} s — {estado_t} "
            f"(máx. {TIEMPO_MAX_INFERENCIA_S:.0f} s)."
        )


# ══════════════════════════════════════════════════════════════════════════════
# PANTALLA DE LOGIN
# Si nadie está autenticado, mostramos solo el formulario de acceso.
# El bloque principal de la app vive en el 'else' de esta condición.
# ══════════════════════════════════════════════════════════════════════════════
if not st.session_state.logueado:
    st.title("🛡️ Acceso al Sistema Experto Automotriz")
    col_img, col_form = st.columns([1, 1])

    with col_img:
        # Imagen decorativa del login. Si no existe el archivo, mostramos un aviso.
        try:
            st.image("autosLogin.jpg", use_container_width=True)
        except:
            st.info("📷 Coloca 'autosLogin.jpg' en la raíz del proyecto")

    with col_form:
        st.markdown("### Ingresa tus credenciales")
        # st.form agrupa los inputs y solo dispara el submit cuando el usuario
        # presiona el botón, evitando reruns innecesarios mientras escribe.
        with st.form("login_form", clear_on_submit=True):
            u = st.text_input("👤 Usuario")
            p = st.text_input("🔒 Contraseña", type="password")
            if st.form_submit_button("Ingresar →", use_container_width=True):
                rol = login(u, p)
                if rol:
                    # Guardamos identidad y rol en session_state y recargamos la app
                    st.session_state.update({'logueado': True, 'rol': rol, 'user': u})
                    st.rerun()
                else:
                    st.error("Credenciales incorrectas")


# ══════════════════════════════════════════════════════════════════════════════
# INTERFAZ PRINCIPAL (usuario autenticado)
# ══════════════════════════════════════════════════════════════════════════════
else:

    # ── BARRA LATERAL ─────────────────────────────────────────────────────────
    # Siempre visible después del login. Muestra quién está conectado,
    # su actividad personal y el botón de cerrar sesión.
    with st.sidebar:
        # Logo del taller — opcional, si no existe mostramos texto
        try:
            st.image("logo_taller.png", use_container_width=True)
        except:
            st.markdown("## ⚙️ EXPERT-AUTO")
        st.divider()

        # Tarjeta de identidad del usuario activo
        st.markdown(f"""
        <div style='background:linear-gradient(135deg,#1a1a2e,#0f3460);
                    padding:18px;border-radius:12px;text-align:center;
                    border:1px solid #4CAF50;'>
            <div style='font-size:36px;'>🧑‍🔧</div>
            <div style='color:#4CAF50;font-weight:800;font-size:16px;margin:6px 0 2px;'>
                {st.session_state.user}</div>
            <div style='color:#aaa;font-size:13px;'>{st.session_state.rol}</div>
            <div style='color:#666;font-size:11px;margin-top:4px;'>Sede Popayán</div>
        </div>
        """, unsafe_allow_html=True)

        st.write("")

        # Mini resumen de actividad personal: cuántos diagnósticos hizo este usuario
        # y cuántos resultaron exitosos. Solo aparece si ya tiene registros.
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT resultado FROM estadisticas WHERE usuario=%s",
                (st.session_state.user,))
            rows = cur.fetchall()
        mis_diag = pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame(columns=['resultado'])
        if not mis_diag.empty:
            total_yo = len(mis_diag)
            exito_yo = int(mis_diag['resultado'].str.contains('Acierto', na=False).sum())
            tasa_yo  = round(exito_yo / total_yo * 100) if total_yo else 0
            st.markdown(f"""
            <div style='background:#111;border-radius:8px;padding:12px;font-size:13px;'>
                <div style='color:#888;margin-bottom:6px;'>📊 Mi actividad</div>
                <div>🔢 Diagnósticos: <b style='color:#4CAF50;'>{total_yo}</b></div>
                <div>✅ Tasa de éxito: <b style='color:#4CAF50;'>{tasa_yo}%</b></div>
            </div>
            """, unsafe_allow_html=True)
            st.write("")

        # Cerrar sesión: borra todo session_state y vuelve al login
        if st.button("🚨 Cerrar Sesión", use_container_width=True, type="primary"):
            for k in list(st.session_state.keys()):
                st.session_state.pop(k, None)
            st.rerun()

    # ── PESTAÑAS DE NAVEGACIÓN ────────────────────────────────────────────────
    # El administrador ve todas las pestañas.
    # El mecánico solo ve Diagnóstico: no tiene acceso a la gestión del sistema.
    if st.session_state.rol == "Administrador":
        nombres_tabs = ["🔍 Diagnóstico", "📚 Base Conocimiento", "🛠️ Resolver Reportes",
                        "📈 Estadísticas", "🎓 Dashboard Validación", "👥 Usuarios"]
    else:
        nombres_tabs = ["🔍 Diagnóstico"]

    tabs = st.tabs(nombres_tabs)


    # ══════════════════════════════════════════════════════════════════════════
    # PESTAÑA 0 — DIAGNÓSTICO
    # El corazón del sistema. Aquí el técnico ingresa el código DTC o describe
    # los síntomas, y el motor de inferencia le guía por el árbol de decisión.
    # ══════════════════════════════════════════════════════════════════════════
    with tabs[0]:
        st.header("🔍 Motor de Inferencia")

        # — Banner de PDF disponible —
        # Cuando un diagnóstico se cierra con éxito, generamos el PDF y lo guardamos
        # en session_state. En el siguiente render (después del rerun) lo mostramos aquí.
        # No podemos mostrarlo en el mismo render donde se generó porque reset_diag()
        # ya borró los datos del código DTC/síntoma antes del rerun.
        if st.session_state.get('pdf_bytes') and st.session_state.get('diag_mensaje'):
            st.success(st.session_state.diag_mensaje)
            st.download_button(
                "📄 Descargar Reporte PDF",
                data=st.session_state.pdf_bytes,
                file_name=st.session_state.pdf_filename,
                mime="application/pdf",
                key="pdf_download_banner"
            )
            # El técnico cierra el banner cuando está listo para el siguiente caso
            if st.button("✖ Cerrar y nuevo diagnóstico", key="cerrar_pdf"):
                st.session_state.pdf_bytes    = None
                st.session_state.pdf_filename = ''
                st.session_state.diag_mensaje = ''
                st.rerun()
            st.divider()

        # El técnico elige cómo quiere buscar:
        # - DTC: tiene el código del escáner OBD (ej. P0300)
        # - Síntomas: describe la falla con palabras propias
        metodo = st.radio("Método de entrada:", ["DTC (Escáner)", "Síntomas (Texto)"], horizontal=True)
        # Alcance v2: solo Combustión está habilitada. Híbrido y Eléctrico se muestran
        # marcados como "próximamente" y, si se eligen, el diagnóstico queda bloqueado.
        opciones_tec = {etiqueta_tecnologia(t): t for t in TECNOLOGIAS}
        sel_tec = st.selectbox(
            "Motorización", list(opciones_tec.keys()),
            help="Alcance actual: vehículos de combustión interna. "
                 "Híbridos y eléctricos se habilitarán en fases posteriores.")
        tipo_v = opciones_tec[sel_tec]
        tec_habilitada = TECNOLOGIAS[tipo_v]


        # ── MODO DTC ──────────────────────────────────────────────────────────
        if not tec_habilitada:
            st.info("🚧 **Próximamente.** El diagnóstico de vehículos híbridos y eléctricos "
                    "está planificado como trabajo futuro. Por ahora selecciona **Combustión**.")
        elif metodo == "DTC (Escáner)":
            codigo = st.text_input("Ingrese código DTC (ej: P0300)").upper().strip()
            c1, c2 = st.columns([1, 4])

            # Al presionar "Analizar", guardamos el código en session_state
            # y marcamos que estamos en el paso 1 del árbol de decisión
            if c1.button("🔎 Analizar DTC"):
                # Validación de entrada (Sprint 3): solo se consulta la base si el
                # texto tiene formato real de DTC (letra + 4 caracteres, ej. P0300).
                if not codigo:
                    st.warning("Ingresa un código DTC para analizar.")
                elif not validar_dtc(codigo):
                    st.error("❌ Formato de DTC inválido. Debe ser una letra (P, B, C o U), "
                             "un dígito de 0 a 3 y tres caracteres hexadecimales. Ejemplo: P0300.")
                else:
                    st.session_state.paso_diag  = 1
                    st.session_state.dtc_actual = codigo
                    st.session_state.dtc_inicio = time.time()  # empezamos a medir el tiempo
                    st.rerun()

            if c2.button("🗑️ Limpiar"):
                reset_diag(); st.rerun()

            # Si ya tenemos un código activo, consultamos el motor
            if st.session_state.paso_diag >= 1 and st.session_state.dtc_actual:
                _t0 = time.perf_counter()
                res = motor.consultar_por_dtc(st.session_state.dtc_actual, tipo_v)
                t_inf = time.perf_counter() - _t0   # RNF3: tiempo de inferencia

                if res["encontrado"]:
                    # Precaución opcional: solo se muestra si la regla tiene una definida.
                    # (En la v1 era obligatoria por la alta tensión de híbridos y
                    # eléctricos, que ahora quedan fuera del alcance.)
                    mostrar_precaucion(res['seguridad'])

                    # — PASO 1: Primera hipótesis (causa más probable) —
                    if st.session_state.paso_diag == 1:
                        st.info(f"**Causa 1:** {res['causa_p']}\n\n**Solución 1:** {res['solucion_p']}")
                        mostrar_explicacion("DTC", st.session_state.dtc_actual, tipo_v, res, t_inf)
                        col1, col2 = st.columns(2)

                        if col1.button("✅ Resolvió el problema"):
                            # El técnico confirma que la solución funcionó.
                            # Registramos el éxito en estadísticas e historial,
                            # generamos el PDF y preparamos el banner de descarga.
                            dur = duracion_desde(st.session_state.dtc_inicio)
                            motor.registrar_estadistica(
                                st.session_state.dtc_actual, "DTC", tipo_v,
                                "Acierto 1er Intento", st.session_state.user, dur)
                            # Igual que en síntomas: la regla confirmada sube en el ranking
                            if res.get("id"):
                                motor.registrar_exito_regla(res["id"])
                            motor.registrar_historial(
                                st.session_state.user, "DTC",
                                st.session_state.dtc_actual, tipo_v,
                                res['causa_p'], res['solucion_p'], "Acierto 1er Intento")
                            datos_pdf = {
                                "usuario": st.session_state.user,
                                "fecha": datetime.now().strftime("%d/%m/%Y %H:%M"),
                                "tecnologia": tipo_v, "metodo": "DTC",
                                "entrada": st.session_state.dtc_actual,
                                "duracion": f"{dur}s",
                                "causa": res['causa_p'], "solucion": res['solucion_p'],
                                "seguridad": res['seguridad'],
                                "resultado": "Resuelto en 1er intento"
                            }
                            # Guardamos el PDF en session_state ANTES del rerun
                            # para que el banner pueda mostrarlo en el siguiente render
                            st.session_state.pdf_bytes    = generar_pdf_diagnostico(datos_pdf)
                            st.session_state.pdf_filename = f"diagnostico_{st.session_state.dtc_actual}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
                            st.session_state.diag_mensaje = "✅ Diagnóstico exitoso registrado. Descarga el reporte abajo."
                            reset_diag()   # limpiamos el flujo activo
                            st.rerun()

                        if col2.button("❌ No funcionó"):
                            # La primera solución no resolvió el problema.
                            # Avanzamos al paso 2: causa secundaria.
                            st.session_state.paso_diag = 2; st.rerun()

                    # — PASO 2: Segunda hipótesis (causa alternativa) —
                    elif st.session_state.paso_diag == 2:
                        st.error("🔎 Ruta Secundaria de Inspección")
                        if res['causa_s']:
                            st.info(f"**Causa 2:** {res['causa_s']}\n\n**Solución 2:** {res['solucion_s']}")
                        else:
                            # No todas las reglas tienen causa secundaria definida
                            st.warning("No hay causa secundaria registrada.")
                        mostrar_explicacion("DTC", st.session_state.dtc_actual, tipo_v, res, t_inf)
                        col1, col2 = st.columns(2)

                        if col1.button("✅ Resolvió (Opción 2)"):
                            # Mismo flujo que el paso 1 pero registramos "2do Intento"
                            dur = duracion_desde(st.session_state.dtc_inicio)
                            motor.registrar_estadistica(
                                st.session_state.dtc_actual, "DTC", tipo_v,
                                "Acierto 2do Intento", st.session_state.user, dur)
                            motor.registrar_historial(
                                st.session_state.user, "DTC",
                                st.session_state.dtc_actual, tipo_v,
                                res.get('causa_s',''), res.get('solucion_s',''), "Acierto 2do Intento")
                            datos_pdf = {
                                "usuario": st.session_state.user,
                                "fecha": datetime.now().strftime("%d/%m/%Y %H:%M"),
                                "tecnologia": tipo_v, "metodo": "DTC",
                                "entrada": st.session_state.dtc_actual,
                                "duracion": f"{dur}s",
                                "causa": res.get('causa_s',''), "solucion": res.get('solucion_s',''),
                                "seguridad": res['seguridad'],
                                "resultado": "Resuelto en 2do intento"
                            }
                            st.session_state.pdf_bytes    = generar_pdf_diagnostico(datos_pdf)
                            st.session_state.pdf_filename = f"diagnostico_{st.session_state.dtc_actual}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
                            st.session_state.diag_mensaje = "✅ Diagnóstico exitoso registrado. Descarga el reporte abajo."
                            reset_diag()
                            st.rerun()

                        if col2.button("❌ Tampoco funcionó"):
                            # Se agotaron ambas hipótesis. Pasamos al reporte.
                            st.session_state.paso_diag = 3; st.rerun()

                    # — PASO 3: El sistema no pudo resolver el caso —
                    # El técnico describe el problema y lo envía como reporte
                    # pendiente para que el administrador lo estudie y enseñe
                    # la solución al sistema (módulo de aprendizaje).
                    elif st.session_state.paso_diag == 3:
                        st.warning("⚠️ Se agotaron las soluciones. Envía el caso al experto.")
                        obs = st.text_area("Describe el problema con detalle:")
                        if st.button("📤 Enviar Reporte"):
                            motor.registrar_caso_pendiente(
                                st.session_state.dtc_actual, tipo_v, obs, "DTC",
                                st.session_state.user)
                            st.success("Reporte enviado correctamente.")
                            reset_diag()
                else:
                    # El código DTC no existe en nuestra base de conocimiento
                    st.error("❌ Código DTC no encontrado en la base de datos.")
                    if not st.session_state.dtc_actual.startswith("P"):
                        st.caption("ℹ️ El prototipo se concentra en códigos de la categoría P "
                                   "(motor y transmisión).")


        # ── MODO SÍNTOMAS ─────────────────────────────────────────────────────
        # El técnico describe la falla con sus propias palabras.
        # El motor expande esas palabras con sinónimos técnicos automotrices
        # y busca la regla con más coincidencias en la BD.
        else:
            sint = st.text_input("Describa la falla física (ej: 'motor pierde potencia y humo negro')")
            col_a, col_b = st.columns([1, 4])

            if col_a.button("🔎 Analizar Síntoma"):
                # Si el texto cambió respecto al anterior, empezamos limpio
                if sint.strip() != st.session_state.sint_actual:
                    reset_sint()
                if sint.strip():
                    # El motor devuelve una lista ordenada por confianza descendente.
                    # Tomamos solo el primer resultado (el de mayor confianza).
                    _t0 = time.perf_counter()
                    resultados = motor.buscar_por_sintoma(sint, tipo_v)
                    st.session_state.sint_t_inf = time.perf_counter() - _t0   # RNF3
                    fila = resultados[0] if resultados else None
                    if fila:
                        st.session_state.sint_res    = fila
                        st.session_state.sint_actual = sint.strip()
                        st.session_state.sint_inicio = time.time()
                        st.session_state.paso_sint   = 1
                    else:
                        # Sin coincidencias: ni el texto ni sus sinónimos aparecen en la BD
                        st.session_state.sint_actual = sint.strip()
                        st.session_state.paso_sint   = -1
                    st.rerun()

            if col_b.button("🗑️ Limpiar"):
                reset_sint(); st.rerun()

            # — Sin resultados: ofrecemos reportar el síntoma desconocido —
            if st.session_state.paso_sint == -1:
                st.info("Sin coincidencias en la base de datos para ese síntoma.")
                st.caption("💡 Intenta con otras palabras clave o términos del problema")
                if st.button("📤 Reportar síntoma no resuelto"):
                    motor.registrar_caso_pendiente(
                        st.session_state.sint_actual, tipo_v,
                        "Sin coincidencia en base", "Sintoma", st.session_state.user)
                    st.success("Síntoma reportado para futura investigación.")
                    reset_sint()

            # — PASO 1: Causa principal —
            elif st.session_state.paso_sint == 1:
                r = st.session_state.sint_res
                mostrar_confianza(r["confianza"])   # barra de porcentaje de coincidencia
                seguridad = r["seguridad"] or ""
                mostrar_precaucion(seguridad)
                st.info(f"**Causa 1:** {r['causa_p']}\n\n**Solución 1:** {r['solucion_p']}")
                mostrar_explicacion("Síntoma", st.session_state.sint_actual, tipo_v, r,
                                    st.session_state.get('sint_t_inf', 0.0))
                col1, col2 = st.columns(2)

                if col1.button("✅ Resolvió el problema", key="sint_ok1"):
                    dur = duracion_desde(st.session_state.sint_inicio)
                    motor.registrar_estadistica(
                        st.session_state.sint_actual, "Sintoma", tipo_v,
                        "Acierto 1er Intento", st.session_state.user, dur)
                    motor.registrar_historial(
                        st.session_state.user, "Sintoma",
                        st.session_state.sint_actual, tipo_v,
                        r['causa_p'], r['solucion_p'], "Acierto 1er Intento")
                    # Además incrementamos el contador de éxitos de esta regla específica.
                    # Así las reglas más efectivas suben en el ranking de la BD.
                    if r.get("id"):
                        motor.registrar_exito_regla(r["id"])
                    datos_pdf = {
                        "usuario": st.session_state.user,
                        "fecha": datetime.now().strftime("%d/%m/%Y %H:%M"),
                        "tecnologia": tipo_v, "metodo": "Síntoma",
                        "entrada": st.session_state.sint_actual,
                        "duracion": f"{dur}s",
                        "causa": r['causa_p'], "solucion": r['solucion_p'],
                        "seguridad": seguridad,
                        "resultado": "Resuelto en 1er intento"
                    }
                    st.session_state.pdf_bytes    = generar_pdf_diagnostico(datos_pdf)
                    st.session_state.pdf_filename = f"diagnostico_sint_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
                    st.session_state.diag_mensaje = "✅ Diagnóstico exitoso registrado. Descarga el reporte abajo."
                    reset_sint()
                    st.rerun()

                if col2.button("❌ No funcionó", key="sint_no1"):
                    st.session_state.paso_sint = 2; st.rerun()

            # — PASO 2: Causa secundaria —
            elif st.session_state.paso_sint == 2:
                r = st.session_state.sint_res
                mostrar_confianza(r["confianza"])
                st.error("🔎 Ruta Secundaria de Inspección")
                if r["causa_s"]:
                    st.info(f"**Causa 2:** {r['causa_s']}\n\n**Solución 2:** {r['solucion_s']}")
                else:
                    st.warning("No hay causa secundaria registrada.")
                mostrar_explicacion("Síntoma", st.session_state.sint_actual, tipo_v, r,
                                    st.session_state.get('sint_t_inf', 0.0))
                col1, col2 = st.columns(2)

                if col1.button("✅ Resolvió (Opción 2)", key="sint_ok2"):
                    dur = duracion_desde(st.session_state.sint_inicio)
                    motor.registrar_estadistica(
                        st.session_state.sint_actual, "Sintoma", tipo_v,
                        "Acierto 2do Intento", st.session_state.user, dur)
                    motor.registrar_historial(
                        st.session_state.user, "Sintoma",
                        st.session_state.sint_actual, tipo_v,
                        r['causa_s'], r['solucion_s'], "Acierto 2do Intento")
                    datos_pdf = {
                        "usuario": st.session_state.user,
                        "fecha": datetime.now().strftime("%d/%m/%Y %H:%M"),
                        "tecnologia": tipo_v, "metodo": "Síntoma",
                        "entrada": st.session_state.sint_actual,
                        "duracion": f"{dur}s",
                        "causa": r['causa_s'], "solucion": r['solucion_s'],
                        "seguridad": r.get('seguridad',''),
                        "resultado": "Resuelto en 2do intento"
                    }
                    st.session_state.pdf_bytes    = generar_pdf_diagnostico(datos_pdf)
                    st.session_state.pdf_filename = f"diagnostico_sint_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
                    st.session_state.diag_mensaje = "✅ Diagnóstico exitoso registrado. Descarga el reporte abajo."
                    reset_sint()
                    st.rerun()

                if col2.button("❌ Tampoco funcionó", key="sint_no2"):
                    st.session_state.paso_sint = 3; st.rerun()

            # — PASO 3: Reporte al experto —
            elif st.session_state.paso_sint == 3:
                st.warning("⚠️ Se agotaron las soluciones. Envía el caso al experto.")
                obs = st.text_area("Añade una observación detallada del caso:")
                if st.button("📤 Enviar Reporte a Experto"):
                    motor.registrar_caso_pendiente(
                        st.session_state.sint_actual, tipo_v, obs, "Sintoma",
                        st.session_state.user)
                    st.success("Reporte enviado. ¡Gracias por la retroalimentación!")
                    reset_sint(); st.rerun()


    # ══════════════════════════════════════════════════════════════════════════
    # PESTAÑAS EXCLUSIVAS DEL ADMINISTRADOR
    # Solo el rol "Administrador" puede ver y usar lo que viene a continuación
    # ══════════════════════════════════════════════════════════════════════════
    if st.session_state.rol == "Administrador":

        # ── PESTAÑA 1 — BASE DE CONOCIMIENTO ──────────────────────────────────
        # El admin puede ver, agregar, editar y eliminar las reglas de diagnóstico.
        # Las reglas son el conocimiento del sistema: cada una asocia un código DTC
        # o síntoma con sus causas probables y sus soluciones.
        with tabs[1]:
            st.header("📚 Gestión de Base de Conocimiento")
            df = cargar_reglas()

            # Tabla completa de todas las reglas existentes
            st.dataframe(df, use_container_width=True, height=280)
            if not df.empty and 'tipo_vehiculo' in df.columns:
                n_act = int((df['tipo_vehiculo'] == TECNOLOGIA_ACTIVA).sum())
                st.caption(f"Reglas activas ({TECNOLOGIA_ACTIVA}): {n_act} · "
                           f"Reservadas e inactivas (Híbrido/Eléctrico): {len(df) - n_act}")

            # Aviso cuando el módulo de aprendizaje automático ha generado reglas nuevas.
            # Esto pasa cuando el admin resuelve un reporte pendiente en la pestaña siguiente.
            aprendidas = len(df[df['origen'] == 'aprendizaje']) if 'origen' in df.columns else 0
            if aprendidas:
                st.info(f"🤖 **{aprendidas} regla(s) generada(s) automáticamente** por el módulo de aprendizaje")

            # Sub-pestañas para las tres operaciones CRUD principales
            sub1, sub2, sub3 = st.tabs(["➕ Añadir", "✏️ Editar", "🗑️ Eliminar"])

            # — Añadir nueva regla manualmente —
            with sub1:
                # clear_on_submit=True limpia los campos después de guardar
                with st.form("add_form", clear_on_submit=True):
                    c1, c2 = st.columns(2)
                    n_dtc  = c1.text_input("DTC", help="Ej: P0300. Usa N/A si la regla es solo por síntoma.").upper()
                    n_tec  = c1.selectbox("Tecnología", [TECNOLOGIA_ACTIVA],
                                          help="Híbrido y Eléctrico están reservados para trabajo futuro.")
                    n_sin  = c2.text_area("Síntoma")
                    n_cp   = st.text_area("Causa 1")
                    n_sp   = st.text_area("Solución 1")
                    n_cs   = st.text_area("Causa 2")          # opcional
                    n_ss   = st.text_area("Solución 2")       # opcional
                    n_prot = st.text_input("Precaución (opcional)")
                    if st.form_submit_button("💾 Guardar"):
                        n_dtc = n_dtc.strip() or "N/A"
                        if n_dtc != "N/A" and not validar_dtc(n_dtc):
                            st.error("DTC con formato inválido (ej: P0300). Usa N/A si la regla es solo por síntoma.")
                        else:
                            with get_conn() as conn:
                                cur = conn.cursor()
                                cur.execute(
                                    '''INSERT INTO reglas_diagnostico
                                       (dtc,tipo_vehiculo,sintoma,causa_principal,solucion_principal,
                                        causa_secundaria,solucion_secundaria,protocolo_seguridad)
                                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s)''',
                                    (n_dtc,n_tec,n_sin,n_cp,n_sp,n_cs,n_ss,n_prot))
                                conn.commit()
                            st.success("Regla guardada."); st.rerun()

            # — Editar una regla existente —
            with sub2:
                df_edit = cargar_reglas()
                if df_edit.empty:
                    st.info("No hay reglas para editar.")
                else:
                    # El admin selecciona la regla por ID
                    id_ed = st.selectbox("ID a editar", df_edit['id'], key="sel_editar")
                    with get_conn() as conn:
                        cur = conn.cursor()
                        cur.execute("SELECT * FROM reglas_diagnostico WHERE id=%s", (id_ed,))
                        data = cur.fetchone()
                    if data:
                        # Precargamos el formulario con los valores actuales de la regla
                        # RealDictCursor devuelve dict, accedemos por nombre de columna
                        with st.form("edit_form"):
                            e_dtc  = st.text_input("DTC",       value=data['dtc'] or "")
                            # Las reglas heredadas de Híbrido/Eléctrico se pueden editar,
                            # pero quedan inactivas: el diagnóstico solo consulta Combustión.
                            _tecs  = list(TECNOLOGIAS)
                            e_tec  = st.selectbox("Tecnología", _tecs,
                                index=_tecs.index(data['tipo_vehiculo']) if data['tipo_vehiculo'] in _tecs else 0,
                                format_func=etiqueta_tecnologia)
                            e_sin  = st.text_area("Síntoma",    value=data['sintoma'] or "")
                            e_cp   = st.text_area("Causa 1",    value=data['causa_principal'] or "")
                            e_sp   = st.text_area("Solución 1", value=data['solucion_principal'] or "")
                            e_cs   = st.text_area("Causa 2",    value=data['causa_secundaria'] or "")
                            e_ss   = st.text_area("Solución 2", value=data['solucion_secundaria'] or "")
                            e_prot = st.text_input("Precaución (opcional)", value=data['protocolo_seguridad'] or "")
                            if st.form_submit_button("💾 Actualizar"):
                                e_dtc = e_dtc.strip().upper() or "N/A"
                                if e_dtc != "N/A" and not validar_dtc(e_dtc):
                                    st.error("DTC con formato inválido (ej: P0300). Usa N/A si la regla es solo por síntoma.")
                                else:
                                    motor.actualizar_regla(id_ed,e_dtc,e_tec,e_sin,e_cp,e_sp,e_cs,e_ss,e_prot)
                                    st.success("✅ Actualizado."); st.rerun()

            # — Eliminar una regla —
            with sub3:
                df_del = cargar_reglas()
                if not df_del.empty:
                    # Mostramos el ID junto con DTC y síntoma para identificar mejor
                    opciones = {
                        row['id']: f"ID {row['id']} │ {row['dtc']} │ {str(row['sintoma'])[:35]}…"
                        for _, row in df_del.iterrows()
                    }
                    id_el = st.selectbox("Regla a eliminar:",
                        options=list(opciones.keys()), format_func=lambda x: opciones[x])
                    # Requerimos confirmación explícita antes de borrar
                    conf = st.checkbox(f"✅ Confirmo eliminar permanentemente la regla ID {id_el}")
                    if st.button("🗑️ Eliminar", type="primary", disabled=not conf):
                        with get_conn() as conn:
                            cur = conn.cursor()
                            cur.execute("DELETE FROM reglas_diagnostico WHERE id=%s", (id_el,))
                            conn.commit()
                        st.success(f"Regla {id_el} eliminada."); st.rerun()
                else:
                    st.info("No hay reglas registradas.")


        # ── PESTAÑA 2 — RESOLVER REPORTES + APRENDIZAJE ───────────────────────
        # Aquí el admin estudia los casos que los técnicos no pudieron resolver
        # y documenta la solución real. Al guardar, el sistema crea automáticamente
        # una nueva regla de diagnóstico con origen='aprendizaje'. Así el sistema
        # crece con cada caso nuevo que se presente en el taller.
        with tabs[2]:
            st.header("🛠️ Reportes Pendientes")

            # Traemos solo los casos que aún no han sido resueltos
            with get_conn() as conn:
                cur = conn.cursor()
                cur.execute("SELECT * FROM casos_pendientes WHERE resuelto=0")
                rows = cur.fetchall()
            pendientes = pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()
            st.dataframe(pendientes, use_container_width=True, height=260)

            if not pendientes.empty:
                st.divider()
                st.subheader("🤖 Resolver y Enseñar al Sistema")
                st.caption("Al completar los campos y guardar, el sistema aprende automáticamente y crea una nueva regla.")

                # El admin selecciona cuál reporte quiere resolver
                id_res = st.selectbox("Seleccionar reporte:", pendientes['id'])
                fila_rep = pendientes[pendientes['id'] == id_res].iloc[0]
                # Mostramos el contexto del caso: qué reportó el mecánico
                st.info(f"**Falla reportada:** {fila_rep['dtc_o_sintoma']}\n\n"
                        f"**Observación del mecánico:** {fila_rep['comentario_mecanico']}")

                c1, c2 = st.columns(2)
                causa_r    = c1.text_area("✏️ Causa real encontrada:")
                solucion_r = c2.text_area("✏️ Solución que funcionó:")

                col_ap, col_el = st.columns(2)

                if col_ap.button("🧠 Resolver y Enseñar al Sistema", type="primary"):
                    if causa_r and solucion_r:
                        # resolver_caso_pendiente hace dos cosas:
                        # 1. Marca el reporte como resuelto en casos_pendientes
                        # 2. Inserta una nueva regla en reglas_diagnostico con origen='aprendizaje'
                        ok = motor.resolver_caso_pendiente(int(id_res), causa_r, solucion_r)
                        if ok:
                            st.success("✅ Reporte resuelto. ¡Nueva regla añadida automáticamente a la base de conocimiento!")
                            st.balloons()  # celebración visual
                            st.rerun()
                    else:
                        st.error("Debes completar causa y solución para enseñar al sistema.")

                if col_el.button("🗑️ Descartar sin aprender"):
                    # Si el reporte es un duplicado o un error, lo borramos sin crear regla
                    motor.borrar_reporte_pendiente(int(id_res))
                    st.warning("Reporte descartado sin generar regla.")
                    st.rerun()

            # Historial de lo que ya se resolvió anteriormente
            st.divider()
            st.subheader("📋 Historial de Reportes Resueltos")
            with get_conn() as conn:
                cur = conn.cursor()
                cur.execute("SELECT * FROM casos_pendientes WHERE resuelto=1 ORDER BY fecha DESC")
                rows = cur.fetchall()
            resueltos = pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()
            if not resueltos.empty:
                st.dataframe(resueltos, use_container_width=True, height=200)
            else:
                st.info("Aún no hay reportes resueltos.")


        # ── PESTAÑA 3 — ESTADÍSTICAS ───────────────────────────────────────────
        # Análisis cuantitativo del desempeño del sistema.
        # Estos datos alimentan la sección de resultados de la tesis:
        # tasa de acierto, fallas más frecuentes, tiempo promedio de diagnóstico.
        with tabs[3]:
            st.header("📈 Análisis de Diagnósticos")

            # Traemos todos los registros de la tabla de estadísticas
            with get_conn() as conn:
                cur = conn.cursor()
                cur.execute("SELECT * FROM estadisticas")
                rows = cur.fetchall()
            stats = pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()

            if not stats.empty:
                # Alias de columnas para no repetir strings largos en el código
                col_res = 'resultado'
                col_tip = 'tipo_diagnostico'
                col_tec = 'tecnologia'
                col_cod = 'identificador'
                col_fec = 'fecha'
                col_dur = 'duracion_seg'

                # — Cálculos principales —
                total    = len(stats)
                aciertos = int(stats[col_res].str.contains('Acierto', na=False).sum())
                fallidos = total - aciertos
                tasa     = round(aciertos / total * 100, 1) if total else 0
                # Duración promedio SOLO de diagnósticos exitosos: los "Fallo Reportado"
                # se guardan con duración 0 y bajaban artificialmente el promedio.
                _ok = stats[stats[col_res].str.contains('Acierto', na=False)]
                dur_prom = round(_ok[col_dur].mean()) if (col_dur in stats.columns and not _ok.empty) else 0

                # — Fila de métricas grandes en la parte superior —
                m1,m2,m3,m4,m5 = st.columns(5)
                m1.metric("Total Diagnósticos",   total)
                m2.metric("Exitosos",              int(aciertos))
                m3.metric("No Resueltos",          fallidos)
                m4.metric("Tasa de Éxito",         f"{tasa} %")
                m5.metric("Duración Promedio",     f"{dur_prom}s")
                st.divider()

                # — Fila 1 de gráficas: distribución de resultados + top 5 fallas —
                g1, g2 = st.columns(2)
                with g1:
                    cnt = stats[col_res].value_counts().reset_index()
                    cnt.columns = ['Resultado','Cantidad']
                    fig = px.pie(cnt, names='Resultado', values='Cantidad',
                        title='Distribución de Resultados', hole=0.45,
                        color_discrete_sequence=px.colors.qualitative.Set2)
                    st.plotly_chart(fig, use_container_width=True)
                with g2:
                    # Las 5 fallas/síntomas que más veces se han diagnosticado
                    top5 = stats[col_cod].value_counts().head(5).reset_index()
                    top5.columns = ['Falla','Diagnósticos']
                    fig = px.bar(top5, x='Falla', y='Diagnósticos',
                        title='Top 5 Fallas Más Frecuentes',
                        color='Diagnósticos', color_continuous_scale='Teal')
                    st.plotly_chart(fig, use_container_width=True)

                # — Fila 2 de gráficas: diagnósticos por técnico + resultados por método —
                g3, g4 = st.columns(2)
                with g3:
                    # (Con el alcance en combustión, una torta por motorización tendría
                    # una sola porción; se reemplaza por la carga por técnico.)
                    por_tec_g = stats.groupby('usuario').size().reset_index(name='Diagnósticos')
                    fig = px.bar(por_tec_g, x='usuario', y='Diagnósticos',
                        title='Diagnósticos por Técnico',
                        color='Diagnósticos', color_continuous_scale='Teal')
                    st.plotly_chart(fig, use_container_width=True)
                with g4:
                    # Muestra si el método DTC o el de síntomas tiene más aciertos
                    cross = stats.groupby([col_tip, col_res]).size().reset_index(name='Cantidad')
                    fig = px.bar(cross, x=col_tip, y='Cantidad', color=col_res,
                        barmode='group', title='Resultados por Método',
                        color_discrete_sequence=px.colors.qualitative.Set1)
                    st.plotly_chart(fig, use_container_width=True)

                # — Línea temporal: diagnósticos por día —
                # Útil para ver la actividad durante la semana de pruebas del Sprint 4
                st.subheader("📅 Evolución Temporal")
                try:
                    stats['fecha_dt'] = pd.to_datetime(stats[col_fec])
                    stats['dia']      = stats['fecha_dt'].dt.date
                    por_dia = stats.groupby('dia').size().reset_index(name='Diagnósticos')
                    fig = px.line(por_dia, x='dia', y='Diagnósticos',
                        title='Diagnósticos por Día', markers=True)
                    st.plotly_chart(fig, use_container_width=True)
                except Exception:
                    pass  # si las fechas están mal formateadas, omitimos esta gráfica

                # — Tiempo promedio por tipo de resultado —
                if col_dur in stats.columns:
                    st.subheader("⏱️ Tiempo Promedio por Resultado")
                    dur_res = _ok.groupby(col_res)[col_dur].mean().round().reset_index()
                    dur_res.columns = ['Resultado','Segundos promedio']
                    fig = px.bar(dur_res, x='Resultado', y='Segundos promedio',
                        color='Segundos promedio', color_continuous_scale='Blues')
                    st.plotly_chart(fig, use_container_width=True)

                # — Listado de fallas que el sistema no pudo resolver —
                # Estos son candidatos para enriquecer la base de conocimiento
                st.subheader("🔴 Fallas Sin Resolver (más frecuentes)")
                no_res = stats[stats[col_res].str.contains('Fallo', na=False)]
                if not no_res.empty:
                    resumen = no_res[col_cod].value_counts().reset_index()
                    resumen.columns = ['Falla / Síntoma','Veces Reportada']
                    st.dataframe(resumen, use_container_width=True, height=200)
                else:
                    st.success("¡Sin casos pendientes sin resolver!")

                # Datos en crudo para quien quiera inspeccionarlos directamente
                with st.expander("🗃️ Datos brutos"):
                    st.dataframe(stats, use_container_width=True, height=300)
            else:
                st.info("Aún no hay datos para mostrar.")


        # ── PESTAÑA 4 — DASHBOARD DE VALIDACIÓN (Sprint 4) ────────────────────
        # Vista diseñada específicamente para las pruebas con los 6 técnicos.
        # Permite al investigador monitorear en tiempo real cómo va cada técnico,
        # cuál es la tasa de acierto global y si se está cumpliendo el objetivo del 70%.
        with tabs[4]:
            st.header("🎓 Dashboard de Validación — Sprint 4")
            st.caption("Vista en tiempo real para las pruebas con los 6 técnicos de Popayán")

            # Botón de refresco manual: los datos de la BD no se actualizan solos
            # a menos que Streamlit re-ejecute el script. Este botón fuerza eso.
            col_refresh, _ = st.columns([1, 4])
            if col_refresh.button("🔄 Actualizar datos", use_container_width=True):
                st.rerun()

            # Cargamos el historial detallado (uno por diagnóstico EXITOSO) y las
            # estadísticas (uno por diagnóstico, exitoso o fallido).
            # IMPORTANTE: los indicadores de validación se calculan sobre `estadisticas`.
            # `historial_diagnosticos` solo guarda casos resueltos; calcular la tasa de
            # acierto sobre él daba siempre 100 %, sin importar cuántos casos fallaran.
            with get_conn() as conn:
                cur = conn.cursor()
                cur.execute("SELECT * FROM historial_diagnosticos ORDER BY fecha DESC")
                rows_hist = cur.fetchall()
                cur.execute("SELECT * FROM estadisticas ORDER BY fecha DESC")
                rows_stats = cur.fetchall()
            hist      = pd.DataFrame([dict(r) for r in rows_hist])  if rows_hist  else pd.DataFrame()
            stats_val = pd.DataFrame([dict(r) for r in rows_stats]) if rows_stats else pd.DataFrame()

            if not stats_val.empty:
                # — Filtros de visualización —
                col_f1, col_f2 = st.columns(2)
                tecnicos = ["Todos"] + sorted(stats_val['usuario'].dropna().unique().tolist())
                tec_sel  = col_f1.selectbox("Filtrar por técnico:", tecnicos)
                rango    = col_f2.selectbox("Período:",
                    ["Hoy","Últimos 7 días","Últimos 30 días","Todo"])

                # Filtro por fecha: convertimos la columna a datetime y aplicamos el rango.
                # tz_localize(None) evita conflictos si alguna fecha llega con zona horaria.
                ahora  = datetime.now()
                rangos = {"Hoy": 1, "Últimos 7 días": 7, "Últimos 30 días": 30, "Todo": 9999}
                dias   = rangos[rango]
                stats_val['fecha_dt'] = pd.to_datetime(stats_val['fecha'], errors='coerce')
                if not hist.empty:
                    hist['fecha_dt'] = pd.to_datetime(hist['fecha'], errors='coerce')
                if dias < 9999:
                    desde = ahora - timedelta(days=dias)
                    stats_val = stats_val[stats_val['fecha_dt'].dt.tz_localize(None) >= desde]
                    if not hist.empty:
                        hist = hist[hist['fecha_dt'].dt.tz_localize(None) >= desde]
                if tec_sel != "Todos":
                    stats_val = stats_val[stats_val['usuario'] == tec_sel]
                    if not hist.empty:
                        hist = hist[hist['usuario'] == tec_sel]

                st.divider()

                if stats_val.empty:
                    # Hay datos en la BD, pero el filtro activo los está ocultando
                    st.warning("⚠️ Hay diagnósticos en la BD pero el filtro actual no muestra ninguno. "
                               "Cambia el período a **'Todo'** o selecciona **'Todos'** los técnicos.")
                else:
                    # — Indicadores de validación del Sprint 4 (documento v2) —
                    #   1. Tasa de acierto (meta META_TASA_ACIERTO %)
                    #   2. Tiempo promedio de diagnóstico (solo casos exitosos)
                    #   3. Tasa de reincidencia: casos que agotan las dos rutas
                    es_acierto = stats_val['resultado'].str.contains('Acierto', na=False)
                    total_val  = len(stats_val)
                    exito_val  = int(es_acierto.sum())
                    fallo_val  = total_val - exito_val
                    tasa_val   = round(exito_val / total_val * 100, 1)
                    reinc_val  = round(fallo_val / total_val * 100, 1)
                    dur_ok     = pd.to_numeric(stats_val.loc[es_acierto, 'duracion_seg'], errors='coerce')
                    dur_val    = int(round(dur_ok.mean())) if dur_ok.notna().any() else 0

                    k1,k2,k3,k4,k5 = st.columns(5)
                    k1.metric("Casos Evaluados",        total_val)
                    k2.metric("Exitosos",               exito_val)
                    k3.metric("Tasa de Acierto",        f"{tasa_val} %")
                    k4.metric("Reincidencia (no resueltos)", f"{reinc_val} %")
                    k5.metric("Tiempo Promedio",        f"{dur_val}s")

                    # — Barra de progreso hacia la meta de acierto —
                    # Verde si ya se alcanzó, amarillo si aún no.
                    objetivo  = META_TASA_ACIERTO
                    color_obj = "#4CAF50" if tasa_val >= objetivo else "#FFC107"
                    st.markdown(f"""
                    <div style='background:#1a1a2e;border:1px solid {color_obj};
                                border-radius:10px;padding:16px;margin:12px 0;'>
                        <b style='color:{color_obj};'>🎯 Objetivo Sprint 4: {objetivo}% de acierto</b>
                        <div style='background:#333;border-radius:5px;height:12px;margin-top:8px;'>
                            <div style='width:{min(tasa_val,100)}%;background:{color_obj};
                                        height:12px;border-radius:5px;'></div>
                        </div>
                        <div style='color:#aaa;font-size:12px;margin-top:4px;'>
                            Actual: {tasa_val}% / {objetivo}% objetivo
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    # — Comparación contra el método tradicional —
                    # El documento exige comparar contra el tiempo promedio del método
                    # tradicional reportado en las entrevistas iniciales. Ese dato NO se
                    # inventa: el investigador lo digita aquí cuando lo tenga.
                    st.subheader("⏱️ Comparación con el método tradicional")
                    t_trad = st.number_input(
                        "Tiempo promedio del método tradicional (segundos), según las entrevistas",
                        min_value=0, value=0, step=30,
                        help="Déjalo en 0 mientras no tengas el dato de las entrevistas.")
                    if t_trad > 0 and dur_val > 0:
                        red = round((t_trad - dur_val) / t_trad * 100, 1)
                        st.metric("Reducción del tiempo de diagnóstico", f"{red} %",
                                  delta=f"{t_trad - dur_val:+d} s respecto al método tradicional")
                    else:
                        st.caption("Pendiente: ingresa el tiempo del método tradicional para "
                                   "calcular la reducción. No se asume ningún valor por defecto.")

                    st.divider()

                    # — Tabla resumen por técnico —
                    st.subheader("📊 Resultados por Técnico")
                    por_tec = stats_val.groupby('usuario').agg(
                        Total=('resultado','count'),
                        Exitosos=('resultado', lambda x: int(x.str.contains('Acierto',na=False).sum()))
                    ).reset_index()
                    por_tec['No resueltos'] = por_tec['Total'] - por_tec['Exitosos']
                    # Conversión explícita a float para evitar TypeError con pandas + Python 3.14
                    por_tec['Tasa %'] = (por_tec['Exitosos'].astype(float) / por_tec['Total'].astype(float) * 100).round(1)
                    st.dataframe(por_tec, use_container_width=True, height=220)

                    # — Detalle caso por caso (solo diagnósticos resueltos) —
                    st.subheader("📋 Historial Detallado (casos resueltos)")
                    if hist.empty:
                        st.info("No hay casos resueltos en el filtro actual.")
                    else:
                        st.dataframe(hist.drop(columns=['fecha_dt'], errors='ignore'),
                            use_container_width=True, height=300)

                    # Exportamos para incluir los datos en la tesis (utf-8-sig: Excel abre bien las tildes)
                    fecha_arch = datetime.now().strftime('%Y%m%d')
                    ce1, ce2 = st.columns(2)
                    ce1.download_button(
                        "📥 Exportar matriz de validación (CSV)",
                        data=stats_val.drop(columns=['fecha_dt'], errors='ignore')
                                      .to_csv(index=False).encode('utf-8-sig'),
                        file_name=f"validacion_sprint4_{fecha_arch}.csv",
                        mime="text/csv", key="csv_validacion")
                    if not hist.empty:
                        ce2.download_button(
                            "📥 Exportar historial detallado (CSV)",
                            data=hist.drop(columns=['fecha_dt'], errors='ignore')
                                     .to_csv(index=False).encode('utf-8-sig'),
                            file_name=f"historial_sprint4_{fecha_arch}.csv",
                            mime="text/csv", key="csv_historial")
            else:
                # La tabla realmente está vacía: nadie ha hecho diagnósticos aún
                st.info("Aún no hay diagnósticos registrados.")
                st.caption("Los diagnósticos aparecen aquí automáticamente cuando los técnicos usen el sistema.")


        # ── PESTAÑA 5 — GESTIÓN DE USUARIOS ───────────────────────────────────
        # El administrador puede crear cuentas nuevas (mecánicos u otros admins)
        # y eliminar las que ya no se necesitan.
        # El sistema no permite eliminar la cuenta propia para evitar que el admin
        # se quede sin acceso por error.
        with tabs[5]:
            st.header("👥 Gestión de Usuarios")
            sub_crear, sub_eliminar = st.tabs(["➕ Crear Usuario", "🗑️ Eliminar Usuario"])

            # — Crear usuario nuevo —
            with sub_crear:
                with st.form("crear_u", clear_on_submit=True):
                    c1,c2,c3 = st.columns(3)
                    u_n = c1.text_input("Nombre de usuario")
                    u_p = c2.text_input("Contraseña", type="password")
                    u_r = c3.selectbox("Rol", ["Mecanico","Administrador"])
                    if st.form_submit_button("Crear"):
                        with get_conn() as conn:
                            try:
                                cur = conn.cursor()
                                cur.execute(
                                    "INSERT INTO usuarios (usuario,password,rol) VALUES (%s,%s,%s)",
                                    (u_n, hash_pw(u_p), u_r))
                                conn.commit()
                                st.success(f"Usuario '{u_n}' creado.")
                            except Exception:
                                conn.rollback()
                                st.error("Ese usuario ya existe.")

            # — Eliminar usuario existente —
            with sub_eliminar:
                with get_conn() as conn:
                    cur = conn.cursor()
                    cur.execute("SELECT id,usuario,rol FROM usuarios")
                    rows = cur.fetchall()
                df_usr = pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame(columns=['id','usuario','rol'])
                st.dataframe(df_usr, use_container_width=True, height=220)
                if not df_usr.empty:
                    usr_b = st.selectbox("Usuario a eliminar", df_usr['usuario'])
                    # Doble confirmación para evitar borrados accidentales
                    conf_u = st.checkbox(f"✅ Confirmo eliminar al usuario '{usr_b}' permanentemente")
                    if st.button("🚨 Eliminar Usuario", type="primary", disabled=not conf_u):
                        if usr_b == st.session_state.user:
                            # Protección: no puedes borrarte a ti mismo estando activo
                            st.error("No puedes eliminar tu propia cuenta activa.")
                        else:
                            with get_conn() as conn:
                                cur = conn.cursor()
                                cur.execute("DELETE FROM usuarios WHERE usuario=%s", (usr_b,))
                                conn.commit()
                            st.success(f"Usuario '{usr_b}' eliminado.")
                            st.rerun()
                else:
                    st.info("No hay usuarios registrados.")