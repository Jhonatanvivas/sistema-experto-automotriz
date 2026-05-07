import streamlit as st   # el framework que convierte este script en una app web
import hashlib           # para cifrar contraseñas con SHA-256
import time              # medir duración de los diagnósticos en segundos
import io                # manejo de flujos de bytes (para el PDF en memoria)
import pandas as pd      # manipulación de tablas y datos del dashboard
import plotly.express as px    # gráficas interactivas rápidas
import plotly.graph_objects as go     # gráficas con más control manual
from datetime import datetime, timedelta   # fechas y cálculo de rangos temporales
from fpdf import FPDF                       # generación del reporte PDF descargable
from inference_engine import MotorInferencia  # nuestro motor de reglas lógicas
from database import get_conn, inicializar_bd
inicializar_bd()  # Aseguramos que la base de datos y sus tablas existan antes de arrancar la app
 
# ══════════════════════════════════════════════════════════════
# CONFIGURACIÓN
# ══════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Expert-Auto Popayán", # título en la pestaña del navegador
    page_icon="⚙️", 
    layout="wide",                    # usamos todo el ancho de pantalla
    initial_sidebar_state="expanded"  # la barra lateral arranca visible
)

# CSS global — dashboard oscuro profesional
# Inyectamos CSS directamente en el HTML que genera Streamlit.
# Esto nos da control sobre colores, bordes y tipografía que Streamlit
# no expone por defecto. El tema oscuro es intencional: los talleres
# suelen trabajar con poca luz y el alto contraste ayuda a leer en pantalla.
st.markdown("""
<style>
    /* Métricas grandes */
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
    /* Tabs */
    .stTabs [data-baseweb="tab"] { font-weight: 600; font-size: 14px; }
    /* Barra de confianza */
    .conf-bar { height: 10px; border-radius: 5px; margin-top: 4px; }
    /* Etiqueta de origen aprendizaje */
    .badge-aprendizaje {
        background: #0f3460; color: #4CAF50; padding: 2px 8px;
        border-radius: 20px; font-size: 11px; font-weight: 700;
    }
    .badge-manual {
        background: #1a1a2e; color: #888; padding: 2px 8px;
        border-radius: 20px; font-size: 11px;
    }
</style>
""", unsafe_allow_html=True)

# ── Estado de sesión ───────────────────────────────────────────
# Streamlit re-ejecuta todo el script cada vez que el usuario interactúa.
# session_state es el único lugar donde podemos guardar información entre
# esas re-ejecuciones sin perderla. Lo inicializamos una sola vez al arrancar.


if 'logueado' not in st.session_state:
    st.session_state.update({
        'logueado'       : False,  # ¿hay alguien autenticado?
        'rol'            : None,   # "Administrador" o "Mecanico"
        'user'           : None,   # nombre de usuario activo
        # Flujo de diagnóstico por DTC
        # paso_diag controla en qué etapa del árbol de decisión estamos:
        # 0 = sin iniciar, 1 = mostrando causa 1, 2 = causa 2, 3 = reporte
        'paso_diag'      : 0,
        'dtc_actual'     : '',  # el código que el técnico ingresó
        'dtc_inicio'     : 0,   # tiempo del momento en que empezó el diagnóstico
        # Flujo de diagnóstico por Síntomas
        # igual que DTC pero con su propio estado independiente
        'paso_sint'      : 0,   # -1 = sin resultados, 1 = causa 1, 2 = causa 2, 3 = reporte
        'sint_actual'    : '',  # texto del síntoma ingresado
        'sint_res'       : None,  # el dict con la regla más probable que devolvió el motor
        'sint_inicio'    : 0,
        # PDF listo para descarga 
        # Guardamos los bytes del PDF aquí para que sobrevivan al st.rerun().
        # Sin esto, el PDF se regenera después del reset y explota si los datos ya no están.
        'pdf_bytes'      : None,
        'pdf_filename'   : '',
        'diag_mensaje'   : '',   # mensaje de éxito que se muestra junto al botón de descarga
    })

# Instanciamos el motor de inferencia una sola vez.
# Este objeto abre conexiones a la BD y ejecuta las consultas de búsqueda.
motor = MotorInferencia()

# ══════════════════════════════════════════════════════════════
# UTILIDADES
# ══════════════════════════════════════════════════════════════
def hash_pw(pw): return hashlib.sha256(pw.encode()).hexdigest() #Convierte una contraseña en texto plano a su hash SHA-256. 
# Nunca guardamos contraseñas en la BD

