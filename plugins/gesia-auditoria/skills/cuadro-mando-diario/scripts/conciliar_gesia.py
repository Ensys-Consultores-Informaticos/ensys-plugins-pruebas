#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fase 2a: CONCILIACION DEL DIARIO CON LOS SALDOS DEL EXPEDIENTE.

Compara el neto del diario por grupo de cuenta con el SaldoCliente de la tabla
Cuentas de Gesia. Es la comprobacion que garantiza que el panel no contradice a
los papeles de trabajo: si el diario que se analiza no es el que sostiene los
saldos del expediente, todo lo que venga despues sobra.

Dos reglas aprendidas del expediente y no de la documentacion:

  * Gesia CALCULA dos cuentas que el diario no lleva: la 080 (cuenta de
    explotacion) y, cuando el diario no trae asiento de regularizacion, la 129
    (resultado del ejercicio). Compararlas produce descuadres falsos, asi que
    se excluyen y se informa de ello.

  * Un grupo con movimiento en el diario pero saldo cero al cierre NO aparece
    en Cuentas al filtrar por saldo distinto de cero. Su ausencia es conforme,
    no un descuadre.

Materialidad: cada descuadre se gradua sobre la importancia relativa de trabajo
(IR_T). Por debajo del umbral de trivialidad es informativo; por encima, es un
hallazgo que hay que resolver antes de publicar el panel.

Uso:
    conciliar_gesia.py <diario.smn> --cuentas <cuentas_gesia.json>
                       [--nivel 3] [--ir-t 200000] [--trivial 5]
                       [--calculadas 080,129] [--json salida.json]

Codigos de salida:
    0  todo conciliado
    1  descuadres por debajo del umbral de trivialidad
    2  descuadres materiales: no publicar el panel sin resolverlos
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from pathlib import Path

import pandas as pd

import lib_diario as LD

MAX_LISTA = 12
CALCULADAS_POR_GESIA = ("080", "129")
TRIVIAL_PCT_IR_T = 5.0   # % de IR_T por debajo del cual un descuadre es trivial

CONFORME = "conforme"
CERO = "conforme (saldo cero)"
TRIVIAL = "descuadre trivial"
MATERIAL = "DESCUADRE MATERIAL"
CALCULADA = "calculada por Gesia"


def _num(v) -> float:
    """Los importes de Gesia llegan como texto con coma decimal."""
    if v is None or v == "":
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    return float(str(v).strip().replace(" ", "").replace(",", "."))


def eur(v: float) -> str:
    return f"{v:,.2f}".replace(",", " ").replace(".", ",") + " EUR"


def cargar_cuentas_gesia(ruta: Path) -> pd.DataFrame:
    """
    Admite la salida cruda de consultar_gesia: una lista de objetos con
    Cuenta, Nombre y los saldos. Solo Cuenta y SaldoCliente son imprescindibles.
    """
    datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    if isinstance(datos, dict):                      # {"400": -733735.16, ...}
        datos = [{"Cuenta": k, "SaldoCliente": v} for k, v in datos.items()]
    filas = []
    for d in datos:
        filas.append(
            {
                "cuenta": str(d.get("Cuenta", d.get("cuenta", ""))).strip(),
                "nombre": str(d.get("Nombre", d.get("nombre", ""))).strip(),
                "gesia": _num(d.get("SaldoCliente", d.get("saldo"))),
                "anterior": _num(d.get("SaldoAnterior")),
                "ajuste": _num(d.get("SaldoAj")),
            }
        )
    g = pd.DataFrame(filas)
    if g.empty or not g["cuenta"].any():
        raise ValueError("el fichero de cuentas de Gesia esta vacio o sin columna Cuenta")
    return g.sort_values("cuenta", kind="mergesort").reset_index(drop=True)


def conciliar(df: pd.DataFrame, g: pd.DataFrame, nivel: int,
              calculadas: set[str], umbral: float) -> pd.DataFrame:
    """Devuelve una fila por grupo de cuenta, con su estado de conciliacion."""
    col = f"G{nivel}"
    diario = (
        df.groupby(col, sort=True)
        .agg(diario=("NETO", "sum"), apuntes=("NETO", "size"), volumen=("VOL", "sum"))
        .reset_index()
        .rename(columns={col: "cuenta"})
    )
    m = g.merge(diario, on="cuenta", how="outer")
    m["nombre"] = m["nombre"].fillna("")
    for c in ("gesia", "anterior", "ajuste", "diario", "volumen"):
        m[c] = m[c].fillna(0.0)
    m["apuntes"] = m["apuntes"].fillna(0).astype(int)
    m["en_gesia"] = m["cuenta"].isin(set(g["cuenta"]))
    m["en_diario"] = m["apuntes"] > 0
    m["dif"] = (m["diario"] - m["gesia"]).round(2)

    def estado(r) -> str:
        if r["cuenta"] in calculadas:
            return CALCULADA
        if abs(r["dif"]) <= LD.TOLERANCIA:
            # Sin movimiento y sin saldo, o cuadre exacto.
            if not r["en_gesia"] and abs(r["diario"]) <= LD.TOLERANCIA:
                return CERO
            return CONFORME
        return TRIVIAL if abs(r["dif"]) <= umbral else MATERIAL

    m["estado"] = m.apply(estado, axis=1)
    m["pct_ir_t"] = None
    return m.sort_values(
        ["estado", "dif"], key=lambda s: s.abs() if s.name == "dif" else s,
        ascending=[True, False], kind="mergesort",
    ).reset_index(drop=True)


