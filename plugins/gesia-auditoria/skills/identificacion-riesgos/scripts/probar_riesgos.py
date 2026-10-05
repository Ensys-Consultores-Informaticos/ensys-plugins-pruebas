"""Arnes del catalogo de riesgos. No necesita Gesia, ni red, ni un master en disco.

    python probar_riesgos.py
    python probar_riesgos.py --catalogo "<trabajo>/riesgos.json"

Existe por un fallo concreto, del 04/09/2026: los dos riesgos de inclusion
obligatoria estaban fijados por numero -OBLIGATORIOS = (18, 27)-, y ese numero es
la numeracion interna de CADA master. Contra el master 25 acertaba; contra el
master 21 metia en el informe "Perdida de la concesion administrativa" y
"Obsolescencia del producto en catalogo" rotulados como obligatorios por la
NIA-ES 240, y dejaba fuera los dos que si lo son. Sin un solo aviso.

Los casos sinteticos reproducen las dos numeraciones medidas ese dia. Con
--catalogo se comprueba ademas un catalogo de verdad, el que deje
extraer_catalogo.py.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib_riesgos import (           # noqa: E402
    CLAVES_OBLIGATORIOS,
    SinObligatorios,
    anio_master,
    aviso_master,
    cargar_catalogo,
    ids_obligatorios,
    resolver_obligatorios,
    salida_utf8,
)

VENTAS = "Integridad de las ventas (fraude)"
ELUSION = "Elusión de controles por la dirección (por sesgo o fraude)"


def catalogo(version, pares, relleno=()):
    """Un catalogo minimo: {id: nombre} y de que master dice venir."""
    riesgos = [{"id": i, "nombre": n, "area": "G", "area_nombre": ""}
               for i, n in list(pares) + list(relleno)]
    return {"version": version, "origen": version + ".gs3", "riesgos": riesgos}


# Las dos numeraciones reales, medidas el 04/09/2026.
M25 = catalogo("Master 25 CON RIESGOS", [(18, VENTAS), (27, ELUSION)])
M21 = catalogo("Master 21 CON RIESGOS", [(97, VENTAS), (28, ELUSION)],
               # Y estos son los que ocupaban el 18 y el 27 en ese master: los
               # que el codigo viejo colaba como obligatorios.
               [(18, "Pérdida de la concesión administrativa"),
                (27, "Obsolescencia del producto en catálogo (de carácter general)")])


def casos():
    yield ("el master 25 resuelve 18 y 27",
           lambda: ids_obligatorios(M25) == (18, 27))
    yield ("el master 21 resuelve 97 y 28",
           lambda: ids_obligatorios(M21) == (97, 28))
    yield ("los nombres resueltos son los dos correctos, en los dos masters",
           lambda: all([r["nombre"] for r in resolver_obligatorios(m)] == [VENTAS, ELUSION]
                       for m in (M25, M21)))

    # LA REGRESION. Si alguien vuelve a fijar (18, 27), esto muerde.
    yield ("contra el master 21 los obligatorios NO son 18 y 27",
           lambda: ids_obligatorios(M21) != (18, 27))
    yield ("y el 18 y el 27 existen en el master 21 siendo otra cosa: por eso "
           "fallaba en silencio",
           lambda: {r["id"] for r in M21["riesgos"]} >= {18, 27}
                   and 18 not in ids_obligatorios(M21))

    # El nombre se busca por un trozo, asi que un parentesis distinto no rompe.
    yield ("un nombre con otro parentesis sigue resolviendo",
           lambda: ids_obligatorios(catalogo(
               "Master X", [(3, "Integridad de las ventas"),
                            (9, "Elusión de controles por la dirección")])) == (3, 9))

    # Y cuando NO se puede resolver, se aborta. Nunca se sigue con lo que haya.
    yield ("un catalogo sin la elusion aborta",
           lambda: aborta(catalogo("Master Y", [(1, VENTAS)])))
    yield ("un catalogo con la elusion repetida aborta",
           lambda: aborta(catalogo("Master Z", [(1, VENTAS), (2, ELUSION), (3, ELUSION)])))
    yield ("un expediente renumerado, que no trae el catalogo, aborta",
           lambda: aborta(catalogo("Expediente", [(5, VENTAS)],
                                   [(1, "Relevancia Tesorería"), (2, "Relevancia compras")])))
    yield ("el mensaje de aborto dice de que catalogo habla",
           lambda: "Master Y" in mensaje(catalogo("Master Y", [(1, VENTAS)])))

    # El año del master, que es lo que avisa de haber cogido el de otro ejercicio.
    yield ("el año sale del nombre del master",
           lambda: (anio_master(M25), anio_master(M21)) == (2025, 2021))
    yield ("sin año en el nombre no se inventa",
           lambda: anio_master({"version": "CON RIESGOS", "origen": ""}) is None)
    yield ("un master de 2021 en un encargo de 2025 avisa",
           lambda: "2021" in (aviso_master(M21, 2025) or ""))
    yield ("el master del año que toca no avisa",
           lambda: aviso_master(M25, 2025) is None)
    yield ("sin ejercicio no se avisa de nada",
           lambda: aviso_master(M21, None) is None)

    # Las claves se comparan sin tildes, asi que ellas mismas no pueden llevarlas.
    yield ("las claves de busqueda van sin tildes y en minuscula",
           lambda: all(c == c.lower() and c.isascii() for c in CLAVES_OBLIGATORIOS))


def aborta(cat) -> bool:
    try:
        resolver_obligatorios(cat)
    except SinObligatorios:
        return True
    return False


def mensaje(cat) -> str:
    try:
        resolver_obligatorios(cat)
    except SinObligatorios as exc:
        return str(exc)
    return ""


def main() -> int:
    salida_utf8()
    p = argparse.ArgumentParser()
    p.add_argument("--catalogo", help="un riesgos.json de verdad, para comprobarlo también")
    args = p.parse_args()

    fallos = 0
    for nombre, prueba in casos():
        try:
            bien = bool(prueba())
        except Exception as exc:                       # noqa: BLE001
            bien, nombre = False, nombre + "  [" + type(exc).__name__ + ": " + str(exc)[:80] + "]"
        print(("  ok   " if bien else "  FALLA ") + nombre)
        fallos += 0 if bien else 1

    if args.catalogo:
        print("\nCatálogo real: " + args.catalogo)
        try:
            cat = cargar_catalogo(args.catalogo)
            obl = resolver_obligatorios(cat)
            print("  máster: " + str(cat.get("version") or "sin identificar")
                  + "  ·  " + str(len(cat["riesgos"])) + " riesgos"
                  + "  ·  año " + str(anio_master(cat) or "?"))
            for r in obl:
                print("  ok   obligatorio " + str(r["id"]) + " — " + r["nombre"])
        except Exception as exc:                       # noqa: BLE001
            print("  FALLA " + type(exc).__name__ + ": " + str(exc)[:200])
            fallos += 1

    print("\n" + ("Todo bien." if not fallos else str(fallos) + " comprobación(es) fallan."))
    return 0 if not fallos else 1


if __name__ == "__main__":
    sys.exit(main())
