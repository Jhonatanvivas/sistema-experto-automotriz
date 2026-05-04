import streamlit as st
import sqlite3
import hashlib
import time
import io
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from fpdf import FPDF
from inference_engine import MotorInferencia

# ══════════════════════════════════════════════════════════════
# CONFIGURACIÓN
# ══════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Expert-Auto Popayán",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS global — dashboard oscuro profesional
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
if 'logueado' not in st.session_state:
    st.session_state.update({
        'logueado'       : False,
        'rol'            : None,
        'user'           : None,
        # DTC
        'paso_diag'      : 0,
        'dtc_actual'     : '',
        'dtc_inicio'     : 0,       # timestamp inicio para medir duración
        # Síntomas
        'paso_sint'      : 0,
        'sint_actual'    : '',
        'sint_res'       : None,
        'sint_inicio'    : 0,
    })

motor = MotorInferencia()

# ══════════════════════════════════════════════════════════════
# UTILIDADES
# ══════════════════════════════════════════════════════════════
def hash_pw(pw): return hashlib.sha256(pw.encode()).hexdigest()

def login(u, p):
    with sqlite3.connect('conocimiento.db') as conn:
        cur = conn.cursor()
        cur.execute("SELECT rol FROM usuarios WHERE usuario=? AND password=?", (u, hash_pw(p)))
        res = cur.fetchone()
        if not res:  # compatibilidad texto plano legacy
            cur.execute("SELECT rol FROM usuarios WHERE usuario=? AND password=?", (u, p))
            res = cur.fetchone()
    return res[0] if res else None

def cargar_reglas():
    with sqlite3.connect('conocimiento.db') as conn:
        df = pd.read_sql_query(
            '''SELECT id, dtc, tipo_vehiculo, sintoma,
                      causa_principal, solucion_principal,
                      causa_secundaria, solucion_secundaria,
                      protocolo_seguridad, origen, veces_exitosa
               FROM reglas_diagnostico
               ORDER BY veces_exitosa DESC, id DESC''', conn)
    return df

def reset_sint():
    st.session_state.update({'paso_sint':0,'sint_actual':'','sint_res':None,'sint_inicio':0})

def reset_diag():
    st.session_state.update({'paso_diag':0,'dtc_actual':'','dtc_inicio':0})

def duracion_desde(ts):
    return int(time.time() - ts) if ts else 0

# ── Generador de PDF ──────────────────────────────────────────
def _pdf_texto(val) -> str:
    """Convierte cualquier valor a texto seguro para FPDF (sin None, sin caracteres raros)."""
    texto = str(val) if val is not None else "---"
    # Reemplaza caracteres que fpdf2 no puede renderizar en Helvetica
    replacements = {
        "\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"',
        "\u2013": "-", "\u2014": "-", "\u2026": "...",
    }
    for orig, rep in replacements.items():
        texto = texto.replace(orig, rep)
    return texto or "---"

def generar_pdf_diagnostico(datos: dict) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # Encabezado
    pdf.set_fill_color(30, 30, 50)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 14, "EXPERT-AUTO POPAYAN", ln=True, align="C", fill=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 8, "Reporte de Diagnostico Automotriz", ln=True, align="C", fill=True)
    pdf.ln(4)

    # Datos generales
    pdf.set_text_color(0, 0, 0)
    pdf.set_fill_color(240, 240, 250)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 9, "INFORMACION GENERAL", ln=True, fill=True)
    pdf.set_font("Helvetica", "", 10)

    campos = [
        ("Tecnico",          datos.get("usuario",    "---")),
        ("Fecha / Hora",     datos.get("fecha",      "---")),
        ("Tipo de vehiculo", datos.get("tecnologia", "---")),
        ("Metodo",           datos.get("metodo",     "---")),
        ("Entrada",          datos.get("entrada",    "---")),
        ("Duracion",         datos.get("duracion",   "---")),
    ]
    for label, val in campos:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(50, 7, f"{label}:", border=0)
        pdf.set_font("Helvetica", "", 10)
        # multi_cell ocupa toda la línea; usamos el ancho disponible (0 = hasta margen derecho)
        pdf.multi_cell(0, 7, _pdf_texto(val))

    pdf.ln(3)

    # Resultado
    pdf.set_fill_color(240, 240, 250)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 9, "RESULTADO DEL DIAGNOSTICO", ln=True, fill=True)
    pdf.set_font("Helvetica", "", 10)

    secciones = [
        ("Causa identificada",  datos.get("causa",     "---")),
        ("Solucion aplicada",   datos.get("solucion",  "---")),
        ("Protocolo seguridad", datos.get("seguridad", "---")),
        ("Conclusion",          datos.get("resultado", "---")),
    ]
    for label, val in secciones:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 7, f"{label}:", ln=True)
        pdf.set_font("Helvetica", "", 9)          # fuente más pequeña = más espacio horizontal
        pdf.set_fill_color(250, 250, 255)
        pdf.multi_cell(0, 6, _pdf_texto(val), border=1, fill=True)
        pdf.ln(2)

    # Pie
    pdf.ln(4)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 6,
        "Documento generado automaticamente por Expert-Auto Popayan | "
        "Universidad Nacional Abierta y a Distancia",
        ln=True, align="C")

    return bytes(pdf.output())

