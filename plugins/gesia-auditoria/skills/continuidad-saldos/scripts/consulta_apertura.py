"""Da la consulta con la que el MCP exporta el asiento de apertura. Puede abortar.

    python consulta_apertura.py --filtro filtro.json [--sin-campo-apertura]

Lee el FiltroDeApertura que se exporto con la consulta de SQL_FILTRO y escribe en
pantalla, en una linea que empieza por SQL:, la consulta que hay que pasar tal cual a
exportar_consulta(fuente="diario"). La consulta trae solo las columnas que la prueba
usa y el filtro ya evaluado en JET (POR_FILTRO): el diario no sale entero del equipo.

--sin-campo-apertura cuando columnas(fuente="diario", tabla="Diario") no lista APERTURA,
que es una opcion de importacion: sin el, la consulta fallaria por un campo inexistente.

Codigos de salida:
  0  la consulta esta en pantalla
  2  el filtro no se puede leer o no se entiende: no se puede hacer la prueba
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# La carpeta del script, explicita: lanzado con `python -I` no esta en sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_continuidad import SQL_FILTRO, leer_filtro, salida_utf8, sql_apertura  # noqa: E402


def main() -> int:
    salida_utf8()
    p = argparse.ArgumentParser()
    p.add_argument("--filtro", required=True, help="el JSON exportado con SQL_FILTRO")
    p.add_argument("--sin-campo-apertura", action="store_true",
                   help="el Diario no trae la columna APERTURA")
    args = p.parse_args()

    filtro = leer_filtro(args.filtro)
    if filtro.get("ausente"):
        print("C02 ERROR: no se puede identificar el asiento de apertura: " + filtro["motivo"]
              + ". El asiento de apertura se fija al normalizar y no tiene que ser el 1, asi "
              "que no se puede suponer.")
        print("  (el filtro se exporta con: " + SQL_FILTRO + ")")
        return 2
    print("C02 · filtro de apertura: " + filtro["campo"] + " " + filtro["operador"] + " "
          + repr(filtro["valor"]))
    print("SQL: " + sql_apertura(filtro, not args.sin_campo_apertura))
    return 0


if __name__ == "__main__":
    sys.exit(main())
