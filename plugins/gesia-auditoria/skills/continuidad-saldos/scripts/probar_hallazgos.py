"""Comprueba que el comparador detecta lo que tiene que detectar.

    python probar_hallazgos.py --diario "<real.smn>" --cierre cierre.json

Parte de un diario REAL, hace una copia y le mete tres casos a proposito:

  1. una cuenta de resultados en el asiento de apertura (710000000, 333.333)
  2. una cuenta de balance nueva que el expediente no reconoce (122000000, 50.000)
  3. las contrapartidas de las dos, que producen diferencias en cuentas que si
     estan en el cierre (570 y 572)

Por que hace falta: en un expediente sin diferencias, un comparador roto y uno
correcto dan el mismo resultado. Que un expediente salga a cero no demuestra que
esto funcione, solo que no se inventa hallazgos.

Sigue exigiendo un .smn real, igual que el resto de las pruebas del proyecto.
Un fixture sintetico desde cero esta pendiente (fase 3).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from lib_continuidad import salida_utf8

# Los tres casos. El importe de la 710 se eligio; los demas son redondos a
# proposito para que el cuadre de control se lea de un vistazo: 383.333 tiene que
# ser 333.333 + 50.000 exactos.
CASOS = [
    ("710000000", "Prestacion de servicios",   0.0, 333333.0, -333333.0),
    ("570000000", "Caja, euros",          333333.0,      0.0,  333333.0),
    ("122000000", "Reserva nueva del cliente", 0.0,  50000.0,  -50000.0),
    ("572000001", "Banco c/c",             50000.0,      0.0,   50000.0),
]

ESPERADO = {
    "cuenta_nueva": {"122000000": -50000.0},
    "diferencia": {"570": 333333.0, "572": 50000.0},
    "sin_apertura": {},
}
CUADRE_ESPERADO = {
    "descuadre_apertura_balance": 383333.0,
    "por_cuentas_de_resultados": 333333.0,
    "por_cuentas_no_reconocidas": 50000.0,
    "sin_explicar": 0.0,
}


def amanar(origen: Path, destino: Path, asiento: str, concepto: str) -> None:
    """Copia el diario y le inserta los casos en el asiento de apertura."""
    import pyodbc

    shutil.copy2(origen, destino)
    con = pyodbc.connect(
        "DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=" + str(destino) + ";"
    )
    cur = con.cursor()
    for cta, nom, debe, haber, ape in CASOS:
        cur.execute(
            "INSERT INTO Diario (FECHA, ASIENTO, CUENTA, NOMBRE, DEBE, HABER, "
            "CONCEPTO, APERTURA) VALUES (?,?,?,?,?,?,?,?)",
            "2025-01-01", asiento, cta, nom, debe, haber, concepto, ape,
        )
    con.commit()
    con.close()


def main() -> int:
    salida_utf8()
    p = argparse.ArgumentParser()
    p.add_argument("--diario", required=True, help="un .smn real, no se modifica")
    p.add_argument("--cierre", required=True)
    p.add_argument("--trabajo", default="trabajo_prueba")
    args = p.parse_args()

    aqui = Path(__file__).resolve().parent
    trabajo = Path(args.trabajo)
    trabajo.mkdir(parents=True, exist_ok=True)

    # El asiento y el concepto de apertura se leen del diario real: el fixture
    # tiene que meter sus apuntes en el MISMO asiento, o el filtro no los ve.
    sys.path.insert(0, str(aqui))
    from lib_continuidad import aplicar_filtro, cargar_diario, leer_filtro_apertura

    filtro = leer_filtro_apertura(args.diario)
    if filtro.get("ausente"):
        print("El diario de partida no sirve: " + filtro["motivo"])
        return 2
    df = cargar_diario(args.diario)
    m = aplicar_filtro(df, filtro)
    asiento = str(df.loc[m, "ASIENTO"].iloc[0])
    concepto = str(df.loc[m, "CONCEPTO"].iloc[0])
    print("diario de partida: asiento de apertura " + asiento
          + ", concepto " + repr(concepto))

    fixture = trabajo / "fixture.smn"
    amanar(Path(args.diario), fixture, asiento, concepto)
    print("fixture escrito en " + str(fixture))

    salida = trabajo / "resultado_fixture.json"
    res = subprocess.run(
        [sys.executable, str(aqui / "comparar.py"), "--diario", str(fixture),
         "--cierre", args.cierre, "--salida", str(salida)],
        capture_output=True, text=True,
    )
    if res.returncode != 0:
        print(res.stdout + res.stderr)
        return 2

    datos = json.loads(salida.read_text(encoding="utf-8"))
    fallos = []

    obtenido: dict = {t: {} for t in ESPERADO}
    for h in datos["hallazgos"]:
        obtenido.setdefault(h["tipo"], {})[h["cuenta"]] = h["importe"]

    for tipo, esperado in ESPERADO.items():
        if obtenido.get(tipo, {}) != esperado:
            fallos.append(
                "hallazgos " + tipo + ": se esperaba " + str(esperado)
                + " y salio " + str(obtenido.get(tipo, {}))
            )
        else:
            print("OK  hallazgos " + tipo + ": " + str(esperado))

    for clave, esperado in CUADRE_ESPERADO.items():
        real = datos["cuadre"][clave]
        if abs(real - esperado) > 0.005:
            fallos.append("cuadre " + clave + ": se esperaba "
                          + format(esperado, ".2f") + " y salio " + format(real, ".2f"))
        else:
            print("OK  cuadre " + clave + " = " + format(real, ".2f"))

    if fallos:
        print("\nFALLA:")
        for f in fallos:
            print("  - " + f)
        return 1
    print("\nTodo detectado. El comparador ve los tres casos y el cuadre los explica.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
