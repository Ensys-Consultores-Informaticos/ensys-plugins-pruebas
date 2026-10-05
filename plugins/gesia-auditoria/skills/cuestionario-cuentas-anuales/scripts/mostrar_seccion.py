"""Imprime UNA seccion del cuestionario, para que el modelo la conteste.

Existe para que el modelo no abra nunca el JSON completo: son 154 filas y
~94.000 caracteres, y meterlos enteros en contexto es justo lo que el molde del
proyecto prohibe. La seccion mas grande de la memoria PYME son 31 preguntas.

    python mostrar_seccion.py --cuestionario trabajo/cuestionario.json --punto 3

Sin `--punto` lista el indice de secciones con su tamaño.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from lib_cuestionario import leer_cuestionario, salida_utf8


def limpiar(texto: str) -> str:
    """Deja el texto en una linea. Los saltos vienen del maquetado del master."""
    return " ".join(str(texto or "").split())


def main() -> int:
    salida_utf8()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cuestionario", required=True)
    p.add_argument("--punto", help="Numero de seccion. Sin el, lista el indice")
    args = p.parse_args()

    datos = leer_cuestionario(args.cuestionario)
    secciones = datos["secciones"]

    if not args.punto:
        print(f"{datos['guia']} — {datos['n_preguntas']} preguntas en {len(secciones)} secciones")
        for s in secciones:
            print(f"  Punto {s['punto']:>2}  {len(s['preguntas']):>3} preguntas  {limpiar(s['titulo'])[:70]}")
        return 0

    seccion = next((s for s in secciones if s["punto"] == str(args.punto)), None)
    if seccion is None:
        print(f"No existe la seccion {args.punto}. Hay: "
              + ", ".join(s["punto"] for s in secciones))
        return 2

    print(f"PUNTO {seccion['punto']} — {limpiar(seccion['titulo'])}")
    print(f"{len(seccion['preguntas'])} preguntas\n")
    for fila in seccion["preguntas"]:
        actual = str(fila.get("Respuesta", "")).strip()
        marca = f"  [ya respondida: {actual}]" if actual else ""
        print(f"[orden {fila['CodigoOrden']}] {seccion['punto']}.{fila['DesglosePunto']}{marca}")
        print(f"  {limpiar(fila['Descripcion'])}")
        norma = limpiar(fila.get("Comentario", ""))
        if norma:
            print(f"  Norma: {norma}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
