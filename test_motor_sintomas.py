"""Pruebas offline del motor de síntomas (sin Supabase ni Streamlit).

IMPORTANTE: las reglas de abajo son DATOS DE PRUEBA SINTÉTICOS para ejercitar la
lógica; NO son la base de conocimiento real ni evidencia de precisión diagnóstica.
Ejecutar:  python test_motor_sintomas.py
"""
import sys, types

REGLAS = [  # (id, dtc, sintoma, causa_principal)
    (1, "P0300", "Fallo de encendido en varios cilindros, motor tiembla", "Bujías o bobinas defectuosas"),
    (2, "N/A", "Pérdida de potencia con humo negro por el escape", "Mezcla rica por inyectores sucios o filtro de aire obstruido"),
    (3, "P0455", "Check engine encendido, olor a combustible y fuga de vapores", "Tapón de combustible mal sellado o sistema EVAP con fuga"),
    (4, "N/A", "Dificultad de arranque en frío, motor tarda en encender", "Bomba de combustible débil"),
    (5, "N/A", "Humo blanco y pérdida de refrigerante, motor se calienta", "Empaque de culata dañado"),
    (6, "N/A", "Ruido de golpeteo en el bloque del motor", "Desgaste de bielas"),
]

class _Cur:
    def execute(self, *a, **k): pass
    def fetchall(self):
        return [dict(id=i, dtc=d, sintoma=s, causa_principal=c, solucion_principal="x",
                     causa_secundaria=None, solucion_secundaria=None,
                     protocolo_seguridad=None, origen="manual", veces_exitosa=0)
                for i, d, s, c in REGLAS]
class _Conn:
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def cursor(self): return _Cur()

fake = types.ModuleType("database"); fake.get_conn = lambda: _Conn()
sys.modules["database"] = fake

from inference_engine import MotorInferencia
from sinonimos import analizar_consulta

m = MotorInferencia()
fallos = 0
def caso(nombre, texto, espera_ids=None, espera_suficiente=None):
    global fallos
    r = m.buscar_por_sintoma(texto, "Combustión")
    top = r[0] if r else None
    ids = [x["id"] for x in r]
    ok = True
    if espera_ids is not None and (ids[:len(espera_ids)] != espera_ids if espera_ids else bool(ids)):
        ok = False
    if espera_suficiente is not None and (top["suficiente"] if top else False) != espera_suficiente:
        ok = False
    fallos += (not ok)
    print(("OK  " if ok else "FALLA"), nombre, "|", texto)
    for x in r[:3]:
        print(f"      ID {x['id']} coinc={x['coincidencia']}% suficiente={x['suficiente']} "
              f"orig={x['originales']} deriv={x['derivados']} falta={x['sin_cobertura']}")
    if not r: print("      (sin reglas relacionadas)")

print("== Casos del informe de revisión (15/10/2026) ==")
caso("Prueba 2: pérdida de potencia y humo negro", "Pérdida de potencia y humo negro", [2], True)
caso("Prueba 3: check engine y olor a gasolina", "Check Engine y olor a gasolina", None, None)
r3 = m.buscar_por_sintoma("Check Engine y olor a gasolina", "Combustión")
assert 4 not in [x["id"] for x in r3], "la regla de arranque en frío ya no debe coincidir (obs. 4.1)"
print("OK   prueba 3: la regla de arranque en frío (bomba) ya no aparece")
caso("Prueba 4: texto ajeno al dominio", "receta de arroz con pollo", [], None)

print("\n== Regresión de lo que fallaba ==")
r = m.buscar_por_sintoma("Pérdida de potencia y humo negro", "Combustión")
assert 3 not in [x["id"] for x in r], "regla EVAP (tapón) no debe salir por 'vapor'"
r = m.buscar_por_sintoma("Check Engine y olor a gasolina", "Combustión")
assert 4 not in [x["id"] for x in r[:1]] or not r[0]["suficiente"], "arranque en frío no debe recomendarse"
c = analizar_consulta("Check Engine y olor a gasolina")
assert [x["original"] for x in c] == ["check engine", "olor", "gasolina"], c
assert not any(s in ("motor","engine","bloque") for x in c for s in x["sinonimos"] if x["original"]=="check engine")
c = analizar_consulta("humo negro")
assert "vapor" not in [s for x in c for s in x["sinonimos"]]
c = analizar_consulta("hay una fuga")
assert "escape" not in [s for x in c for s in x["sinonimos"]]
print("OK   regresiones")

print("\n== Comportamiento esperado adicional ==")
caso("Solo término genérico → no concluyente", "motor falla", None, False)
caso("Sinónimo vale menos que literal", "perdida de potencia y fumando", [2], None)
caso("Sin tildes = con tildes", "perdida de potencia y humo negro", [2], True)
caso("Palabra completa: 'bloqueo' no es 'bloque'", "bloqueo", [], None)
caso("Humo blanco no activa humo negro", "humo blanco y se calienta", [5], True)

print("\nRESULTADO:", "todo OK" if not fallos else f"{fallos} caso(s) fallaron")
sys.exit(1 if fallos else 0)
