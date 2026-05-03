import streamlit as st
import sqlite3
import hashlib
import pandas as pd
import plotly.express as px
from inference_engine import MotorInferencia

# ══════════════════════════════════════════════════════════════
# CONFIGURACIÓN INICIAL
# ══════════════════════════════════════════════════════════════
st.set_page_config(page_title="Expert-Auto Popayán", page_icon="⚙️", layout="wide")

# Estado de sesión — se inicializa UNA sola vez
if 'logueado' not in st.session_state:
    st.session_state.update({
        'logueado'    : False,
        'rol'         : None,
        'user'        : None,
        # DTC
        'paso_diag'   : 0,
        'dtc_actual'  : '',
        # Síntomas — mismo esquema de pasos que DTC
        'paso_sint'   : 0,    # 0=inactivo  1=causa1  2=causa2  3=reporte  -1=sin coincidencia
        'sint_actual' : '',   # texto buscado, para detectar si el usuario lo cambió
        'sint_res'    : None  # fila de BD guardada en sesión
    })

motor = MotorInferencia()

# ══════════════════════════════════════════════════════════════
# UTILIDADES
# ══════════════════════════════════════════════════════════════
def hash_pw(pw: str) -> str:
    """SHA-256. Para producción con muchos usuarios considera bcrypt."""
    return hashlib.sha256(pw.encode()).hexdigest()

def login(u, p):
    """Intenta login con hash; si no, con texto plano (compatibilidad)."""
    with sqlite3.connect('conocimiento.db') as conn:
        cur = conn.cursor()
        cur.execute("SELECT rol FROM usuarios WHERE usuario=? AND password=?", (u, hash_pw(p)))
        res = cur.fetchone()
        if not res:
            cur.execute("SELECT rol FROM usuarios WHERE usuario=? AND password=?", (u, p))
            res = cur.fetchone()
    return res[0] if res else None

def cargar_reglas():
    """Siempre lee la BD fresca, sin caché."""
    with sqlite3.connect('conocimiento.db') as conn:
        df = pd.read_sql_query(
            "SELECT id, dtc, tipo_vehiculo, sintoma, causa_principal FROM reglas_diagnostico", conn
        )
    return df

def reset_sint():
    st.session_state.update({'paso_sint': 0, 'sint_actual': '', 'sint_res': None})

