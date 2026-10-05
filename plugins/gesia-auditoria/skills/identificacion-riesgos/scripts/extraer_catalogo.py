"""Extrae el catalogo de riesgos de un master de Gesia a JSON.

    python extraer_catalogo.py --gs3 "<Master ... CON RIESGOS.gs3>" --salida .

    python extraer_catalogo.py --catalogo <fichero exportado> --salida <trabajo>

Normaliza el catalogo que deja `exportar_consulta(entidad='catalogo_riesgos')`.
Hasta el 26/08/2026 esto era una herramienta de construccion: generaba un
`datos/riesgos.json` que viajaba DENTRO del paquete distribuido, o sea 240 KB con
la metodologia del master en claro en cada copia. Ahora el catalogo se lee del
master de cada cliente en cada ejecucion y se escribe en el directorio de
trabajo, que se borra al terminar.

Sigue admitiendo --gs3 para leer el API directamente, que es util para inspeccionar
un master desde la maquina del auditor. Pero en Cowork ese camino no funciona: el
contenedor no alcanza el localhost del auditor.

El catalogo vive en la tabla RiesgosNIAS del master. Trae bastante mas que el
Excel que se usaba antes: aserciones, valoracion del riesgo en sus tres niveles,
si es significativo, a que afecta y la referencia del papel de trabajo.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib_riesgos import (           # noqa: E402
    SinObligatorios,
    anio_master,
    resolver_obligatorios,
)

# Campos que SI son catalogo. Se dejan fuera a proposito:
#   Conclusion, Recomendacion  las escribe el auditor en su expediente
#   FicheroVinculado1/2, ReferenciaPT  son del encargo, no del catalogo
CAMPOS = (
    "IdRiesgo", "CodigoArea", "Riesgo", "CodigoClaseReferencia", "CodigoReferencia",
    "Integridad", "Existencia", "Exactitud", "Valoracion",
    "CodigoValorRIA_RI", "CodigoValorRIA_RCI", "CodigoValorRIA_RIM",
    "Significativo", "TipoRiesgo", "AfectaSaldo", "AfectaTransacciones",
    "AfectaInformacion", "Clasificacion", "AMRA", "Descripcion", "Procedimientos",
)


def puerto_gesia() -> int:
    try:
        s = ctypes.c_ulong(0)
        pid = ctypes.windll.kernel32.GetCurrentProcessId()
        ctypes.windll.kernel32.ProcessIdToSessionId(pid, ctypes.byref(s))
        return 8888 + s.value
    except Exception:
        return 8889


def consultar(gs3: str, sql: str, puerto: int) -> list:
    url = ("http://localhost:" + str(puerto) + "/gs3?archivo="
           + urllib.parse.quote(gs3) + "&sql=" + urllib.parse.quote(sql))
    with urllib.request.urlopen(url, timeout=180) as r:
        datos = json.loads(r.read().decode("utf-8"))
    if isinstance(datos, dict):
        raise RuntimeError("el servidor no devolvio filas: " + str(datos)[:300])
    return datos


def texto(v) -> str:
    """Normaliza los saltos de linea y quita los bloques en blanco de mas."""
    if v is None:
        return ""
    t = str(v).replace("_x000D_", "").replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"\n{3,}", "\n\n", t)
    return "\n".join(l.rstrip() for l in t.split("\n")).strip()


def si_no(v) -> bool:
    return str(v).strip().lower() in ("true", "-1", "1", "si", "sí")


def entero(v):
    t = str(v or "").strip()
    return int(t) if t.isdigit() else None


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    p.add_argument("--gs3", default="", help="el master CON RIESGOS, leido por el API")
    p.add_argument("--catalogo", default="",
                   help="fichero que dejo exportar_consulta(entidad="
                        "'catalogo_riesgos'). Es el camino normal: asi el "
                        "catalogo no pasa por el contexto del modelo ni viaja "
                        "en el paquete.")
    # Por defecto escribe en los datos del propio skill. Hubo un momento con dos
    # copias del catalogo, una en el repo y otra en el skill, y ese es el camino
    # seguro para que el dia de mañana se actualice una y el skill lea la otra.
    # Sin valor por defecto A PROPOSITO. Antes escribia en datos/ del propio
    # skill y el catalogo acababa viajando dentro del paquete: 240 KB con la
    # metodologia del master, en claro, en cada copia distribuida. Ahora se
    # escribe en el directorio de trabajo de la sesion y se borra al terminar.
    p.add_argument("--salida", required=True,
                   help="directorio de destino, normalmente el de trabajo")
    p.add_argument("--version", default="", help='etiqueta, p.ej. "Master 25"')
    # Por el camino normal -el de --catalogo- aqui no llega la ruta del master, y
    # el catalogo se quedaba SIN ORIGEN: version y origen vacios. Un catalogo
    # anonimo no se puede contrastar con nada, y asi es como se llego a usar el
    # master de 2021 en un encargo de 2025 sin que nada lo dijera.
    p.add_argument("--master", default="",
                   help="ruta o nombre del .gs3 del master, para dejar constancia "
                        "de DE DONDE sale el catalogo. Con --catalogo es la unica "
                        "forma de saberlo")
    p.add_argument("--puerto", type=int, default=None)
    args = p.parse_args()

    if not args.catalogo and not args.gs3:
        print("Hace falta --catalogo (lo normal) o --gs3.")
        return 2

    if args.catalogo:
        # El fichero que deja exportar_consulta: la consulta ya la hizo el MCP,
        # con el JOIN a Areas incluido. Aqui solo se normaliza.
        filas = json.loads(Path(args.catalogo).read_text(encoding="utf-8"))
        if isinstance(filas, dict):
            filas = filas.get("filas") or filas.get("rows") or []
        puerto = None
    else:
        puerto = args.puerto or puerto_gesia()
        filas = consultar(
            args.gs3,
            "SELECT " + ", ".join(CAMPOS)
            + " FROM RiesgosNIAS ORDER BY CodigoArea, IdRiesgo",
            puerto,
        )
    if not filas:
        print("El master no tiene riesgos en RiesgosNIAS.")
        return 2

    # Los nombres de area viven en el propio expediente, no en RiesgosNIAS.
    areas = {}
    if args.catalogo:
        # La entidad del MCP ya trae el nombre del area por LEFT JOIN.
        for f in filas:
            if f.get("Area"):
                areas[texto(f["CodigoArea"])] = texto(f["Area"])
    else:
        try:
            for a in consultar(args.gs3, "SELECT CodigoArea, Area FROM Areas", puerto):
                areas[texto(a["CodigoArea"])] = texto(a["Area"])
        except Exception as exc:                   # noqa: BLE001
            print("AVISO: no se han podido leer los nombres de area ("
                  + str(exc)[:80] + ")")

    riesgos = []
    for f in filas:
        cod = texto(f["CodigoArea"])
        riesgos.append({
            "id": entero(f["IdRiesgo"]),
            "area": cod,
            "area_nombre": areas.get(cod, ""),
            "nombre": texto(f["Riesgo"]),
            "referencia": texto(f["CodigoReferencia"]),
            "clase_referencia": texto(f["CodigoClaseReferencia"]),
            # Las cuatro aserciones de la NIA 315 que el master marca por riesgo.
            "aserciones": {
                "integridad": si_no(f["Integridad"]),
                "existencia": si_no(f["Existencia"]),
                "exactitud": si_no(f["Exactitud"]),
                "valoracion": si_no(f["Valoracion"]),
            },
            # Codigos 1-3. La escala (bajo/medio/alto) NO esta confirmada: hay que
            # preguntarla antes de traducirla a texto en ningun entregable.
            "valoracion_riesgo": {
                "inherente": entero(f["CodigoValorRIA_RI"]),
                "control_interno": entero(f["CodigoValorRIA_RCI"]),
                "incorreccion_material": entero(f["CodigoValorRIA_RIM"]),
            },
            "significativo": si_no(f["Significativo"]),
            "tipo_riesgo": entero(f["TipoRiesgo"]),
            "afecta": {
                "saldos": si_no(f["AfectaSaldo"]),
                "transacciones": si_no(f["AfectaTransacciones"]),
                "informacion": si_no(f["AfectaInformacion"]),
            },
            "clasificacion": texto(f["Clasificacion"]),
            "amra": si_no(f["AMRA"]),
            "descripcion": texto(f["Descripcion"]),
            "procedimientos": texto(f["Procedimientos"]),
        })

    destino = Path(args.salida)
    destino.mkdir(parents=True, exist_ok=True)
    de_donde = args.master or args.gs3
    catalogo = {
        "version": args.version or Path(de_donde).stem,
        "origen": Path(de_donde).name,
        "n": len(riesgos),
        "areas": sorted({r["area"] for r in riesgos}),
        "riesgos": riesgos,
    }
    (destino / "riesgos.json").write_text(
        json.dumps(catalogo, ensure_ascii=False, indent=1, allow_nan=False),
        encoding="utf-8")

    # Indice: lo unico que se lee entero. Lleva las marcas que sirven para elegir
    # sin abrir el detalle.
    L = ["# Catálogo de riesgos — " + catalogo["version"], "",
         str(len(riesgos)) + " riesgos en " + str(len(catalogo["areas"]))
         + " áreas. El detalle —descripción y procedimientos— está en "
           "`riesgos.json`; se lee por área o por id, nunca entero.", "",
         "Marcas: **S** significativo · aserciones I=integridad, E=existencia, "
         "X=exactitud, V=valoración.", ""]
    area = None
    for r in riesgos:
        if r["area"] != area:
            area = r["area"]
            L += ["", "## " + area + (" — " + r["area_nombre"] if r["area_nombre"] else "")]
        # Cada asercion con su letra explicita: existencia y exactitud empiezan
        # las dos por E y "IEE" no dice cual de las dos es.
        LETRAS = (("integridad", "I"), ("existencia", "E"),
                  ("exactitud", "X"), ("valoracion", "V"))
        marcas = "".join(letra for clave, letra in LETRAS if r["aserciones"][clave])
        L.append("- `" + str(r["id"]).rjust(3) + "` "
                 + ("**S** " if r["significativo"] else "")
                 + r["nombre"] + (" · " + marcas if marcas else ""))
    (destino / "indice.md").write_text("\n".join(L) + "\n", encoding="utf-8")

    print("Escrito en " + str(destino))
    print("  riesgos.json  " + str(len(riesgos)) + " riesgos, "
          + str(round((destino / "riesgos.json").stat().st_size / 1024, 1)) + " KB")
    print("  indice.md     "
          + str(round((destino / "indice.md").stat().st_size / 1024, 1)) + " KB")
    print("  areas         " + " ".join(catalogo["areas"]))
    print("  significativos " + str(sum(1 for r in riesgos if r["significativo"])))
    sin_nombre = sum(1 for r in riesgos if not r["area_nombre"])
    if sin_nombre:
        print("  AVISO: " + str(sin_nombre) + " riesgos sin nombre de area")

    # De donde sale, y con que numero vienen aqui los dos obligatorios. Se imprime
    # SIEMPRE: es el momento en que el auditor puede ver que ha cogido el master
    # que no era, y el unico sitio donde el numero de esos dos riesgos aparece
    # junto al fichero del que sale.
    if not catalogo["version"]:
        print("  AVISO: el catálogo no dice de qué máster sale. Pasa --master con "
              "la ruta del .gs3 para que quede constancia en el papel de trabajo.")
    else:
        print("  máster        " + catalogo["version"]
              + (" · año " + str(anio_master(catalogo)) if anio_master(catalogo) else ""))
    try:
        for r in resolver_obligatorios(catalogo):
            print("  obligatorio   " + str(r["id"]) + " — " + r["nombre"])
    except SinObligatorios as exc:
        print("  AVISO: " + str(exc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
