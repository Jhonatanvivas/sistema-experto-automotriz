# Expert-Auto Popayán

**Sistema experto de diagnóstico de fallas vehiculares — prototipo académico**

Proyecto de grado de Ingeniería de Sistemas, Universidad Nacional Abierta y a Distancia (UNAD), Escuela de Ciencias Básicas, Tecnología e Ingeniería (ECBTI), sede Popayán.
Autor: Jhonatan David Vivas Muñoz.

> **Estado del proyecto:** prototipo en fase de validación. La base de conocimiento es un **borrador pendiente de validación por un experto técnico** y la precisión diagnóstica del sistema **aún no ha sido certificada**. No debe usarse como única fuente para intervenir un vehículo.

Aplicación publicada: (https://sistema-experto-automotriz.streamlit.app/)

---

## 1. Descripción

Expert-Auto asiste a técnicos de talleres automotrices de Popayán en el diagnóstico de fallas. El sistema aplica reglas de decisión almacenadas en una base de conocimiento y guía al técnico con **hipótesis ordenadas, pruebas de comprobación y advertencias de seguridad**, en lugar de sugerir el reemplazo directo de piezas. No pretende reemplazar al profesional, sino apoyar su criterio.

## 2. Alcance actual

- **Habilitado:** vehículos de **combustión interna**.
- **Reservado como trabajo futuro:** vehículos híbridos y eléctricos. Aparecen en el selector como «próximamente» (ver `config.py`); habilitarlos requiere cargar sus reglas y protocolos de seguridad de alta tensión.
- No incluye conexión directa con el vehículo: el técnico ingresa manualmente el código DTC o describe los síntomas.
- Arquitectura web en la nube; no funciona sin conexión a internet.

## 3. Funcionalidades

| Módulo | Descripción |
|---|---|
1--> | Diagnóstico por **código DTC** | Valida el formato OBD-II (ej. `P0300`) y consulta la regla asociada. |
2-->| Diagnóstico por **síntomas** | Texto libre en lenguaje del taller; muestra una recomendación solo si la coincidencia supera un umbral. |
3-->| Hipótesis y ruta secundaria | Hipótesis 1 con su comprobación y acción; si no resuelve, una hipótesis 2. |
4-->| Módulo de **explicación** | Muestra los hechos de entrada, la regla activada, su origen, las confirmaciones previas y el tiempo de inferencia. |
5-->| Precauciones de seguridad | Se muestran cuando la regla las define. |
6-->| **Reportes pendientes y aprendizaje asistido** | Los casos no resueltos pasan al administrador, quien registra la causa real y la solución. |
7-->| Base de conocimiento | Alta, edición y eliminación de reglas (administrador). |
8-->| Estadísticas y **dashboard de validación** | Tasa de resultados, tiempos, resultados por técnico y exportación a CSV. |
9-->| Reporte **PDF** | Se genera al confirmar un diagnóstico exitoso. |
10-->| Roles | `Administrador` y `Mecanico`. |

## 4. Cómo funciona el motor

**Por DTC.** Búsqueda de la regla que coincide con el código y la tecnología del vehículo.

**Por síntomas.** El texto del técnico se descompone en *conceptos*:

1. Se normaliza (sin tildes, sin palabras vacías) y se reconocen frases técnicas («check engine», «pierde potencia»).
2. Cada concepto puede ampliarse con **sinónimos técnicos**, que se distinguen siempre de lo que escribió el técnico.
3. Se puntúa cada regla: término literal = 1,0; sinónimo = `PESO_SINONIMO`; término genérico (ej. «motor») = `PESO_GENERICO`.
4. Solo se recomienda si la coincidencia alcanza `UMBRAL_COINCIDENCIA` y la regla cubre un mínimo de términos específicos. En caso contrario, el sistema **pide más datos y no sugiere ninguna reparación**.

> El porcentaje mostrado es la **coincidencia con la regla**, es decir, cuánto de lo descrito aparece en ella. **No es la probabilidad de que el diagnóstico sea correcto.**

Los parámetros están en `config.py`. Sus valores actuales son **provisionales** y deben calibrarse con la matriz formal de pruebas.

## 5. Estructura del repositorio

| Archivo | Función |
|---|---|
| `app.py` | Interfaz Streamlit: login, diagnóstico, administración y dashboard. |
| `inference_engine.py` | Motor de inferencia y operaciones sobre la base de conocimiento. |
| `sinonimos.py` | Análisis del texto de síntomas, sinónimos y puntuación de reglas. |
| `config.py` | Alcance (tecnologías habilitadas) y parámetros del motor. |
| `database.py` | Conexión a PostgreSQL (Supabase) y creación de tablas. |
| `test_motor_sintomas.py` | Pruebas automáticas del motor de síntomas (sin base de datos). |
| `requirements.txt` | Dependencias de Python. |
| `.devcontainer/` | Configuración del entorno de desarrollo. |
| `autosLogin.jpg`, `logo_taller.png` | Imágenes opcionales de la interfaz. |

## 6. Requisitos

- Python 3.11 o superior (el contenedor de desarrollo usa 3.11).
- Una base de datos **PostgreSQL** (el proyecto usa [Supabase](https://supabase.com)).
- Dependencias: `streamlit`, `pandas`, `plotly`, `fpdf2`, `psycopg2-binary`.
  Versiones probadas: `[PENDIENTE: completar con la salida de pip freeze]`

## 7. Instalación y ejecución local

```bash
git clone https://github.com/Jhonatanvivas/sistema-experto-automotriz.git
cd sistema-experto-automotriz
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Cree el archivo `.streamlit/secrets.toml` (**no lo suba a GitHub**):

```toml
DATABASE_URL = "postgresql://USUARIO:CONTRASENA@HOST:PUERTO/BASE_DE_DATOS"

# Opcionales: contraseñas iniciales de los usuarios creados en el primer arranque
ADMIN_PASSWORD   = "defina-una-contrasena"
TALLER1_PASSWORD = "defina-una-contrasena"
```

Ejecute la aplicación:

```bash
streamlit run app.py
```

En el primer arranque la aplicación crea las tablas (`usuarios`, `reglas_diagnostico`, `casos_pendientes`, `estadisticas`, `historial_diagnosticos`) y, solo si la tabla de usuarios está vacía, los usuarios iniciales `admin` (Administrador) y `taller1` (Mecánico). Cambie sus contraseñas.

## 8. Despliegue en Streamlit Community Cloud

1. Conecte el repositorio y defina `app.py` como archivo principal.
2. En **Settings → Secrets** pegue el contenido de `secrets.toml` descrito arriba.

## 9. Base de conocimiento

Cada regla se guarda en la tabla `reglas_diagnostico`:

| Campo | Contenido |
|---|---|
| `dtc` | Código DTC, o `N/A` si la regla es solo por síntomas. |
| `tipo_vehiculo` | Tecnología (hoy: `Combustión`). |
| `sintoma` | Descripción del síntoma, en el lenguaje que usaría un técnico. |
| `causa_principal` / `solucion_principal` | Hipótesis 1 y su comprobación y acción. |
| `causa_secundaria` / `solucion_secundaria` | Hipótesis 2 y su comprobación y acción. |
| `protocolo_seguridad` | Precauciones (opcional). |
| `origen` | `manual` o `aprendizaje` (regla generada desde un caso resuelto). |
| `veces_exitosa` | Cuántas veces el técnico confirmó que la regla resolvió el problema. |

**Formato de las soluciones:** `Comprobación: … Si se confirma: …`. Primero se comprueba la hipótesis; solo si se confirma se repara o reemplaza.

> Las reglas actuales son un **borrador**. Antes de usarlas en pruebas con técnicos o citarlas como evidencia, deben ser revisadas por un experto, con su fuente técnica documentada.

## 10. Pruebas

```bash
python test_motor_sintomas.py
```

Verifica la lógica del motor de síntomas sin conectarse a la base de datos. Usa **reglas sintéticas** de prueba; no constituye una medida de precisión diagnóstica.

## 11. Limitaciones conocidas

- Base de conocimiento en validación; precisión diagnóstica no certificada.
- Umbral de coincidencia y pesos provisionales, pendientes de calibración.
- Solo combustión interna; híbridos y eléctricos son trabajo futuro.
- Sin modo sin conexión.
- La seguridad de acceso (gestión de contraseñas y usuarios de demostración) es la propia de un prototipo académico y no está endurecida para uso en producción.

## 12. Documentación y autoría

- Documento del proyecto de grado: (https://docs.google.com/document/d/1kbdpSEd5QvdqC8wL4HzvU1qi_Rp7crrH/edit?usp=sharing&ouid=105111828453651123639&rtpof=true&sd=true)
- Licencia: `[PENDIENTE: definir]`
- Universidad Nacional Abierta y a Distancia (UNAD) — Programa de Ingeniería de Sistemas, Popayán.