def imprimir(m: pd.DataFrame, nivel: int, ir_t: float | None, umbral: float,
             calculadas: set[str], df: pd.DataFrame) -> None:
    an = "=" * 74
    print(an)
    print(f"CONCILIACION DIARIO <-> GESIA  (nivel {nivel} digitos)")
    print(an)

    cuenta_estados = m["estado"].value_counts()
    conformes = int(cuenta_estados.get(CONFORME, 0))
    ceros = int(cuenta_estados.get(CERO, 0))
    triviales = int(cuenta_estados.get(TRIVIAL, 0))
    materiales = int(cuenta_estados.get(MATERIAL, 0))
    calc = int(cuenta_estados.get(CALCULADA, 0))

    print(f"  grupos comparados      {len(m) - calc}")
    print(f"  conformes              {conformes}"
          + (f" (+{ceros} con saldo cero)" if ceros else ""))
    print(f"  descuadres triviales   {triviales}"
          + (f"   (<= {eur(umbral)})" if ir_t else ""))
    print(f"  DESCUADRES MATERIALES  {materiales}")
    print(f"  excluidas (calculadas) {calc}   {', '.join(sorted(calculadas))}")

    conciliado = m.loc[m["estado"].isin([CONFORME, CERO]), "volumen"].sum()
    total = float(df["VOL"].sum())
    print(f"  volumen conciliado     {conciliado / total * 100:.2f}% del diario")
    print()

    problemas = m[m["estado"].isin([MATERIAL, TRIVIAL])]
    if len(problemas):
        print("DESCUADRES")
        print(f"  {'cuenta':7s} {'diario':>16s} {'Gesia':>16s} {'diferencia':>15s}  estado")
        for _, r in problemas.head(MAX_LISTA).iterrows():
            marca = "MATERIAL" if r["estado"] == MATERIAL else "trivial"
            print(f"  {r['cuenta']:7s} {eur(r['diario']):>16s} {eur(r['gesia']):>16s} "
                  f"{eur(r['dif']):>15s}  {marca}")
            # Sin este apunte, un descuadre por ausencia sale con la columna de
            # nombre en blanco y no se entiende de que lado falta la cuenta.
            if not r["en_gesia"]:
                print("          (no esta en el plan de cuentas de Gesia)")
            elif not r["en_diario"]:
                print(f"          {r['nombre'][:52]} (sin movimiento en el diario)")
            elif r["nombre"]:
                print(f"          {r['nombre'][:64]}")
        if len(problemas) > MAX_LISTA:
            print(f"  ... y {len(problemas) - MAX_LISTA} mas (en el JSON)")
        print()

    excl = m[m["estado"] == CALCULADA]
    if len(excl):
        print("EXCLUIDAS PORQUE LAS CALCULA GESIA, NO EL DIARIO")
        for _, r in excl.iterrows():
            print(f"  {r['cuenta']:7s} {r['nombre'][:44]:46s} Gesia {eur(r['gesia']):>16s}"
                  f"   diario {eur(r['diario'])}")
        print()

    veredicto = ("NO CONCILIA" if materiales else
                 "CONCILIA CON DIFERENCIAS TRIVIALES" if triviales else "CONCILIA")
    print(an)
    print(f"VEREDICTO: {veredicto}")
    print(an)


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("diario")
    p.add_argument("--cuentas", required=True,
                   help="JSON con las cuentas de Gesia (salida de consultar_gesia)")
    p.add_argument("--nivel", type=int, default=3,
                   help="digitos de agregacion (1, 2 o 3; el nivel 4 de Gesia "
                        "esta incompleto y no debe usarse)")
    p.add_argument("--ir-t", type=_num, default=None,
                   help="importancia relativa de trabajo")
    p.add_argument("--trivial", type=float, default=TRIVIAL_PCT_IR_T,
                   help=f"%% de IR_T por debajo del cual el descuadre es trivial "
                        f"(por defecto {TRIVIAL_PCT_IR_T:.0f})")
    p.add_argument("--calculadas", default=",".join(CALCULADAS_POR_GESIA),
                   help="cuentas que calcula Gesia y no estan en el diario")
    p.add_argument("--json", help="ruta donde escribir el resultado")
    args = p.parse_args()

    if args.nivel == 4:
        print("  [AVISO] el nivel de 4 digitos de Gesia esta incompleto: no crea "
              "la agregacion en todas las ramas. Usa 1, 2 o 3.")

    df, _ = LD.cargar(args.diario)
    g = cargar_cuentas_gesia(Path(args.cuentas))
    calculadas = {c.strip() for c in args.calculadas.split(",") if c.strip()}
    umbral = (args.ir_t * args.trivial / 100.0) if args.ir_t else LD.TOLERANCIA

    m = conciliar(df, g, args.nivel, calculadas, umbral)
    imprimir(m, args.nivel, args.ir_t, umbral, calculadas, df)

    materiales = int((m["estado"] == MATERIAL).sum())
    triviales = int((m["estado"] == TRIVIAL).sum())

    if args.json:
        filas = m.drop(columns=["pct_ir_t"]).to_dict(orient="records")
        Path(args.json).write_text(
            json.dumps(
                {
                    "nivel": args.nivel,
                    "ir_t": args.ir_t,
                    "umbral_trivial": round(umbral, 2),
                    "calculadas_excluidas": sorted(calculadas),
                    "resumen": {
                        "grupos": len(m),
                        "conformes": int((m["estado"] == CONFORME).sum()),
                        "conformes_saldo_cero": int((m["estado"] == CERO).sum()),
                        "triviales": triviales,
                        "materiales": materiales,
                        "ajustes_auditoria_total": round(float(m["ajuste"].sum()), 2),
                    },
                    "grupos": filas,
                },
                indent=2, ensure_ascii=False, default=str,
            ),
            encoding="utf-8",
        )
        print(f"conciliacion escrita en {args.json}")

    return 2 if materiales else (1 if triviales else 0)


if __name__ == "__main__":
    sys.exit(main())