# ── Barra de confianza visual ─────────────────────────────────
def mostrar_confianza(pct: int):
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
# ══════════════════════════════════════════════════════════════
if not st.session_state.logueado:
    st.title("🛡️ Acceso al Sistema Experto Automotriz")
    col_img, col_form = st.columns([1, 1])
    with col_img:
        try:
            st.image("autosLogin.jpg", use_container_width=True)
        except:
            st.info("📷 Coloca 'autosLogin.jpg' en la raíz del proyecto")
    with col_form:
        st.markdown("### Ingresa tus credenciales")
        with st.form("login_form", clear_on_submit=True):
            u = st.text_input("👤 Usuario")
            p = st.text_input("🔒 Contraseña", type="password")
            if st.form_submit_button("Ingresar →", use_container_width=True):
                rol = login(u, p)
                if rol:
                    st.session_state.update({'logueado': True, 'rol': rol, 'user': u})
                    st.rerun()
                else:
                    st.error("Credenciales incorrectas")

# ══════════════════════════════════════════════════════════════
# INTERFAZ PRINCIPAL
# ══════════════════════════════════════════════════════════════
else:
    # ── SIDEBAR ───────────────────────────────────────────────
    with st.sidebar:
        try:
            st.image("logo_taller.png", use_container_width=True)
        except:
            st.markdown("## ⚙️ EXPERT-AUTO")
        st.divider()

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

        # Mini estadística personal en sidebar
        with sqlite3.connect('conocimiento.db') as conn:
            mis_diag = pd.read_sql_query(
                "SELECT resultado FROM estadisticas WHERE usuario=?",
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

        if st.button("🚨 Cerrar Sesión", use_container_width=True, type="primary"):
            for k in list(st.session_state.keys()):
                st.session_state.pop(k, None)
            st.rerun()

    # ── PESTAÑAS ──────────────────────────────────────────────
    if st.session_state.rol == "Administrador":
        nombres_tabs = ["🔍 Diagnóstico", "📚 Base Conocimiento", "🛠️ Resolver Reportes",
                        "📈 Estadísticas", "🎓 Dashboard Validación", "👥 Usuarios"]
    else:
        nombres_tabs = ["🔍 Diagnóstico"]

    tabs = st.tabs(nombres_tabs)

    # ══════════════════════════════════════════════════════════
    # PESTAÑA 0 — DIAGNÓSTICO
    # ══════════════════════════════════════════════════════════
    with tabs[0]:
        st.header("🔍 Motor de Inferencia")
        metodo = st.radio("Método de entrada:", ["DTC (Escáner)", "Síntomas (Texto)"], horizontal=True)
        tipo_v = st.selectbox("Motorización", ["Combustión", "Híbrido", "Eléctrico"])

        # ── DTC ───────────────────────────────────────────────
        if metodo == "DTC (Escáner)":
            codigo = st.text_input("Ingrese código DTC (ej: P0300)").upper().strip()
            c1, c2 = st.columns([1, 4])
            if c1.button("🔎 Analizar DTC"):
                st.session_state.paso_diag  = 1
                st.session_state.dtc_actual = codigo
                st.session_state.dtc_inicio = time.time()
                st.rerun()
            if c2.button("🗑️ Limpiar"):
                reset_diag(); st.rerun()

            if st.session_state.paso_diag >= 1 and st.session_state.dtc_actual:
                res = motor.consultar_por_dtc(st.session_state.dtc_actual, tipo_v)
                if res["encontrado"]:
                    st.warning(f"🛑 **SEGURIDAD:** {res['seguridad']}")

                    # PASO 1
                    if st.session_state.paso_diag == 1:
                        st.info(f"**Causa 1:** {res['causa_p']}\n\n**Solución 1:** {res['solucion_p']}")
                        col1, col2 = st.columns(2)
                        if col1.button("✅ Resolvió el problema"):
                            dur = duracion_desde(st.session_state.dtc_inicio)
                            motor.registrar_estadistica(
                                st.session_state.dtc_actual, "DTC", tipo_v,
                                "Acierto 1er Intento", st.session_state.user, dur)
                            motor.registrar_historial(
                                st.session_state.user, "DTC",
                                st.session_state.dtc_actual, tipo_v,
                                res['causa_p'], res['solucion_p'], "Acierto 1er Intento")
                            # PDF
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
                            pdf_bytes = generar_pdf_diagnostico(datos_pdf)
                            st.success("✅ Diagnóstico exitoso registrado.")
                            st.download_button(
                                "📄 Descargar Reporte PDF", data=pdf_bytes,
                                file_name=f"diagnostico_{st.session_state.dtc_actual}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                                mime="application/pdf")
                            reset_diag()

                        if col2.button("❌ No funcionó"):
                            st.session_state.paso_diag = 2; st.rerun()

                    # PASO 2
                    elif st.session_state.paso_diag == 2:
                        st.error("🔎 Ruta Secundaria de Inspección")
                        if res['causa_s']:
                            st.info(f"**Causa 2:** {res['causa_s']}\n\n**Solución 2:** {res['solucion_s']}")
                        else:
                            st.warning("No hay causa secundaria registrada.")
                        col1, col2 = st.columns(2)
                        if col1.button("✅ Resolvió (Opción 2)"):
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
                            pdf_bytes = generar_pdf_diagnostico(datos_pdf)
                            st.success("✅ Diagnóstico exitoso registrado.")
                            st.download_button(
                                "📄 Descargar Reporte PDF", data=pdf_bytes,
                                file_name=f"diagnostico_{st.session_state.dtc_actual}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                                mime="application/pdf")
                            reset_diag()

                        if col2.button("❌ Tampoco funcionó"):
                            st.session_state.paso_diag = 3; st.rerun()

                    # PASO 3 — Reporte
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
                    st.error("❌ Código DTC no encontrado en la base de datos.")

        # ── SÍNTOMAS ──────────────────────────────────────────
        else:
            sint = st.text_input("Describa la falla física (ej: 'motor pierde potencia y humo negro')")
            col_a, col_b = st.columns([1, 4])

            if col_a.button("🔎 Analizar Síntoma"):
                if sint.strip() != st.session_state.sint_actual:
                    reset_sint()
                if sint.strip():
                    resultados = motor.buscar_por_sintoma(sint, tipo_v)
                    fila = resultados[0] if resultados else None
                    if fila:
                        st.session_state.sint_res    = fila
                        st.session_state.sint_actual = sint.strip()
                        st.session_state.sint_inicio = time.time()
                        st.session_state.paso_sint   = 1
                    else:
                        st.session_state.sint_actual = sint.strip()
                        st.session_state.paso_sint   = -1
                    st.rerun()

            if col_b.button("🗑️ Limpiar"):
                reset_sint(); st.rerun()

            # Sin coincidencia
            if st.session_state.paso_sint == -1:
                st.info("Sin coincidencias en la base de datos para ese síntoma.")
                st.caption("💡 Intenta con otras palabras clave o términos del problema")
                if st.button("📤 Reportar síntoma no resuelto"):
                    motor.registrar_caso_pendiente(
                        st.session_state.sint_actual, tipo_v,
                        "Sin coincidencia en base", "Sintoma", st.session_state.user)
                    st.success("Síntoma reportado para futura investigación.")
                    reset_sint()

            # PASO 1 — causa principal
            elif st.session_state.paso_sint == 1:
                r = st.session_state.sint_res
                mostrar_confianza(r["confianza"])
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
                    pdf_bytes = generar_pdf_diagnostico(datos_pdf)
                    st.success("✅ Diagnóstico exitoso registrado.")
                    st.download_button(
                        "📄 Descargar Reporte PDF", data=pdf_bytes,
                        file_name=f"diagnostico_sint_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                        mime="application/pdf")
                    reset_sint(); st.rerun()

                if col2.button("❌ No funcionó", key="sint_no1"):
                    st.session_state.paso_sint = 2; st.rerun()

            # PASO 2 — causa secundaria
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
                    pdf_bytes = generar_pdf_diagnostico(datos_pdf)
                    st.success("✅ Diagnóstico exitoso registrado.")
                    st.download_button(
                        "📄 Descargar Reporte PDF", data=pdf_bytes,
                        file_name=f"diagnostico_sint_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                        mime="application/pdf")
                    reset_sint(); st.rerun()

                if col2.button("❌ Tampoco funcionó", key="sint_no2"):
                    st.session_state.paso_sint = 3; st.rerun()

            # PASO 3 — reporte
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
    # PESTAÑAS ADMINISTRADOR
    # ══════════════════════════════════════════════════════════
    if st.session_state.rol == "Administrador":

        # ── PESTAÑA 1 — BASE DE CONOCIMIENTO ──────────────────
        with tabs[1]:
            st.header("📚 Gestión de Base de Conocimiento")
            df = cargar_reglas()

            # Tabla con badge de origen
            st.dataframe(df, use_container_width=True, height=280)

            # Indicador rápido de reglas aprendidas
            aprendidas = len(df[df['origen'] == 'aprendizaje']) if 'origen' in df.columns else 0
            if aprendidas:
                st.info(f"🤖 **{aprendidas} regla(s) generada(s) automáticamente** por el módulo de aprendizaje")

            sub1, sub2, sub3 = st.tabs(["➕ Añadir", "✏️ Editar", "🗑️ Eliminar"])

            with sub1:
                with st.form("add_form", clear_on_submit=True):
                    c1, c2 = st.columns(2)
                    n_dtc  = c1.text_input("DTC").upper()
                    n_tec  = c1.selectbox("Tecnología", ["Combustión","Híbrido","Eléctrico"])
                    n_sin  = c2.text_area("Síntoma")
                    n_cp   = st.text_area("Causa 1")
                    n_sp   = st.text_area("Solución 1")
                    n_cs   = st.text_area("Causa 2")
                    n_ss   = st.text_area("Solución 2")
                    n_prot = st.text_input("Protocolo de Seguridad")
                    if st.form_submit_button("💾 Guardar"):
                        with sqlite3.connect('conocimiento.db') as conn:
                            conn.execute(
                                '''INSERT INTO reglas_diagnostico
                                   (dtc,tipo_vehiculo,sintoma,causa_principal,solucion_principal,
                                    causa_secundaria,solucion_secundaria,protocolo_seguridad)
                                   VALUES (?,?,?,?,?,?,?,?)''',
                                (n_dtc,n_tec,n_sin,n_cp,n_sp,n_cs,n_ss,n_prot))
                        st.success("Regla guardada."); st.rerun()

            with sub2:
                df_edit = cargar_reglas()
                if df_edit.empty:
                    st.info("No hay reglas para editar.")
                else:
                    id_ed = st.selectbox("ID a editar", df_edit['id'], key="sel_editar")
                    with sqlite3.connect('conocimiento.db') as conn:
                        cur = conn.cursor()
                        cur.execute("SELECT * FROM reglas_diagnostico WHERE id=?", (id_ed,))
                        data = cur.fetchone()
                    if data:
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

            with sub3:
                df_del = cargar_reglas()
                if not df_del.empty:
                    opciones = {
                        row['id']: f"ID {row['id']} │ {row['dtc']} │ {str(row['sintoma'])[:35]}…"
                        for _, row in df_del.iterrows()
                    }
                    id_el = st.selectbox("Regla a eliminar:",
                        options=list(opciones.keys()), format_func=lambda x: opciones[x])
                    conf = st.checkbox(f"✅ Confirmo eliminar permanentemente la regla ID {id_el}")
                    if st.button("🗑️ Eliminar", type="primary", disabled=not conf):
                        with sqlite3.connect('conocimiento.db') as conn:
                            conn.execute("DELETE FROM reglas_diagnostico WHERE id=?", (id_el,))
                        st.success(f"Regla {id_el} eliminada."); st.rerun()
                else:
                    st.info("No hay reglas registradas.")

        # ── PESTAÑA 2 — RESOLVER REPORTES + APRENDIZAJE ───────
        with tabs[2]:
            st.header("🛠️ Reportes Pendientes")
            with sqlite3.connect('conocimiento.db') as conn:
                pendientes = pd.read_sql_query(
                    "SELECT * FROM casos_pendientes WHERE resuelto=0", conn)
            st.dataframe(pendientes, use_container_width=True, height=260)

            if not pendientes.empty:
                st.divider()
                st.subheader("🤖 Resolver y Enseñar al Sistema")
                st.caption("Al completar los campos y guardar, el sistema aprende automáticamente y crea una nueva regla.")
                id_res = st.selectbox("Seleccionar reporte:", pendientes['id'])
                fila_rep = pendientes[pendientes['id'] == id_res].iloc[0]
                st.info(f"**Falla reportada:** {fila_rep['dtc_o_sintoma']}\n\n"
                        f"**Observación del mecánico:** {fila_rep['comentario_mecanico']}")

                c1, c2 = st.columns(2)
                causa_r    = c1.text_area("✏️ Causa real encontrada:")
                solucion_r = c2.text_area("✏️ Solución que funcionó:")

                col_ap, col_el = st.columns(2)
                if col_ap.button("🧠 Resolver y Enseñar al Sistema", type="primary"):
                    if causa_r and solucion_r:
                        ok = motor.resolver_caso_pendiente(int(id_res), causa_r, solucion_r)
                        if ok:
                            st.success("✅ Reporte resuelto. ¡Nueva regla añadida automáticamente a la base de conocimiento!")
                            st.balloons()
                            st.rerun()
                    else:
                        st.error("Debes completar causa y solución para enseñar al sistema.")

                if col_el.button("🗑️ Descartar sin aprender"):
                    motor.borrar_reporte_pendiente(int(id_res))
                    st.warning("Reporte descartado sin generar regla.")
                    st.rerun()

            st.divider()
            st.subheader("📋 Historial de Reportes Resueltos")
            with sqlite3.connect('conocimiento.db') as conn:
                resueltos = pd.read_sql_query(
                    "SELECT * FROM casos_pendientes WHERE resuelto=1 ORDER BY fecha DESC", conn)
            if not resueltos.empty:
                st.dataframe(resueltos, use_container_width=True, height=200)
            else:
                st.info("Aún no hay reportes resueltos.")

        # ── PESTAÑA 3 — ESTADÍSTICAS ───────────────────────────
        with tabs[3]:
            st.header("📈 Análisis de Diagnósticos")
            with sqlite3.connect('conocimiento.db') as conn:
                stats = pd.read_sql_query("SELECT * FROM estadisticas", conn)

            if not stats.empty:
                col_res = 'resultado'
                col_tip = 'tipo_diagnostico'
                col_tec = 'tecnologia'
                col_cod = 'identificador'
                col_fec = 'fecha'
                col_dur = 'duracion_seg'

                total    = len(stats)
                aciertos = int(stats[col_res].str.contains('Acierto', na=False).sum())
                fallidos = total - aciertos
                tasa     = round(aciertos / total * 100, 1) if total else 0
                dur_prom = round(stats[col_dur].mean()) if col_dur in stats.columns else 0

                # Métricas
                m1,m2,m3,m4,m5 = st.columns(5)
                m1.metric("Total Diagnósticos",   total)
                m2.metric("Exitosos",              int(aciertos))
                m3.metric("No Resueltos",          fallidos)
                m4.metric("Tasa de Éxito",         f"{tasa} %")
                m5.metric("Duración Promedio",     f"{dur_prom}s")
                st.divider()

                # Fila 1
                g1, g2 = st.columns(2)
                with g1:
                    cnt = stats[col_res].value_counts().reset_index()
                    cnt.columns = ['Resultado','Cantidad']
                    fig = px.pie(cnt, names='Resultado', values='Cantidad',
                        title='Distribución de Resultados', hole=0.45,
                        color_discrete_sequence=px.colors.qualitative.Set2)
                    st.plotly_chart(fig, use_container_width=True)
                with g2:
                    top5 = stats[col_cod].value_counts().head(5).reset_index()
                    top5.columns = ['Falla','Diagnósticos']
                    fig = px.bar(top5, x='Falla', y='Diagnósticos',
                        title='Top 5 Fallas Más Frecuentes',
                        color='Diagnósticos', color_continuous_scale='Teal')
                    st.plotly_chart(fig, use_container_width=True)

                # Fila 2
                g3, g4 = st.columns(2)
                with g3:
                    fig = px.pie(stats, names=col_tec,
                        title='Por Tipo de Motorización', hole=0.45,
                        color_discrete_sequence=px.colors.qualitative.Pastel)
                    st.plotly_chart(fig, use_container_width=True)
                with g4:
                    cross = stats.groupby([col_tip, col_res]).size().reset_index(name='Cantidad')
                    fig = px.bar(cross, x=col_tip, y='Cantidad', color=col_res,
                        barmode='group', title='Resultados por Método',
                        color_discrete_sequence=px.colors.qualitative.Set1)
                    st.plotly_chart(fig, use_container_width=True)

                # Línea temporal
                st.subheader("📅 Evolución Temporal")
                try:
                    stats['fecha_dt'] = pd.to_datetime(stats[col_fec])
                    stats['dia']      = stats['fecha_dt'].dt.date
                    por_dia = stats.groupby('dia').size().reset_index(name='Diagnósticos')
                    fig = px.line(por_dia, x='dia', y='Diagnósticos',
                        title='Diagnósticos por Día', markers=True)
                    st.plotly_chart(fig, use_container_width=True)
                except Exception:
                    pass

                # Duración promedio por resultado
                if col_dur in stats.columns:
                    st.subheader("⏱️ Tiempo Promedio por Resultado")
                    dur_res = stats.groupby(col_res)[col_dur].mean().round().reset_index()
                    dur_res.columns = ['Resultado','Segundos promedio']
                    fig = px.bar(dur_res, x='Resultado', y='Segundos promedio',
                        color='Segundos promedio', color_continuous_scale='Blues')
                    st.plotly_chart(fig, use_container_width=True)

                # Casos no resueltos
                st.subheader("🔴 Fallas Sin Resolver (más frecuentes)")
                no_res = stats[stats[col_res].str.contains('Fallo', na=False)]
                if not no_res.empty:
                    resumen = no_res[col_cod].value_counts().reset_index()
                    resumen.columns = ['Falla / Síntoma','Veces Reportada']
                    st.dataframe(resumen, use_container_width=True, height=200)
                else:
                    st.success("¡Sin casos pendientes sin resolver!")

                with st.expander("🗃️ Datos brutos"):
                    st.dataframe(stats, use_container_width=True, height=300)
            else:
                st.info("Aún no hay datos para mostrar.")

        # ── PESTAÑA 4 — DASHBOARD DE VALIDACIÓN ───────────────
        with tabs[4]:
            st.header("🎓 Dashboard de Validación — Sprint 4")
            st.caption("Vista en tiempo real para las pruebas con los 6 técnicos de Popayán")

            col_refresh, _ = st.columns([1, 4])
            if col_refresh.button("🔄 Actualizar datos", use_container_width=True):
                st.rerun()

            with sqlite3.connect('conocimiento.db') as conn:
                hist = pd.read_sql_query(
                    "SELECT * FROM historial_diagnosticos ORDER BY fecha DESC", conn)
                stats_val = pd.read_sql_query("SELECT * FROM estadisticas", conn)

            if not hist.empty:
                # Selector de técnico / fecha
                col_f1, col_f2 = st.columns(2)
                tecnicos = ["Todos"] + sorted(hist['usuario'].dropna().unique().tolist())
                tec_sel  = col_f1.selectbox("Filtrar por técnico:", tecnicos)
                rango    = col_f2.selectbox("Período:",
                    ["Hoy","Últimos 7 días","Últimos 30 días","Todo"])

                # Filtro fecha
                ahora = datetime.now()
                rangos = {"Hoy": 0, "Últimos 7 días": 7, "Últimos 30 días": 30, "Todo": 9999}
                dias   = rangos[rango]
                hist['fecha_dt'] = pd.to_datetime(hist['fecha'])
                if dias < 9999:
                    desde = ahora - timedelta(days=dias)
                    hist  = hist[hist['fecha_dt'] >= desde]
                if tec_sel != "Todos":
                    hist = hist[hist['usuario'] == tec_sel]

                st.divider()

                # KPIs de validación
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

                # Objetivo del Sprint 4
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

                # Tabla de resultados por técnico
                st.subheader("📊 Resultados por Técnico")
                por_tec = hist.groupby('usuario').agg(
                    Total=('resultado','count'),
                    Exitosos=('resultado', lambda x: int(x.str.contains('Acierto',na=False).sum()))
                ).reset_index()
                por_tec['Tasa %'] = (por_tec['Exitosos'].astype(float) / por_tec['Total'].astype(float) * 100).round(1)
                st.dataframe(por_tec, use_container_width=True, height=220)

                # Historial detallado
                st.subheader("📋 Historial Detallado")
                st.dataframe(hist.drop(columns=['fecha_dt'], errors='ignore'),
                    use_container_width=True, height=300)

                # Exportar CSV para la tesis
                csv_bytes = hist.to_csv(index=False).encode('utf-8')
                st.download_button(
                    "📥 Exportar datos para tesis (CSV)",
                    data=csv_bytes,
                    file_name=f"validacion_sprint4_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv"
                )
            else:
                st.info("Aún no hay diagnósticos registrados en el historial.")
                st.caption("Los diagnósticos aparecen aquí automáticamente cuando los técnicos usen el sistema.")

        # ── PESTAÑA 5 — USUARIOS ───────────────────────────────
        with tabs[5]:
            st.header("👥 Gestión de Usuarios")
            sub_crear, sub_eliminar = st.tabs(["➕ Crear Usuario", "🗑️ Eliminar Usuario"])

            with sub_crear:
                with st.form("crear_u", clear_on_submit=True):
                    c1,c2,c3 = st.columns(3)
                    u_n = c1.text_input("Nombre de usuario")
                    u_p = c2.text_input("Contraseña", type="password")
                    u_r = c3.selectbox("Rol", ["Mecanico","Administrador"])
                    if st.form_submit_button("Crear"):
                        with sqlite3.connect('conocimiento.db') as conn:
                            try:
                                conn.execute(
                                    "INSERT INTO usuarios (usuario,password,rol) VALUES (?,?,?)",
                                    (u_n, hash_pw(u_p), u_r))
                                st.success(f"Usuario '{u_n}' creado.")
                            except sqlite3.IntegrityError:
                                st.error("Ese usuario ya existe.")

            with sub_eliminar:
                with sqlite3.connect('conocimiento.db') as conn:
                    df_usr = pd.read_sql_query("SELECT id,usuario,rol FROM usuarios", conn)
                st.dataframe(df_usr, use_container_width=True, height=220)
                if not df_usr.empty:
                    usr_b = st.selectbox("Usuario a eliminar", df_usr['usuario'])
                    conf_u = st.checkbox(f"✅ Confirmo eliminar al usuario '{usr_b}' permanentemente")
                    if st.button("🚨 Eliminar Usuario", type="primary", disabled=not conf_u):
                        if usr_b == st.session_state.user:
                            st.error("No puedes eliminar tu propia cuenta activa.")
                        else:
                            with sqlite3.connect('conocimiento.db') as conn:
                                conn.execute("DELETE FROM usuarios WHERE usuario=?", (usr_b,))
                            st.success(f"Usuario '{usr_b}' eliminado.")
                            st.rerun()
                else:
                    st.info("No hay usuarios registrados.")