"""Compara las respuestas propuestas contra las que ya puso un auditor.

Es la fase 2 del proceso: medir el skill contra un expediente real en vez de
suponer que funciona. Necesita un cuestionario YA contestado y las respuestas
que el modelo produjo leyendo solo las cuentas anuales.

    python probar_calibracion.py --cuestionario trabajo/cuestionario.json \
        --respuestas trabajo/respuestas.json

**El numero que hay que leer es el del eje hallazgo/no hallazgo**, no el de
coincidencia literal del codigo. `1` y `3` significan lo mismo para el trabajo
—esta pregunta no arroja hallazgo—, y cual de los dos se pone es convencion del
auditor que la contesta: en la segunda calibracion fueron 23 de 42
discrepancias, y se comprobo que no se puede deducir de la memoria (de las 55
respuestas `3` con motivo negativo, el auditor dio por buenas 39; voltearlas en
bloque arreglaba 16 y rompia 39).

Lo que importa de verdad es **en que se equivoca**. La matriz de confusion
separa los errores que cuestan trabajo (proponer 4 donde el auditor supo
responder) de los que son peligrosos (proponer 1 donde el auditor dijo 2: dar
por desglosado algo que falta).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from lib_cuestionario import RESPUESTAS, es_cabecera, salida_utf8

MAX_LISTA = 40

# `1` y `3` colapsan: los dos dicen que la pregunta no arroja hallazgo.
EJE = {1: "sin hallazgo", 2: "hallazgo", 3: "sin hallazgo", 4: "pendiente"}


def main() -> int:
    salida_utf8()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cuestionario", required=True, help="Con las respuestas del auditor")
    p.add_argument("--respuestas", required=True, help="Las propuestas por el modelo")
    args = p.parse_args()

    cuestionario = json.loads(Path(args.cuestionario).read_text(encoding="utf-8"))
    crudo = json.loads(Path(args.respuestas).read_text(encoding="utf-8"))
    propuestas = {str(r["orden"]): r for r in
                  (crudo["respuestas"] if isinstance(crudo, dict) else crudo)}

    # exportar_consulta devuelve una lista pelada; el formato con "filas" es
    # el de las pruebas antiguas. Se aceptan los dos, como con las respuestas.
    crudas = cuestionario["filas"] if isinstance(cuestionario, dict) else cuestionario
    filas = [f for f in crudas if not es_cabecera(f)]
    referencia = {str(f["CodigoOrden"]): f for f in filas
                  if str(f.get("Respuesta", "")).strip()}

    if not referencia:
        print("ABORTA: el cuestionario no tiene respuestas del auditor contra las que medir.")
        return 2

    matriz: dict[tuple[int, int], int] = {}
    fondo = []       # desacuerdan en si hay hallazgo o no
    convencion = []  # coinciden en el fondo, distinto codigo (1 frente a 3)
    for orden, fila in sorted(referencia.items(), key=lambda x: int(x[0])):
        propuesta = propuestas.get(orden)
        if propuesta is None:
            continue
        auditor, modelo = int(fila["Respuesta"]), int(propuesta["respuesta"])
        matriz[(auditor, modelo)] = matriz.get((auditor, modelo), 0) + 1
        if auditor == modelo:
            continue
        caso = (orden, fila, auditor, modelo, propuesta)
        (convencion if EJE[auditor] == EJE[modelo] else fondo).append(caso)

    comparadas = sum(matriz.values())
    literales = sum(n for (a, m), n in matriz.items() if a == m)
    de_acuerdo = comparadas - len(fondo)

    print(f"Comparadas {comparadas} preguntas de {len(filas)}.")
    print(f"Eje hallazgo/no hallazgo: {de_acuerdo}  ({de_acuerdo / comparadas:.1%})"
          "   <-- el numero que cuenta")
    print(f"Codigo literal:           {literales}  ({literales / comparadas:.1%})\n")

    codigos = sorted(RESPUESTAS)
    print("Matriz: filas = auditor, columnas = modelo")
    print("        " + "".join(f"{RESPUESTAS[c][:9]:>11}" for c in codigos) + f"{'total':>9}")
    for a in codigos:
        fila_total = sum(n for (x, _), n in matriz.items() if x == a)
        if not fila_total:
            continue
        celdas = "".join(f"{matriz.get((a, m), 0):>11}" for m in codigos)
        print(f"{RESPUESTAS[a][:7]:>8}" + celdas + f"{fila_total:>9}")

    # Los dos errores que no son iguales de graves.
    peligrosos = [d for d in fondo if d[2] == 2 and d[3] in (1, 3)]
    conservadores = [d for d in fondo if d[3] == 4 and d[2] != 4]
    print(f"\nPELIGROSOS  {len(peligrosos)}: el auditor dijo No y el modelo dio por bueno "
          "el desglose o lo declaró no aplicable")
    print(f"CONSERVADORES {len(conservadores)}: el modelo dejó Pendiente algo que el auditor "
          "supo responder")

    print(f"\n{len(fondo)} desacuerdos de fondo:")
    for orden, fila, auditor, modelo, propuesta in fondo[:MAX_LISTA]:
        marca = "  <-- PELIGROSA" if (auditor == 2 and modelo in (1, 3)) else ""
        print(f"\n  [{orden}] {fila['Punto']}.{fila['DesglosePunto']}  "
              f"auditor={auditor} {RESPUESTAS[auditor]} · modelo={modelo} "
              f"{RESPUESTAS[modelo]}{marca}")
        print(f"      {' '.join(str(fila['Descripcion']).split())[:150]}")
        if propuesta.get("motivo"):
            print(f"      modelo: {propuesta['motivo'][:200]}")
    if len(fondo) > MAX_LISTA:
        print(f"\n  … y {len(fondo) - MAX_LISTA} desacuerdos de fondo más")

    if convencion:
        print(f"\nCONVENCION 1/3: {len(convencion)} preguntas. Mismo criterio de fondo "
              "—sin hallazgo—,\ndistinto codigo. Informativo: no son desacuerdos.")
        for orden, fila, auditor, modelo, _ in convencion:
            print(f"  [{orden}] {fila['Punto']}.{fila['DesglosePunto']}  "
                  f"auditor={auditor} · modelo={modelo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
