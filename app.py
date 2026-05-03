import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
from inference_engine import MotorInferencia

# Configuración inicial de la página
st.set_page_config(page_title="Expert-Auto Popayán", page_icon="⚙️", layout="wide")

# Inicialización de estados de sesión
if 'logueado' not in st.session_state:
    st.session_state.update({
        'logueado': False,
        'rol': None,
        'user': None,
        'paso_diag': 0,
        'paso_sintoma': 0,
        'indice_sintoma': 0,
        'ultimo_sint': ''      # FIX BUG 1: guardamos el texto buscado para detectar cambios
    })

motor = MotorInferencia()

def login(u, p):
    conn = sqlite3.connect('conocimiento.db')
    cur = conn.cursor()
    cur.execute("SELECT rol FROM usuarios WHERE usuario=? AND password=?", (u, p))
    res = cur.fetchone()
    conn.close()
    return res[0] if res else None

# FIX BUG 3: función centralizada para leer la BD siempre fresca (sin caché)
def cargar_reglas():
    conn = sqlite3.connect('conocimiento.db')
    df = pd.read_sql_query(
        "SELECT id, dtc, tipo_vehiculo, sintoma, causa_principal FROM reglas_diagnostico", conn
    )
    conn.close()
    return df

# --- PANTALLA DE LOGIN ---
if not st.session_state.logueado:
    st.title("🛡️ Acceso al Sistema Experto Automotriz")
    col_img, col_form = st.columns([1, 1])
    with col_img:
        try:
            st.image("autosLogin.jpg", use_container_width=True)
        except:
            st.warning("Imagen 'autosLogin.jpg' no encontrada en la raíz del proyecto.")
            st.info("💡 Consejo: Verifica que el nombre no tenga mayúsculas diferentes (ej: .JPG vs .jpg)")

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

