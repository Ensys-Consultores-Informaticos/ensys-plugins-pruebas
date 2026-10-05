"""Comprueba que los riesgos elegidos existen y estan bien citados. Puede abortar.

    python validar_seleccion.py --seleccion seleccion.json [--analisis analisis.json]

Esto es lo que sustituye a la instruccion «no te los inventes». Con un catalogo en
disco y ids, que un riesgo exista no es una recomendacion al modelo: es una
comprobacion que pasa o no pasa.

Forma de `seleccion.json`:

  {"riesgos": [
    {"id": 18,
     "nombre": "Integridad de las ventas (fraude)",
     "justificacion": "...",
     "evidencia": {"ratio": "AFC01", "elemento": "Fondo de Maniobra",
                   "valor": -3163962.34},
     ... o bien ...
     "evidencia": {"epigrafe": "res I.1",
                   "concepto": "Importe neto de la cifra de negocios",
                   "importe": -358300.0, "variacion": -0.467}}
  ]}

Codigos de salida:
  0  la seleccion es valida
  1  avisos: se puede seguir, pero hay que leerlos
  2  no vale. No se genera el informe.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from lib_riesgos import (
    MAX_RIESGOS,
    MIN_RIESGOS,
    SinObligatorios,
    aviso_master,
    cargar_catalogo,
    resolver_obligatorios,
    salida_utf8,
)


def main() -> int:
    salida_utf8()
    p = argparse.ArgumentParser()
    p.add_argument("--seleccion", required=True)
    p.add_argument("--analisis", help="para comprobar que la evidencia citada existe")
    p.add_argument("--catalogo")
    p.add_argument("--ejercicio",
                   help="el ejercicio auditado, p.ej. 2025. Solo sirve para avisar "
                        "si el catálogo es del máster de otro año")
    args = p.parse_args()

    catalogo = cargar_catalogo(args.catalogo)
    por_id = catalogo["por_id"]

    # Los dos obligatorios se resuelven POR NOMBRE contra ESTE catalogo: su
    # numero es la numeracion interna del master que se acaba de leer y cambia
    # de un master a otro. Si no se pueden resolver, no se valida nada.
    try:
        obligatorios = resolver_obligatorios(catalogo)
    except SinObligatorios as exc:
        print("ERROR   " + str(exc))
        return 2
    ids_obligatorios = [r["id"] for r in obligatorios]

    datos = json.loads(Path(args.seleccion).read_text(encoding="utf-8"))
    elegidos = datos.get("riesgos") if isinstance(datos, dict) else datos
    if not elegidos:
        print("ERROR: la selección no trae ningún riesgo.")
        return 2

    errores, avisos = [], []

    # V01 · los ids existen. Un id inventado es el fallo que esto viene a evitar.
    ids = []
    for r in elegidos:
        i = r.get("id")
        try:
            i = int(i)
        except (TypeError, ValueError):
            errores.append("id ilegible: " + repr(r.get("id")))
            continue
        if i not in por_id:
            errores.append("el riesgo " + str(i) + " NO existe en el catálogo ("
                           + catalogo.get("version", "") + ")")
            continue
        ids.append(i)

    # V02 · sin repetidos
    repetidos = sorted({i for i in ids if ids.count(i) > 1})
    if repetidos:
        errores.append("riesgos repetidos: " + str(repetidos))

    # V03 · el nombre es el del catalogo, literal. Se pide citar el nombre exacto,
    # y "casi el mismo nombre" en un papel de trabajo es un nombre distinto.
    for r in elegidos:
        try:
            i = int(r.get("id"))
        except (TypeError, ValueError):
            continue
        if i not in por_id:
            continue
        esperado = por_id[i]["nombre"]
        dado = str(r.get("nombre", "")).strip()
        if dado and dado != esperado:
            errores.append("el riesgo " + str(i) + " se cita como " + repr(dado)
                           + " y en el catálogo es " + repr(esperado))
        elif not dado:
            avisos.append("el riesgo " + str(i) + " viene sin nombre; se usará el "
                          "del catálogo")

    # V04 · los dos obligatorios, con el numero que tienen en este catalogo
    for r in obligatorios:
        if r["id"] not in ids:
            errores.append("falta el riesgo obligatorio " + str(r["id"]) + " — "
                           + r["nombre"])

    # V05 · cuantos. El rango es orientativo: fuera de rango se avisa, no se aborta.
    n = len(set(ids))
    if n < MIN_RIESGOS:
        avisos.append("solo hay " + str(n) + " riesgos y lo orientativo son "
                      + str(MIN_RIESGOS) + "-" + str(MAX_RIESGOS)
                      + ". Si las cifras no dan para más, el informe tiene que "
                        "decirlo en vez de rellenar.")
    elif n > MAX_RIESGOS:
        avisos.append("hay " + str(n) + " riesgos y lo orientativo son hasta "
                      + str(MAX_RIESGOS) + ".")

    # V06 · evidencia. Los dos obligatorios van siempre, asi que no necesitan
    # justificarse con cifras; los demas si: se eligen porque algo los dispara.
    for r in elegidos:
        try:
            i = int(r.get("id"))
        except (TypeError, ValueError):
            continue
        if i in ids_obligatorios:
            continue
        ev = r.get("evidencia") or {}
        # La evidencia puede venir de dos sitios y las dos valen: un epigrafe del
        # balance o la PyG, o un ratio de la revision analitica. Un fondo de
        # maniobra que se vuelve negativo justifica un riesgo tan bien como una
        # variacion del 30 % en una partida.
        por_epigrafe = bool(ev.get("concepto") or ev.get("epigrafe"))
        por_ratio = bool(ev.get("ratio") or ev.get("elemento"))
        if not por_epigrafe and not por_ratio:
            avisos.append("el riesgo " + str(i) + " no cita ningún epígrafe ni ratio: "
                          "se ha elegido sin evidencia cuantitativa y el informe "
                          "debería decir por qué")
        elif por_epigrafe and not por_ratio and (
                ev.get("importe") is None and ev.get("variacion") is None):
            avisos.append("el riesgo " + str(i) + " cita el epígrafe pero ni importe "
                          "ni variación")
        elif por_ratio and ev.get("valor") is None and ev.get("importe") is None:
            avisos.append("el riesgo " + str(i) + " cita el ratio "
                          + repr(ev.get("ratio") or ev.get("elemento"))
                          + " pero no su valor")

    # V07 · el master del catalogo. Se avisa, no se aborta: puede haber una razon
    # para usar el de otro año, pero tiene que ser una decision y no un descuido.
    desfase = aviso_master(catalogo, args.ejercicio)
    if desfase:
        avisos.append(desfase)

    for e in errores:
        print("ERROR   " + e)
    for a in avisos:
        print("AVISO   " + a)

    if errores:
        print("\nLa selección no vale. No se genera el informe.")
        return 2

    print("\nSelección válida: " + str(n) + " riesgos, con los "
          + str(len(obligatorios)) + " obligatorios.")
    print("  catálogo: " + str(catalogo.get("version") or "sin identificar")
          + ", " + str(len(catalogo.get("riesgos") or [])) + " riesgos")
    # Con el numero SIEMPRE el nombre: el numero solo significa algo dentro de
    # este catalogo, y leerlo suelto es lo que dejo pasar dos riesgos que no eran.
    for r in obligatorios:
        print("  obligatorio: " + str(r["id"]) + " — " + r["nombre"])
    if avisos:
        print("Con " + str(len(avisos)) + " aviso(s) que tienen que constar en el "
              "informe.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
