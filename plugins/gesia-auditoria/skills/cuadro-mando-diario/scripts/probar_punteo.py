#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Arnes de pruebas del modulo de punteo.

Comprueba lo que de verdad puede salir mal: que un punteo masivo no se cuele
como plazo de liquidacion, que el aging no se publique sin apertura, y que la
cobertura para el aging y la representatividad de los plazos se midan por
separado (una linea en grupo masivo esta cancelada, aunque su plazo no sirva).

Uso:  probar_punteo.py <diario.smn>
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

import lib_diario as LD
import analizar_punteo as AP

CIERRE = pd.Timestamp("2025-12-31")
UMBRAL = 80.0
NIVEL = 3


def escenario(df, sin_punteo=False, sin_apertura=False):
    d = df.copy()
    if sin_punteo:
        d["Indice"] = 0
    if sin_apertura:
        d = d[d["APERTURA"] == 0].reset_index(drop=True)
    return d


def main() -> int:
    df, _ = LD.cargar(Path(sys.argv[1]))
    resultados: list[tuple[str, bool, str]] = []

    def check(nombre, condicion, detalle=""):
        resultados.append((nombre, bool(condicion), detalle))

    # ---------------------------------------------------- expediente real ---
    g = LD.grupos_punteo(df)
    ap = LD.detectar_apertura(df)
    cob = AP.cobertura(df, g, NIVEL)
    pl = AP.plazos(df, g, NIVEL)

    check("hay punteo", g is not None, f"{len(g)} grupos")
    check("todos los grupos netean a cero", bool(g["cuadra"].all()))
    check("se detectan punteos masivos", int(g["masivo"].sum()) > 0,
          f"{int(g['masivo'].sum())} grupos, {int(g[g['masivo']].lineas.sum())} lineas")

    # El IVA soportado se cancela entero en un grupo masivo: cancelado al 100%,
    # pero sin una sola partida emparejada. Es el caso que motivo la distincion.
    if "472" in cob.index:
        r = cob.loc["472"]
        check("472 IVA: cancelado 100% y 0% en partidas",
              r["pct_cancelado"] == 100.0 and r["pct_partidas"] == 0.0,
              f"cancelado {r['pct_cancelado']}%, partidas {r['pct_partidas']}%")
        check("472 no aparece en los plazos", "472" not in pl.index)

    # Proveedores: el punteo masivo inflaba la media y la cola.
    if "400" in pl.index:
        p400 = pl.loc["400"]
        todos = g.reset_index()
        todos["g3"] = todos["CUENTA"].str[:3]
        sucio = todos[todos["g3"] == "400"]
        check("400: excluir masivos reduce la cola de morosos",
              int((sucio["dias"] > 180).sum()) > 20 and p400["grupos"] > 1000,
              f"sucio {int((sucio['dias'] > 180).sum())} vs limpio "
              f"{int((sucio[~sucio['masivo']]['dias'] > 180).sum())} partidas > 180 d")
        check("400: cobertura para aging suficiente",
              float(cob.loc['400', 'pct_cancelado']) >= UMBRAL,
              f"{cob.loc['400', 'pct_cancelado']}%")

    # Clientes: cobertura baja -> sin cifra de cabecera.
    if "430" in cob.index:
        check("430 clientes: cobertura insuficiente",
              float(cob.loc["430", "pct_cancelado"]) < UMBRAL,
              f"{cob.loc['430', 'pct_cancelado']}%")

    # Ninguna mediana sobre menos de MIN_PARTIDAS partidas se resume.
    check("no se resumen medianas sin muestra",
          bool((pl.loc[pl["muestra_suficiente"], "grupos"] >= AP.MIN_PARTIDAS).all()))

    # El aging tiene que sumar el saldo de la cuenta.
    punteables = set(cob.index)
    ag = AP.aging(df, CIERRE, ap["mask"], punteables, NIVEL)
    for grupo in ("400", "430"):
        if grupo in set(ag["grupo"]):
            suma = float(ag.loc[ag["grupo"] == grupo, "neto"].sum())
            saldo = float(df.loc[df["G3"] == grupo, "NETO"].sum())
            check(f"aging de {grupo} suma el saldo de la cuenta",
                  abs(suma - saldo) <= 0.05, f"{suma:.2f} vs {saldo:.2f}")

    # -------------------------------------------------------- sin punteo ---
    d = escenario(df, sin_punteo=True)
    check("sin punteo: no hay grupos", LD.grupos_punteo(d) is None)

    # ------------------------------------------------------ sin apertura ---
    d = escenario(df, sin_apertura=True)
    ap2 = LD.detectar_apertura(d)
    g2 = LD.grupos_punteo(d)
    check("sin apertura: no se detecta", not ap2["verificada"])
    check("sin apertura: el punteo se rompe",
          int((~g2["cuadra"]).sum()) > 0,
          f"{int((~g2['cuadra']).sum())} grupos dejan de netear")

    # ----------------------------------------------- umbral al 100 por 100 ---
    ev = cob[cob["lineas"] >= AP.MIN_LINEAS]
    check("con umbral al 100%, casi nada es suficiente",
          int((ev["pct_cancelado"] >= 100.0).sum()) < len(ev),
          f"{int((ev['pct_cancelado'] >= 100.0).sum())} de {len(ev)}")

    # ----------------------------------------------------------- informe ---
    print(f"{'comprobacion':52s} resultado  detalle")
    print("-" * 100)
    fallos = 0
    for nombre, ok, detalle in resultados:
        fallos += 0 if ok else 1
        print(f"{nombre:52s} {'OK' if ok else 'FALLO':9s}  {detalle}")
    print("-" * 100)
    print(f"{len(resultados) - fallos}/{len(resultados)} comprobaciones correctas")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