# --- INTERFAZ PRINCIPAL (LOGUEADO) ---
else:
    # --- BARRA LATERAL ---
    with st.sidebar:
        try:
            st.image("logo_taller.png", use_container_width=True)
        except:
            st.write("### EXPERT-AUTO")

        st.divider()

        st.markdown(f"""
        <div style='background-color: #1E1E1E; padding: 20px; border-radius: 10px; text-align: center; border: 1px solid #4CAF50;'>
            <h2 style='margin-bottom: 5px; color: #4CAF50;'>🧑‍🔧 Perfil Técnico</h2>
            <p style='margin-bottom: 2px; font-size: 16px;'><b>Usuario:</b> {st.session_state.user}</p>
            <p style='margin-bottom: 2px; font-size: 16px;'><b>Rango:</b> {st.session_state.rol}</p>
            <p style='margin-bottom: 15px; font-size: 12px; color: #888888;'>Sede: Popayán</p>
        </div>
        """, unsafe_allow_html=True)

        st.write("")
        if st.button("🚨 Cerrar Sesión", use_container_width=True, type="primary"):
            st.session_state.update({
                'logueado': False, 'rol': None,
                'paso_diag': 0, 'paso_sintoma': 0,
                'indice_sintoma': 0, 'ultimo_sint': ''
            })
            st.rerun()

    # --- PESTAÑAS ---
    if st.session_state.rol == "Administrador":
        nombres_tabs = ["🔍 Diagnóstico", "📚 Base Conocimiento", "🛠️ Resolver Reportes", "📈 Matriz Estadísticas", "👥 Usuarios"]
    else:
        nombres_tabs = ["🔍 Diagnóstico"]

    tabs = st.tabs(nombres_tabs)

    # ═══════════════════════════════════════════════════════════
    # PESTAÑA 0: DIAGNÓSTICO
    # ═══════════════════════════════════════════════════════════
    with tabs[0]:
        st.header("Motor de Inferencia")
        metodo = st.radio("Método de entrada:", ["DTC (Escáner)", "Síntomas (Texto)"], horizontal=True)
        tipo_v = st.selectbox("Motorización", ["Combustión", "Híbrido", "Eléctrico"])

        # ── DTC ──────────────────────────────────────────────────
        if metodo == "DTC (Escáner)":
            codigo = st.text_input("Ingrese código DTC").upper().strip()
            c1, c2 = st.columns([1, 4])
            if c1.button("Analizar DTC"):
                st.session_state.paso_diag = 1
            if c2.button("Limpiar"):
                st.session_state.paso_diag = 0
                st.rerun()

            if st.session_state.paso_diag >= 1 and codigo:
                res = motor.consultar_por_dtc(codigo, tipo_v)
                if res["encontrado"]:
                    st.warning(f"🛑 SEGURIDAD: {res['seguridad']}")
                    if st.session_state.paso_diag == 1:
                        st.info(f"**Causa Probable 1:** {res['causa_p']}\n\n**Solución 1:** {res['solucion_p']}")
                        col1, col2 = st.columns(2)
                        if col1.button("✅ Resolvió el problema"):
                            motor.registrar_estadistica(codigo, "DTC", tipo_v, "Acierto 1er Intento")
                            st.success("Registrado.")
                            st.session_state.paso_diag = 0
                        if col2.button("❌ No funcionó"):
                            st.session_state.paso_diag = 2
                            st.rerun()
                    elif st.session_state.paso_diag == 2:
                        st.error("Ruta Secundaria de Inspección")
                        if res['causa_s']:
                            st.info(f"**Causa 2:** {res['causa_s']}\n\n**Solución 2:** {res['solucion_s']}")
                        else:
                            st.warning("No hay alternativa secundaria. Reporte al experto.")
                        col1, col2 = st.columns(2)
                        if col1.button("✅ Resolvió (Opción 2)"):
                            motor.registrar_estadistica(codigo, "DTC", tipo_v, "Acierto 2do Intento")
                            st.success("Registrado.")
                            st.session_state.paso_diag = 0
                        if col2.button("Tampoco funcionó"):
                            st.session_state.paso_diag = 3
                            st.rerun()
                    elif st.session_state.paso_diag == 3:
                        obs = st.text_area("Detalle el problema para el administrador:")
                        if st.button("Enviar Reporte"):
                            motor.registrar_caso_pendiente(codigo, tipo_v, obs, "DTC")
                            st.success("Fallo registrado.")
                            st.session_state.paso_diag = 0
                else:
                    st.error("Código no encontrado.")

        # ── SÍNTOMAS ─────────────────────────────────────────────
        else:
            sint = st.text_input("Describa la falla física")

            col_a, col_b = st.columns([1, 4])
            if col_a.button("Analizar Síntoma"):
                # FIX BUG 1: al iniciar nueva búsqueda siempre reseteamos el índice
                st.session_state.paso_sintoma = 1
                st.session_state.indice_sintoma = 0
                st.session_state.ultimo_sint = sint   # guardamos el texto actual

            if col_b.button("Limpiar Síntoma"):
                st.session_state.paso_sintoma = 0
                st.session_state.indice_sintoma = 0
                st.session_state.ultimo_sint = ''
                st.rerun()

            # FIX BUG 1: si el usuario cambia el texto sin pulsar "Analizar" de nuevo,
            # reseteamos para evitar que el índice viejo cause el warning falso
            if sint != st.session_state.ultimo_sint and st.session_state.paso_sintoma == 1:
                st.session_state.paso_sintoma = 0
                st.session_state.indice_sintoma = 0

            if st.session_state.paso_sintoma == 1 and sint:
                resultados = motor.buscar_por_sintoma(sint, tipo_v)

                if resultados:
                    indice = st.session_state.indice_sintoma

                    if indice < len(resultados):
                        r = resultados[indice]

                        st.info(f"💡 Posible Solución {indice + 1} de {len(resultados)}")
                        st.write(f"**Relacionado con DTC:** {r[0]}")
                        st.write(f"**Causa:** {r[2]}")
                        st.write(f"**Solución:** {r[3]}")

                        c1, c2 = st.columns(2)
                        if c1.button("✅ Resolvió el problema", key=f"btn_si_{indice}"):
                            motor.registrar_estadistica(sint, "Sintoma", tipo_v, "Acierto")
                            st.success("Diagnóstico exitoso guardado.")
                            st.session_state.paso_sintoma = 0
                            st.session_state.indice_sintoma = 0
                            st.session_state.ultimo_sint = ''
                            st.rerun()

                        if c2.button("❌ No funcionó", key=f"btn_no_{indice}"):
                            st.session_state.indice_sintoma += 1
                            st.rerun()
                    else:
                        # Se agotaron todas las opciones
                        st.warning("⚠️ Se agotaron las soluciones en la base de datos para este síntoma.")
                        obs = st.text_area("Añade una observación detallada del caso:")
                        if st.button("Enviar Reporte a Experto"):
                            motor.registrar_caso_pendiente(sint, tipo_v, obs, "Sintoma")
                            st.success("Reporte enviado. ¡Gracias por la retroalimentación!")
                            st.session_state.paso_sintoma = 0
                            st.session_state.indice_sintoma = 0
                            st.session_state.ultimo_sint = ''
                else:
                    st.info("Sin coincidencias en la base de datos.")
                    if st.button("Reportar Síntoma no resuelto"):
                        motor.registrar_caso_pendiente(sint, tipo_v, "No hay coincidencia en base", "Sintoma")
                        st.success("Síntoma reportado para futura investigación.")

    # ═══════════════════════════════════════════════════════════
    # PESTAÑAS SÓLO ADMINISTRADOR
    # ═══════════════════════════════════════════════════════════
    if st.session_state.rol == "Administrador":

        # ── PESTAÑA 1: BASE DE CONOCIMIENTO ─────────────────────
        with tabs[1]:
            st.header("Gestión de Base de Conocimiento")

            # FIX BUG 3: cargamos el df siempre fresco aquí dentro del tab,
            # no una sola vez al principio del script
            df = cargar_reglas()
            st.dataframe(df, use_container_width=True)

            sub1, sub2, sub3 = st.tabs(["➕ Añadir", "✏️ Editar", "🗑️ Eliminar"])

            # ── AÑADIR ───────────────────────────────────────────
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
                    n_prot = st.text_input("Seguridad")
                    if st.form_submit_button("Guardar"):
                        conn = sqlite3.connect('conocimiento.db')
                        cur = conn.cursor()
                        cur.execute(
                            'INSERT INTO reglas_diagnostico '
                            '(dtc,tipo_vehiculo,sintoma,causa_principal,solucion_principal,'
                            'causa_secundaria,solucion_secundaria,protocolo_seguridad) '
                            'VALUES (?,?,?,?,?,?,?,?)',
                            (n_dtc, n_tec, n_sin, n_cp, n_sp, n_cs, n_ss, n_prot)
                        )
                        conn.commit()
                        conn.close()
                        st.success("Guardado.")
                        # FIX BUG 4: rerun para que el df del selector de edición se actualice
                        st.rerun()

            # ── EDITAR ───────────────────────────────────────────
            with sub2:
                # FIX BUG 3: recargamos la lista siempre fresca para el selectbox
                df_edit = cargar_reglas()

                col_sel, col_limpiar = st.columns([3, 1])
                id_ed = col_sel.selectbox(
                    "ID a editar",
                    df_edit['id'] if not df_edit.empty else [0],
                    key="sel_editar"
                )

                # FIX BUG 2: el botón Restaurar usa una key de estado para forzar
                # que el form se re-renderice con los valores originales de la BD
                if col_limpiar.button("🧹 Restaurar / Limpiar", key="btn_restaurar"):
                    # Limpiamos cualquier key de widget del form para que Streamlit
                    # lo vuelva a dibujar con los valores por defecto (los de `value=data[x]`)
                    for k in list(st.session_state.keys()):
                        if k.startswith("edit_"):
                            del st.session_state[k]
                    st.rerun()

                if id_ed:
                    conn = sqlite3.connect('conocimiento.db')
                    cur = conn.cursor()
                    cur.execute("SELECT * FROM reglas_diagnostico WHERE id=?", (id_ed,))
                    data = cur.fetchone()
                    conn.close()

                    if data:
                        with st.form("edit_form"):
                            e_dtc  = st.text_input("DTC",        value=data[1], key="edit_dtc")
                            e_tec  = st.selectbox(
                                "Tecnología",
                                ["Combustión", "Híbrido", "Eléctrico"],
                                index=["Combustión", "Híbrido", "Eléctrico"].index(data[2]),
                                key="edit_tec"
                            )
                            e_sin  = st.text_area("Síntoma",     value=data[3], key="edit_sin")
                            e_cp   = st.text_area("Causa 1",     value=data[4], key="edit_cp")
                            e_sp   = st.text_area("Solución 1",  value=data[5], key="edit_sp")
                            e_cs   = st.text_area("Causa 2",     value=data[6] if data[6] else "", key="edit_cs")
                            e_ss   = st.text_area("Solución 2",  value=data[7] if data[7] else "", key="edit_ss")
                            e_prot = st.text_input("Seguridad",  value=data[8], key="edit_prot")
                            if st.form_submit_button("Actualizar"):
                                motor.actualizar_regla(id_ed, e_dtc, e_tec, e_sin, e_cp, e_sp, e_cs, e_ss, e_prot)
                                st.success("Actualizado.")
                                st.rerun()   # FIX BUG 4: actualizamos la tabla superior

            # ── ELIMINAR ─────────────────────────────────────────
            with sub3:
                st.write("### Eliminar Regla de Conocimiento")
                # FIX BUG 3: también recargamos aquí
                df_del = cargar_reglas()

                if not df_del.empty:
                    opciones = {
                        row['id']: f"ID: {row['id']} | DTC: {row['dtc']} | Síntoma: {row['sintoma'][:30]}..."
                        for _, row in df_del.iterrows()
                    }
                    id_eliminar = st.selectbox(
                        "Selecciona la regla a eliminar:",
                        options=list(opciones.keys()),
                        format_func=lambda x: opciones[x]
                    )
                    if st.button("🗑️ Confirmar Eliminación", type="primary"):
                        conn = sqlite3.connect('conocimiento.db')
                        cur = conn.cursor()
                        cur.execute("DELETE FROM reglas_diagnostico WHERE id=?", (id_eliminar,))
                        conn.commit()
                        conn.close()
                        st.success(f"La regla con ID {id_eliminar} ha sido eliminada.")
                        st.rerun()
                else:
                    st.info("No hay reglas registradas en el sistema.")

        # ── PESTAÑA 2: RESOLVER REPORTES ────────────────────────
        with tabs[2]:
            st.header("Reportes Pendientes")
            conn = sqlite3.connect('conocimiento.db')
            pendientes = pd.read_sql_query("SELECT * FROM casos_pendientes", conn)
            conn.close()
            st.dataframe(pendientes, use_container_width=True)
            if not pendientes.empty:
                id_res = st.selectbox("Marcar resuelto ID", pendientes['id'])
                if st.button("Limpiar Reporte"):
                    motor.borrar_reporte_pendiente(int(id_res))
                    st.rerun()

        # ── PESTAÑA 3: ESTADÍSTICAS ──────────────────────────────
        with tabs[3]:
            st.header("📊 Análisis Profundo de Diagnósticos")
            conn = sqlite3.connect('conocimiento.db')
            stats = pd.read_sql_query("SELECT * FROM estadisticas", conn)
            conn.close()

            if not stats.empty:
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Total Diagnósticos Realizados", len(stats))
                with col2:
                    columna_resultado = 'resultado' if 'resultado' in stats.columns else stats.columns[-1]
                    aciertos = len(stats[stats[columna_resultado].astype(str).str.contains('Acierto', case=False, na=False)])
                    st.metric("Total Diagnósticos Exitosos", aciertos)

                c_graf1, c_graf2 = st.columns(2)
                with c_graf1:
                    if 'tipo_vehiculo' in stats.columns:
                        fig1 = px.pie(stats, names='tipo_vehiculo', title='Diagnósticos por Tipo de Motorización', hole=0.3)
                        st.plotly_chart(fig1, use_container_width=True)
                    else:
                        st.write("Columna 'tipo_vehiculo' no encontrada para la gráfica.")

                with c_graf2:
                    columna_codigo = 'codigo_sintoma' if 'codigo_sintoma' in stats.columns else stats.columns[1]
                    top_fallas = stats[columna_codigo].value_counts().head(5).reset_index()
                    top_fallas.columns = ['Falla', 'Cantidad']
                    fig2 = px.bar(top_fallas, x='Falla', y='Cantidad', title='Top 5 Fallas/DTC Más Recurrentes')
                    st.plotly_chart(fig2, use_container_width=True)

                st.subheader("Base de Datos Bruta")
                st.dataframe(stats, use_container_width=True)
            else:
                st.info("Aún no hay datos suficientes para generar estadísticas gráficas.")

        # ── PESTAÑA 4: USUARIOS ──────────────────────────────────
        with tabs[4]:
            st.header("Gestión de Usuarios")

            sub_crear, sub_eliminar = st.tabs(["➕ Crear Usuario", "🗑️ Eliminar Usuario"])

            with sub_crear:
                with st.form("crear_u", clear_on_submit=True):
                    c1, c2, c3 = st.columns(3)
                    u_n = c1.text_input("Nombre Usuario")
                    u_p = c2.text_input("Contraseña", type="password")
                    u_r = c3.selectbox("Rol", ["Mecanico", "Administrador"])
                    if st.form_submit_button("Crear"):
                        conn = sqlite3.connect('conocimiento.db')
                        cur = conn.cursor()
                        try:
                            cur.execute(
                                "INSERT INTO usuarios (usuario, password, rol) VALUES (?, ?, ?)",
                                (u_n, u_p, u_r)
                            )
                            conn.commit()
                            st.success(f"Usuario '{u_n}' creado.")
                        except sqlite3.IntegrityError:
                            st.error("Error: El usuario ya existe.")
                        finally:
                            conn.close()

            with sub_eliminar:
                conn = sqlite3.connect('conocimiento.db')
                df_usuarios = pd.read_sql_query("SELECT id, usuario, rol FROM usuarios", conn)
                conn.close()
                st.dataframe(df_usuarios, use_container_width=True)

                if not df_usuarios.empty:
                    usuario_a_borrar = st.selectbox("Seleccione el usuario a eliminar", df_usuarios['usuario'])
                    if st.button("🚨 Eliminar Usuario Definitivamente", type="primary"):
                        if usuario_a_borrar == st.session_state.user:
                            st.error("Por seguridad, no puedes eliminar tu propia sesión activa.")
                        else:
                            conn = sqlite3.connect('conocimiento.db')
                            cur = conn.cursor()
                            cur.execute("DELETE FROM usuarios WHERE usuario=?", (usuario_a_borrar,))
                            conn.commit()
                            conn.close()
                            st.success(f"Usuario '{usuario_a_borrar}' eliminado del sistema.")
                            st.rerun()
                else:
                    st.info("No hay usuarios registrados.")