def reset_diag():
    st.session_state.update({'paso_diag': 0, 'dtc_actual': ''})

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
            st.warning("Imagen 'autosLogin.jpg' no encontrada.")
            st.info("💡 Verifica mayúsculas en la extensión (.jpg / .JPG)")

    with col_form:
        with st.form("login_form", clear_on_submit=True):
            u = st.text_input("Usuario")
            p = st.text_input("Contraseña", type="password")
            if st.form_submit_button("Ingresar"):
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
    # ── BARRA LATERAL ─────────────────────────────────────────
    with st.sidebar:
        try:
            st.image("logo_taller.png", use_container_width=True)
        except:
            st.write("### EXPERT-AUTO")

        st.divider()
        st.markdown(f"""
        <div style='background-color:#1E1E1E;padding:20px;border-radius:10px;
                    text-align:center;border:1px solid #4CAF50;'>
            <h2 style='margin-bottom:5px;color:#4CAF50;'>🧑‍🔧 Perfil Técnico</h2>
            <p style='margin-bottom:2px;font-size:16px;'><b>Usuario:</b> {st.session_state.user}</p>
            <p style='margin-bottom:2px;font-size:16px;'><b>Rango:</b> {st.session_state.rol}</p>
            <p style='margin-bottom:15px;font-size:12px;color:#888;'>Sede: Popayán</p>
        </div>
        """, unsafe_allow_html=True)

        st.write("")
        if st.button("🚨 Cerrar Sesión", use_container_width=True, type="primary"):
            for k in ['logueado','rol','user','paso_diag','dtc_actual',
                      'paso_sint','sint_actual','sint_res']:
                st.session_state.pop(k, None)
            st.rerun()

    # ── PESTAÑAS ──────────────────────────────────────────────
    if st.session_state.rol == "Administrador":
        nombres_tabs = ["🔍 Diagnóstico", "📚 Base Conocimiento",
                        "🛠️ Resolver Reportes", "📈 Estadísticas", "👥 Usuarios"]
    else:
        nombres_tabs = ["🔍 Diagnóstico"]

    tabs = st.tabs(nombres_tabs)

    # ══════════════════════════════════════════════════════════
    # PESTAÑA 0 — DIAGNÓSTICO
    # ══════════════════════════════════════════════════════════
    with tabs[0]:
        st.header("Motor de Inferencia")
        metodo = st.radio("Método de entrada:", ["DTC (Escáner)", "Síntomas (Texto)"], horizontal=True)
        tipo_v = st.selectbox("Motorización", ["Combustión", "Híbrido", "Eléctrico"])

        # ─────────────────────────────────────────────────────
        # BLOQUE DTC
        # ─────────────────────────────────────────────────────
        if metodo == "DTC (Escáner)":
            codigo = st.text_input("Ingrese código DTC").upper().strip()
            c1, c2 = st.columns([1, 4])

            if c1.button("Analizar DTC"):
                st.session_state.paso_diag  = 1
                st.session_state.dtc_actual = codigo
                st.rerun()
            if c2.button("Limpiar DTC"):
                reset_diag()
                st.rerun()

            if st.session_state.paso_diag >= 1 and st.session_state.dtc_actual:
                res = motor.consultar_por_dtc(st.session_state.dtc_actual, tipo_v)
                if res["encontrado"]:
                    st.warning(f"🛑 SEGURIDAD: {res['seguridad']}")

                    # PASO 1 — causa principal
                    if st.session_state.paso_diag == 1:
                        st.info(f"**Causa 1:** {res['causa_p']}\n\n**Solución 1:** {res['solucion_p']}")
                        col1, col2 = st.columns(2)
                        if col1.button("✅ Resolvió el problema"):
                            motor.registrar_estadistica(
                                st.session_state.dtc_actual, "DTC", tipo_v, "Acierto 1er Intento")
                            st.success("Diagnóstico exitoso registrado.")
                            reset_diag()
                        if col2.button("❌ No funcionó"):
                            st.session_state.paso_diag = 2
                            st.rerun()

                    # PASO 2 — causa secundaria
                    elif st.session_state.paso_diag == 2:
                        st.error("🔎 Ruta Secundaria de Inspección")
                        if res['causa_s']:
                            st.info(f"**Causa 2:** {res['causa_s']}\n\n**Solución 2:** {res['solucion_s']}")
                        else:
                            st.warning("No hay causa secundaria registrada para este código.")
                        col1, col2 = st.columns(2)
                        if col1.button("✅ Resolvió (Opción 2)"):
                            motor.registrar_estadistica(
                                st.session_state.dtc_actual, "DTC", tipo_v, "Acierto 2do Intento")
                            st.success("Diagnóstico exitoso registrado.")
                            reset_diag()
                        if col2.button("❌ Tampoco funcionó"):
                            st.session_state.paso_diag = 3
                            st.rerun()

                    # PASO 3 — reporte
                    elif st.session_state.paso_diag == 3:
                        st.warning("⚠️ Se agotaron las soluciones. Envía el caso al experto.")
                        obs = st.text_area("Describe el problema con detalle:")
                        if st.button("📤 Enviar Reporte"):
                            motor.registrar_caso_pendiente(
                                st.session_state.dtc_actual, tipo_v, obs, "DTC")
                            st.success("Reporte enviado correctamente.")
                            reset_diag()
                else:
                    st.error("Código DTC no encontrado en la base de datos.")

        # ─────────────────────────────────────────────────────
        # BLOQUE SÍNTOMAS — flujo idéntico a DTC
        # ─────────────────────────────────────────────────────
        else:
            sint = st.text_input("Describa la falla física")
            col_a, col_b = st.columns([1, 4])

            if col_a.button("Analizar Síntoma"):
                # Si el texto cambió, reiniciamos el flujo
                if sint.strip() != st.session_state.sint_actual:
                    reset_sint()

                if sint.strip():
                    resultado = motor.buscar_por_sintoma(sint, tipo_v)
                    # Normalizamos: puede devolver lista o fila directa
                    if isinstance(resultado, list):
                        fila = resultado[0] if resultado else None
                    else:
                        fila = resultado

                    if fila:
                        st.session_state.sint_res    = fila
                        st.session_state.sint_actual = sint.strip()
                        st.session_state.paso_sint   = 1
                    else:
                        st.session_state.sint_actual = sint.strip()
                        st.session_state.paso_sint   = -1
                    st.rerun()

            if col_b.button("Limpiar Síntoma"):
                reset_sint()
                st.rerun()

            # Sin coincidencia
            if st.session_state.paso_sint == -1:
                st.info("Sin coincidencias en la base de datos para ese síntoma.")
                if st.button("📤 Reportar síntoma no resuelto"):
                    motor.registrar_caso_pendiente(
                        st.session_state.sint_actual, tipo_v,
                        "Sin coincidencia en base de datos", "Sintoma")
                    st.success("Síntoma reportado para futura investigación.")
                    reset_sint()

            # PASO 1 — causa principal
            elif st.session_state.paso_sint == 1:
                r = st.session_state.sint_res
                # Índices de la tupla (ajusta si tu SELECT devuelve otro orden):
                # 0=dtc, 1=sintoma, 2=causa_principal, 3=solucion_principal,
                # 4=causa_secundaria, 5=solucion_secundaria, 6=protocolo_seguridad
                seguridad = r[6] if len(r) > 6 and r[6] else "Sigue los protocolos estándar"
                st.warning(f"🛑 SEGURIDAD: {seguridad}")
                st.info(f"**Causa 1:** {r[2]}\n\n**Solución 1:** {r[3]}")

                col1, col2 = st.columns(2)
                if col1.button("✅ Resolvió el problema", key="sint_ok1"):
                    motor.registrar_estadistica(
                        st.session_state.sint_actual, "Sintoma", tipo_v, "Acierto 1er Intento")
                    st.success("Diagnóstico exitoso registrado.")
                    reset_sint()
                    st.rerun()
                if col2.button("❌ No funcionó", key="sint_no1"):
                    st.session_state.paso_sint = 2
                    st.rerun()

            # PASO 2 — causa secundaria
            elif st.session_state.paso_sint == 2:
                r = st.session_state.sint_res
                st.error("🔎 Ruta Secundaria de Inspección")
                causa_s    = r[4] if len(r) > 4 and r[4] else None
                solucion_s = r[5] if len(r) > 5 and r[5] else None

                if causa_s:
                    st.info(f"**Causa 2:** {causa_s}\n\n**Solución 2:** {solucion_s}")
                else:
                    st.warning("No hay causa secundaria registrada. "
                               "Puedes agregarla en Base de Conocimiento → Editar.")

                col1, col2 = st.columns(2)
                if col1.button("✅ Resolvió (Opción 2)", key="sint_ok2"):
                    motor.registrar_estadistica(
                        st.session_state.sint_actual, "Sintoma", tipo_v, "Acierto 2do Intento")
                    st.success("Diagnóstico exitoso registrado.")
                    reset_sint()
                    st.rerun()
                if col2.button("❌ Tampoco funcionó", key="sint_no2"):
                    st.session_state.paso_sint = 3
                    st.rerun()

            # PASO 3 — reporte al experto
            elif st.session_state.paso_sint == 3:
                st.warning("⚠️ Se agotaron las soluciones. Envía el caso al experto.")
                obs = st.text_area("Añade una observación detallada del caso:")
                if st.button("📤 Enviar Reporte a Experto"):
                    motor.registrar_caso_pendiente(
                        st.session_state.sint_actual, tipo_v, obs, "Sintoma")
                    st.success("Reporte enviado. ¡Gracias por la retroalimentación!")
                    reset_sint()
                    st.rerun()

    # ══════════════════════════════════════════════════════════
    # PESTAÑAS ADMINISTRADOR
    # ══════════════════════════════════════════════════════════
    if st.session_state.rol == "Administrador":

        # ── PESTAÑA 1 — BASE DE CONOCIMIENTO ──────────────────
        with tabs[1]:
            st.header("Gestión de Base de Conocimiento")
            df = cargar_reglas()
            st.dataframe(df, use_container_width=True, height=280)

            sub1, sub2, sub3 = st.tabs(["➕ Añadir", "✏️ Editar", "🗑️ Eliminar"])

            # ── AÑADIR ────────────────────────────────────────
            with sub1:
                with st.form("add_form", clear_on_submit=True):
                    c1, c2 = st.columns(2)
                    n_dtc  = c1.text_input("DTC").upper()
                    n_tec  = c1.selectbox("Tecnología", ["Combustión", "Híbrido", "Eléctrico"])
                    n_sin  = c2.text_area("Síntoma")
                    n_cp   = st.text_area("Causa 1")
                    n_sp   = st.text_area("Solución 1")
                    n_cs   = st.text_area("Causa 2")
                    n_ss   = st.text_area("Solución 2")
                    n_prot = st.text_input("Protocolo de Seguridad")
                    if st.form_submit_button("💾 Guardar"):
                        with sqlite3.connect('conocimiento.db') as conn:
                            conn.execute(
                                'INSERT INTO reglas_diagnostico '
                                '(dtc,tipo_vehiculo,sintoma,causa_principal,solucion_principal,'
                                'causa_secundaria,solucion_secundaria,protocolo_seguridad) '
                                'VALUES (?,?,?,?,?,?,?,?)',
                                (n_dtc, n_tec, n_sin, n_cp, n_sp, n_cs, n_ss, n_prot)
                            )
                        st.success("Regla guardada correctamente.")
                        st.rerun()   # actualiza tabla y selectores en vivo

            # ── EDITAR ────────────────────────────────────────
            # BUG 2 FIX: se eliminó el botón "Restaurar/Limpiar".
            # Al presionar "Actualizar", st.rerun() recarga el form
            # con los valores frescos de la BD, limpiando cualquier edición.
            with sub2:
                df_edit = cargar_reglas()
                if df_edit.empty:
                    st.info("No hay reglas para editar.")
                else:
                    id_ed = st.selectbox(
                        "Selecciona el ID a editar",
                        df_edit['id'],
                        key="sel_editar"
                    )
                    with sqlite3.connect('conocimiento.db') as conn:
                        cur = conn.cursor()
                        cur.execute("SELECT * FROM reglas_diagnostico WHERE id=?", (id_ed,))
                        data = cur.fetchone()

                    if data:
                        with st.form("edit_form"):
                            e_dtc  = st.text_input("DTC",        value=data[1])
                            e_tec  = st.selectbox(
                                "Tecnología",
                                ["Combustión", "Híbrido", "Eléctrico"],
                                index=["Combustión","Híbrido","Eléctrico"].index(data[2])
                            )
                            e_sin  = st.text_area("Síntoma",     value=data[3])
                            e_cp   = st.text_area("Causa 1",     value=data[4])
                            e_sp   = st.text_area("Solución 1",  value=data[5])
                            e_cs   = st.text_area("Causa 2",     value=data[6] if data[6] else "")
                            e_ss   = st.text_area("Solución 2",  value=data[7] if data[7] else "")
                            e_prot = st.text_input("Seguridad",  value=data[8] if data[8] else "")

                            if st.form_submit_button("💾 Actualizar"):
                                motor.actualizar_regla(
                                    id_ed, e_dtc, e_tec, e_sin,
                                    e_cp, e_sp, e_cs, e_ss, e_prot
                                )
                                st.success("✅ Regla actualizada correctamente.")
                                st.rerun()  # recarga el form con valores nuevos de la BD

            # ── ELIMINAR ──────────────────────────────────────
            with sub3:
                st.write("### Eliminar Regla de Conocimiento")
                df_del = cargar_reglas()
                if not df_del.empty:
                    opciones = {
                        row['id']: f"ID {row['id']} │ DTC: {row['dtc']} │ {row['sintoma'][:40]}…"
                        for _, row in df_del.iterrows()
                    }
                    id_eliminar = st.selectbox(
                        "Selecciona la regla a eliminar:",
                        options=list(opciones.keys()),
                        format_func=lambda x: opciones[x]
                    )
                    # MEJORA: checkbox de confirmación — botón deshabilitado hasta confirmar
                    confirmar = st.checkbox(
                        f"✅ Confirmo que quiero eliminar permanentemente la regla ID {id_eliminar}"
                    )
                    if st.button("🗑️ Eliminar Regla", type="primary", disabled=not confirmar):
                        with sqlite3.connect('conocimiento.db') as conn:
                            conn.execute(
                                "DELETE FROM reglas_diagnostico WHERE id=?", (id_eliminar,)
                            )
                        st.success(f"Regla ID {id_eliminar} eliminada.")
                        st.rerun()
                else:
                    st.info("No hay reglas registradas en el sistema.")

        # ── PESTAÑA 2 — RESOLVER REPORTES ─────────────────────
        with tabs[2]:
            st.header("Reportes Pendientes")
            with sqlite3.connect('conocimiento.db') as conn:
                pendientes = pd.read_sql_query("SELECT * FROM casos_pendientes", conn)
            st.dataframe(pendientes, use_container_width=True, height=300)
            if not pendientes.empty:
                id_res = st.selectbox("Seleccionar reporte a cerrar", pendientes['id'])
                if st.button("✅ Marcar como Resuelto"):
                    motor.borrar_reporte_pendiente(int(id_res))
                    st.success("Reporte cerrado.")
                    st.rerun()

        # ── PESTAÑA 3 — ESTADÍSTICAS ───────────────────────────
        with tabs[3]:
            st.header("📊 Análisis Profundo de Diagnósticos")
            with sqlite3.connect('conocimiento.db') as conn:
                stats = pd.read_sql_query("SELECT * FROM estadisticas", conn)

            if not stats.empty:
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Total Diagnósticos Realizados", len(stats))
                with col2:
                    col_res  = 'resultado' if 'resultado' in stats.columns else stats.columns[-1]
                    aciertos = stats[col_res].astype(str).str.contains(
                        'Acierto', case=False, na=False).sum()
                    st.metric("Total Diagnósticos Exitosos", int(aciertos))

                c1, c2 = st.columns(2)
                with c1:
                    if 'tipo_vehiculo' in stats.columns:
                        fig1 = px.pie(
                            stats, names='tipo_vehiculo',
                            title='Diagnósticos por Tipo de Motorización', hole=0.3
                        )
                        st.plotly_chart(fig1, use_container_width=True)
                with c2:
                    col_cod = 'codigo_sintoma' if 'codigo_sintoma' in stats.columns else stats.columns[1]
                    top5    = stats[col_cod].value_counts().head(5).reset_index()
                    top5.columns = ['Falla', 'Cantidad']
                    fig2 = px.bar(top5, x='Falla', y='Cantidad',
                                  title='Top 5 Fallas / DTC Más Recurrentes')
                    st.plotly_chart(fig2, use_container_width=True)

                st.subheader("Datos completos")
                st.dataframe(stats, use_container_width=True, height=300)
            else:
                st.info("Aún no hay datos para mostrar estadísticas.")

        # ── PESTAÑA 4 — USUARIOS ───────────────────────────────
        with tabs[4]:
            st.header("Gestión de Usuarios")
            sub_crear, sub_eliminar = st.tabs(["➕ Crear Usuario", "🗑️ Eliminar Usuario"])

            with sub_crear:
                with st.form("crear_u", clear_on_submit=True):
                    c1, c2, c3 = st.columns(3)
                    u_n = c1.text_input("Nombre de usuario")
                    u_p = c2.text_input("Contraseña", type="password")
                    u_r = c3.selectbox("Rol", ["Mecanico", "Administrador"])
                    if st.form_submit_button("Crear"):
                        with sqlite3.connect('conocimiento.db') as conn:
                            try:
                                # MEJORA: contraseña guardada con hash SHA-256
                                conn.execute(
                                    "INSERT INTO usuarios (usuario, password, rol) VALUES (?,?,?)",
                                    (u_n, hash_pw(u_p), u_r)
                                )
                                st.success(f"Usuario '{u_n}' creado correctamente.")
                            except sqlite3.IntegrityError:
                                st.error("Error: ese nombre de usuario ya existe.")

            with sub_eliminar:
                with sqlite3.connect('conocimiento.db') as conn:
                    df_usr = pd.read_sql_query("SELECT id, usuario, rol FROM usuarios", conn)
                st.dataframe(df_usr, use_container_width=True, height=250)

                if not df_usr.empty:
                    usr_borrar = st.selectbox("Usuario a eliminar", df_usr['usuario'])
                    # MEJORA: confirmación antes de borrar
                    confirmar_usr = st.checkbox(
                        f"✅ Confirmo que quiero eliminar al usuario '{usr_borrar}' permanentemente"
                    )
                    if st.button("🚨 Eliminar Usuario", type="primary", disabled=not confirmar_usr):
                        if usr_borrar == st.session_state.user:
                            st.error("No puedes eliminar tu propia cuenta mientras está activa.")
                        else:
                            with sqlite3.connect('conocimiento.db') as conn:
                                conn.execute(
                                    "DELETE FROM usuarios WHERE usuario=?", (usr_borrar,)
                                )
                            st.success(f"Usuario '{usr_borrar}' eliminado.")
                            st.rerun()
                else:
                    st.info("No hay usuarios registrados.")