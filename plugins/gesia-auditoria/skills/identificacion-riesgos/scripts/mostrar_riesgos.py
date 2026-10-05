"""Muestra el detalle de unos riesgos del catalogo, para decidir si encajan.

    python mostrar_riesgos.py --ids 18,27,33,80
    python mostrar_riesgos.py --area H

El indice solo trae el nombre, y con el nombre no siempre se sabe si un riesgo
aplica: hay que leer su descripcion. Sin esto, el paso de eleccion acaba abriendo
`riesgos.json` entero —240 KB— para mirar cuatro fichas.

Por defecto NO imprime los procedimientos: ocupan tanto como la descripcion y en
el momento de elegir no hacen falta. Con `--procedimientos` se ven.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from lib_riesgos import cargar_catalogo, riesgo_legible, salida_utf8

ANCHO = 78


def pinta(r: dict, con_procedimientos: bool) -> None:
    leg = riesgo_legible(r, con_procedimientos=con_procedimientos)
    print("")
    print("─" * ANCHO)
    cabecera = str(leg["id"]) + " · " + leg["nombre"]
    if leg["significativo"]:
        cabecera += "   [SIGNIFICATIVO]"
    print(cabecera)
    print("   área " + leg["area"] + (" — " + leg["area_nombre"]
                                      if leg["area_nombre"] else ""))

    detalle = []
    if leg["tipo"]:
        detalle.append(leg["tipo"])
    if leg["calificacion"]:
        detalle.append(leg["calificacion"])
    if leg["riesgo_incorreccion"]:
        detalle.append("incorrección " + leg["riesgo_incorreccion"].lower())
    if leg["aserciones"]:
        detalle.append("afirmaciones: " + ", ".join(leg["aserciones"]))
    if leg["referencia"]:
        detalle.append("ref. " + leg["referencia"])
    if detalle:
        print("   " + " · ".join(detalle))

    if leg["descripcion"]:
        print("")
        for linea in leg["descripcion"].split("\n"):
            print("   " + linea if linea.strip() else "")
    if con_procedimientos and leg.get("procedimientos"):
        print("")
        print("   PROCEDIMIENTOS")
        for linea in leg["procedimientos"].split("\n"):
            print("   " + linea if linea.strip() else "")


def main() -> int:
    salida_utf8()
    p = argparse.ArgumentParser()
    # Obligatorio y sin valor por defecto: el catalogo ya no vive en el skill,
    # se lee del master en cada ejecucion y queda en el directorio de trabajo.
    p.add_argument("--catalogo", required=True,
                   help="riesgos.json normalizado por extraer_catalogo.py")
    p.add_argument("--ids", help="lista separada por comas, p.ej. 18,27,33")
    p.add_argument("--area", help="código de área, p.ej. H")
    p.add_argument("--procedimientos", action="store_true",
                   help="incluir los procedimientos previstos")
    args = p.parse_args()

    if not args.ids and not args.area:
        print("Hay que decir --ids o --area.")
        return 2

    catalogo = cargar_catalogo(args.catalogo)
    por_id = {int(r["id"]): r for r in catalogo["riesgos"] if r.get("id") is not None}

    if args.ids:
        pedidos, desconocidos = [], []
        for trozo in args.ids.split(","):
            trozo = trozo.strip()
            if not trozo:
                continue
            if trozo.isdigit() and int(trozo) in por_id:
                pedidos.append(por_id[int(trozo)])
            else:
                desconocidos.append(trozo)
        if desconocidos:
            # Un id que no existe casi siempre es un id inventado, y conviene
            # verlo ahora y no cuando el validador aborte con el informe a medias.
            print("ATENCIÓN: estos ids no están en el catálogo: "
                  + ", ".join(desconocidos))
        for r in pedidos:
            pinta(r, args.procedimientos)
        print("")
        print("─" * ANCHO)
        print(str(len(pedidos)) + " de " + str(len(catalogo["riesgos"]))
              + " riesgos del catálogo " + str(catalogo.get("version", "")))
        return 0 if not desconocidos else 1

    del_area = [r for r in catalogo["riesgos"]
                if str(r.get("area", "")).upper() == args.area.strip().upper()]
    if not del_area:
        print("El área " + repr(args.area) + " no tiene riesgos en el catálogo. "
              "Las que hay: " + " ".join(catalogo.get("areas", [])))
        return 1
    for r in del_area:
        pinta(r, args.procedimientos)
    print("")
    print("─" * ANCHO)
    print(str(len(del_area)) + " riesgos en el área " + args.area.upper())
    return 0


if __name__ == "__main__":
    sys.exit(main())