def login(u, p): #Verifica credenciales contra la base de datos.
    with get_conn() as conn:   #Primero busca con contraseña hasheada; si no coincide, intenta
        cur = conn.cursor()                            # texto plano (compatibilidad con registros legacy del sistema anterior).
        cur.execute("SELECT rol FROM usuarios WHERE usuario=%s AND password=%s", (u, hash_pw(p)))
        res = cur.fetchone()
        if not res:  # compatibilidad texto plano legacy
            cur.execute("SELECT rol FROM usuarios WHERE usuario=%s AND password=%s", (u, p))
            res = cur.fetchone()
    return res['rol'] if res else None  # devuelve el rol o None si falla

def cargar_reglas(): #Trae todas las reglas de diagnóstico de la BD como un DataFrame.
    with get_conn() as conn:
        df = pd.read_sql_query(
            '''SELECT id, dtc, tipo_vehiculo, sintoma,
                      causa_principal, solucion_principal,
                      causa_secundaria, solucion_secundaria,
                      protocolo_seguridad, origen, veces_exitosa
               FROM reglas_diagnostico
               ORDER BY veces_exitosa DESC, id DESC''', conn)
    return df  #Las ordena por veces_exitosa para que las reglas más efectivas
               #aparezcan primero en la tabla del admin.

def reset_sint(): #Limpia todo el estado del flujo de síntomas para empezar desde cero. en un diagnostico nuevo
    st.session_state.update({'paso_sint':0,'sint_actual':'','sint_res':None,'sint_inicio':0})

def reset_diag(): #Igual que reset_sint pero para el flujo de DTC"
    st.session_state.update({'paso_diag':0,'dtc_actual':'','dtc_inicio':0})

def duracion_desde(ts): #Calcula cuántos segundos pasaron desde que empezó el diagnóstico.
                        #Esto alimenta la estadística de 'tiempo promedio de diagnóstico'.
    return int(time.time() - ts) if ts else 0

# ── Generador de PDF ──────────────────────────────────────────
def _pdf_texto(val) -> str: #Sanitiza cualquier valor antes de mandarlo a FPDF.
    """Convierte cualquier valor a texto seguro para FPDF (sin None, sin caracteres raros)."""

     # Primero nos aseguramos de que no llegue nada vacío o nulo
    if val is None or str(val).strip() in ("", "None", "nan"):
        return "No especificado"
    texto = str(val)
    # Reemplazamos caracteres especiales por sus equivalentes ASCII seguros.
    # Helvetica (la fuente que usamos) no renderiza unicode fuera de latin-1.
     # vocales con tilde → sin tilde
    replacements = {
        "\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"',
        "\u2013": "-", "\u2014": "-", "\u2026": "...",
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
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15) # salta página automáticamente si se llena

    # Calculamos el ancho útil de la página una sola vez.
    # En A4 son 210mm; con márgenes de ~10mm a cada lado quedan ~190mm.
    ANCHO = pdf.w - pdf.l_margin - pdf.r_margin   # ≈ 190mm
    LABEL_W = 52    # ancho fijo de la columna de etiquetas ejemplo: "Tecnico:", "Fecha:"

    # — Encabezado con fondo oscuro —
    pdf.set_fill_color(30, 30, 50)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(ANCHO, 13, "EXPERT-AUTO POPAYAN", ln=True, align="C", fill=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(ANCHO, 8, "Reporte de Diagnostico Automotriz", ln=True, align="C", fill=True)
    pdf.ln(4) # espacio vertical

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
        y_antes = pdf.get_y()
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
        ("Protocolo seguridad", datos.get("seguridad", "---")),
        ("Conclusion",          datos.get("resultado", "---")),
    ]
    for label, val in secciones:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(ANCHO, 7, f"{label}:", ln=True)
        pdf.set_font("Helvetica", "", 9) # fuente 9pt = más texto cabe horizontalmente
        pdf.set_fill_color(250, 250, 255)
        # Ancho explícito — nunca 0 para evitar el error de espacio
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

# ── Barra de confianza visual ─────────────────────────────────
# Se usa en el modo de diagnóstico por síntomas para mostrarle al técnico
# cuán seguro está el sistema de su recomendación
def mostrar_confianza(pct: int):
    #Renderiza una barra de progreso coloreada con el porcentaje de confianza.
    #Verde >= 70%, Amarillo >= 40%, Rojo < 40%.
    #El porcentaje lo calcula el motor de inferencia según cuántas palabras
    #del síntoma ingresado coincidieron con las reglas de la BD.

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

# ══════════════════════════════════════════════════════════════
# PANTALLA DE LOGIN
# Si nadie está autenticado, mostramos solo el formulario de acceso.
# ══════════════════════════════════════════════════════════════
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

# ══════════════════════════════════════════════════════════════
# INTERFAZ PRINCIPAL (usuario autenticado)
# ══════════════════════════════════════════════════════════════
else:
    # ── BARRA LATERAL ───────────────────────────────────────────────
    # Siempre visible después del login. Muestra quién está conectado,
    # su actividad personal y el botón de cerrar sesión.
    with st.sidebar:
        try:
            # Logo del taller, si no existe mostramos texto
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
            mis_diag = pd.read_sql_query(
                "SELECT resultado FROM estadisticas WHERE usuario=%s",
                conn, params=(st.session_state.user,))
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

    # ── PESTAÑAS DE NAVEGACIÓN ──────────────────────────────────────────────
    # El administrador ve todas las pestañas.
    # El mecánico solo ve Diagnóstico: no tiene acceso a la gestión del sistema.
    if st.session_state.rol == "Administrador":
        nombres_tabs = ["🔍 Diagnóstico", "📚 Base Conocimiento", "🛠️ Resolver Reportes",
                        "📈 Estadísticas", "🎓 Dashboard Validación", "👥 Usuarios"]
    else:
        nombres_tabs = ["🔍 Diagnóstico"]

    tabs = st.tabs(nombres_tabs)

    # ══════════════════════════════════════════════════════════
    # PESTAÑA 0 — DIAGNÓSTICO
    # El corazón del sistema. Aquí el técnico ingresa el código DTC o describe
    # los síntomas, y el motor de inferencia le guía por el árbol de decisión.
    # ══════════════════════════════════════════════════════════
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
        tipo_v = st.selectbox("Motorización", ["Combustión", "Híbrido", "Eléctrico"])

        # ── MODO DTC ───────────────────────────────────────────────
        if metodo == "DTC (Escáner)":
            codigo = st.text_input("Ingrese código DTC (ej: P0300)").upper().strip()
            c1, c2 = st.columns([1, 4])

            # Al presionar "Analizar", guardamos el código en session_state
            # y marcamos que estamos en el paso 1 del árbol de decisión
            if c1.button("🔎 Analizar DTC"):
                st.session_state.paso_diag  = 1
                st.session_state.dtc_actual = codigo
                st.session_state.dtc_inicio = time.time() # empezamos a medir el tiemp
                st.rerun()
            if c2.button("🗑️ Limpiar"):
                reset_diag(); st.rerun()

            # Si ya tenemos un código activo, consultamos el motor
            if st.session_state.paso_diag >= 1 and st.session_state.dtc_actual:
                res = motor.consultar_por_dtc(st.session_state.dtc_actual, tipo_v)

                # El protocolo de seguridad se muestra siempre, antes que cualquier
                # instrucción de diagnóstico. Esto es obligatorio para vehículos
                # con sistemas de alta tensión (híbridos y eléctricos).
                if res["encontrado"]:
                    st.warning(f"🛑 **SEGURIDAD:** {res['seguridad']}")

                    # — PASO 1: Primera hipótesis (causa más probable) —
                    if st.session_state.paso_diag == 1:
                        st.info(f"**Causa 1:** {res['causa_p']}\n\n**Solución 1:** {res['solucion_p']}")
                        col1, col2 = st.columns(2)
                        if col1.button("✅ Resolvió el problema"):
                            # El técnico confirma que la solución funcionó.
                            # Registramos el éxito en estadísticas e historial,
                            # generamos el PDF y preparamos el banner de descarga.

                            dur = duracion_desde(st.session_state.dtc_inicio)
                            motor.registrar_estadistica(
                                st.session_state.dtc_actual, "DTC", tipo_v,
                                "Acierto 1er Intento", st.session_state.user, dur)
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
                            reset_diag() # limpiamos el flujo activo
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
                    resultados = motor.buscar_por_sintoma(sint, tipo_v)
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
                mostrar_confianza(r["confianza"]) # barra de porcentaje de coincidencia
                seguridad = r["seguridad"] or "Sigue los protocolos estándar"
                st.warning(f"🛑 **SEGURIDAD:** {seguridad}")
                st.info(f"**Causa 1:** {r['causa_p']}\n\n**Solución 1:** {r['solucion_p']}")
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

    # ══════════════════════════════════════════════════════════
    # PESTAÑAS EXCLUSIVAS DEL ADMINISTRADOR
    # Solo el rol "Administrador" puede ver y usar lo que viene a continuación
    # ══════════════════════════════════════════════════════════
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
                    n_dtc  = c1.text_input("DTC").upper()  # siempre en mayúsculas
                    n_tec  = c1.selectbox("Tecnología", ["Combustión","Híbrido","Eléctrico"])
                    n_sin  = c2.text_area("Síntoma")
                    n_cp   = st.text_area("Causa 1")
                    n_sp   = st.text_area("Solución 1")
                    n_cs   = st.text_area("Causa 2")       # opcional
                    n_ss   = st.text_area("Solución 2")    # opcional
                    n_prot = st.text_input("Protocolo de Seguridad")
                    if st.form_submit_button("💾 Guardar"):
                        with get_conn() as conn:
                            conn.execute(
                                '''INSERT INTO reglas_diagnostico
                                   (dtc,tipo_vehiculo,sintoma,causa_principal,solucion_principal,
                                    causa_secundaria,solucion_secundaria,protocolo_seguridad)
                                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)''',
                                (n_dtc,n_tec,n_sin,n_cp,n_sp,n_cs,n_ss,n_prot))
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
                        with st.form("edit_form"):
                            e_dtc  = st.text_input("DTC",       value=data[1])
                            e_tec  = st.selectbox("Tecnología",
                                ["Combustión","Híbrido","Eléctrico"],
                                index=["Combustión","Híbrido","Eléctrico"].index(data[2]))
                            e_sin  = st.text_area("Síntoma",    value=data[3])
                            e_cp   = st.text_area("Causa 1",    value=data[4])
                            e_sp   = st.text_area("Solución 1", value=data[5])
                            e_cs   = st.text_area("Causa 2",    value=data[6] if data[6] else "")
                            e_ss   = st.text_area("Solución 2", value=data[7] if data[7] else "")
                            e_prot = st.text_input("Seguridad", value=data[8] if data[8] else "")
                            if st.form_submit_button("💾 Actualizar"):
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
                            conn.execute("DELETE FROM reglas_diagnostico WHERE id=%s", (id_el,))
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
                pendientes = pd.read_sql_query(
                    "SELECT * FROM casos_pendientes WHERE resuelto=0", conn)
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
                            st.balloons() # celebración visual
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
                resueltos = pd.read_sql_query(
                    "SELECT * FROM casos_pendientes WHERE resuelto=1 ORDER BY fecha DESC", conn)
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
                stats = pd.read_sql_query("SELECT * FROM estadisticas", conn)

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
                dur_prom = round(stats[col_dur].mean()) if col_dur in stats.columns else 0

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

                # — Fila 2 de gráficas: motorización + resultados por método —
                g3, g4 = st.columns(2)
                with g3:
                    fig = px.pie(stats, names=col_tec,
                        title='Por Tipo de Motorización', hole=0.45,
                        color_discrete_sequence=px.colors.qualitative.Pastel)
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
                    pass # si las fechas están mal formateadas, omitimos esta gráfica

                # — Tiempo promedio por tipo de resultado —
                if col_dur in stats.columns:
                    st.subheader("⏱️ Tiempo Promedio por Resultado")
                    dur_res = stats.groupby(col_res)[col_dur].mean().round().reset_index()
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

            # Cargamos el historial detallado (uno por diagnóstico) y las estadísticas agregadas
            with get_conn() as conn:
                hist = pd.read_sql_query(
                    "SELECT * FROM historial_diagnosticos ORDER BY fecha DESC", conn)
                stats_val = pd.read_sql_query("SELECT * FROM estadisticas", conn)

            if not hist.empty:
                # — Filtros de visualización —
                col_f1, col_f2 = st.columns(2)
                tecnicos = ["Todos"] + sorted(hist['usuario'].dropna().unique().tolist())
                tec_sel  = col_f1.selectbox("Filtrar por técnico:", tecnicos)
                rango    = col_f2.selectbox("Período:",
                    ["Hoy","Últimos 7 días","Últimos 30 días","Todo"])

                # Filtro por fecha: convertimos la columna a datetime y aplicamos el rango.
                # Usamos tz_localize(None) para evitar conflictos de timezone con SQLite,
                # que guarda los timestamps sin información de zona horaria.
                ahora = datetime.now()
                hist['fecha_dt'] = pd.to_datetime(hist['fecha'], errors='coerce')
                rangos = {"Hoy": 1, "Últimos 7 días": 7, "Últimos 30 días": 30, "Todo": 9999}
                dias   = rangos[rango]
                if dias < 9999:
                    desde = ahora - timedelta(days=dias)
                    # Comparar sin timezone
                    hist = hist[hist['fecha_dt'].dt.tz_localize(None) >= desde]
                if tec_sel != "Todos":
                    hist = hist[hist['usuario'] == tec_sel]

                st.divider()

                # — KPIs del Sprint 4 —
                total_val = len(hist)
                exito_val = int(hist['resultado'].str.contains('Acierto', na=False).sum())
                tasa_val  = round(exito_val / total_val * 100, 1) if total_val else 0
                dur_val   = 0
                if not stats_val.empty and 'duracion_seg' in stats_val.columns:
                    dur_val = round(stats_val['duracion_seg'].mean())

                k1,k2,k3,k4 = st.columns(4)
                k1.metric("Casos Evaluados",   total_val)
                k2.metric("Exitosos",          int(exito_val))
                k3.metric("Tasa de Acierto",   f"{tasa_val} %")
                k4.metric("Tiempo Promedio",   f"{dur_val}s")

                # — Barra de progreso hacia el objetivo del 70% —
                # Verde si ya se alcanzó, amarillo si aún no.
                # Este es el indicador clave de la validación del Sprint 4.
                objetivo = 70
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

                st.divider()

                # — Tabla resumen por técnico —
                # Muestra cuántos casos hizo cada uno y su tasa individual de acierto
                st.subheader("📊 Resultados por Técnico")
                por_tec = hist.groupby('usuario').agg(
                    Total=('resultado','count'),
                    Exitosos=('resultado', lambda x: int(x.str.contains('Acierto',na=False).sum()))
                ).reset_index()
                # Conversión explícita a float para evitar TypeError con pandas + Python 3.14
                por_tec['Tasa %'] = (por_tec['Exitosos'].astype(float) / por_tec['Total'].astype(float) * 100).round(1)
                st.dataframe(por_tec, use_container_width=True, height=220)

                # — Detalle caso por caso —
                st.subheader("📋 Historial Detallado")
                st.dataframe(hist.drop(columns=['fecha_dt'], errors='ignore'),
                    use_container_width=True, height=300)

                # Exportamos el historial como CSV para incluirlo en la tesis
                csv_bytes = hist.to_csv(index=False).encode('utf-8')
                st.download_button(
                    "📥 Exportar datos para tesis (CSV)",
                    data=csv_bytes,
                    file_name=f"validacion_sprint4_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv"
                )
            else:
                # Si el historial está vacío, verificamos si es por el filtro o porque no hay datos
                with get_conn() as _conn:
                    _total_hist = pd.read_sql_query("SELECT COUNT(*) as c FROM historial_diagnosticos", _conn).iloc[0]['c']
                if _total_hist > 0:
                # Hay datos pero el filtro activo los está ocultando
                    st.warning(f"⚠️ Hay **{_total_hist} diagnóstico(s)** en la BD pero el filtro actual no muestra ninguno. Cambia el período a **'Todo'** o selecciona **'Todos'** los técnicos.")
                else:
                    # La tabla realmente está vacía: nadie ha hecho diagnósticos aún
                    st.info("Aún no hay diagnósticos registrados en el historial.")
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
                                conn.execute(
                                    "INSERT INTO usuarios (usuario,password,rol) VALUES (%s,%s,%s)",
                                    (u_n, hash_pw(u_p), u_r))  # contraseña siempre hasheada
                                st.success(f"Usuario '{u_n}' creado.")
                            except sqlite3.IntegrityError:
                                # La columna 'usuario' tiene restricción UNIQUE en la BD
                                st.error("Ese usuario ya existe.")

            # — Eliminar usuario existente —
            with sub_eliminar:
                with get_conn() as conn:
                    df_usr = pd.read_sql_query("SELECT id,usuario,rol FROM usuarios", conn)
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
                                conn.execute("DELETE FROM usuarios WHERE usuario=%s", (usr_b,))
                            st.success(f"Usuario '{usr_b}' eliminado.")
                            st.rerun()
                else:
                    st.info("No hay usuarios registrados.")