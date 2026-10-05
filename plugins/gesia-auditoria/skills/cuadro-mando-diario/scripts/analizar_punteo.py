#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fase 2b: PUNTEO, PLAZOS DE LIQUIDACION Y PARTIDAS ABIERTAS.

El punteo de Gesia empareja las lineas que se cancelan entre si (una compra con
su pago, por ejemplo) dandoles el mismo Indice DENTRO DE LA MISMA CUENTA. De ahi
salen dos cosas que el diario por si solo no da:

  * el plazo real de liquidacion de cada partida, sin necesidad de emparejar
    numeros de factura, que en un diario real son intratables;
  * la antiguedad de lo que queda sin cancelar al cierre.

Tres cautelas que el modulo aplica y deja escritas en su salida:

  1. El punteo NO es evidencia contable: lo produce un algoritmo por importe y
     tercero. Todo lo que sale de aqui es una lista de revision, no una
     conclusion. Por eso el informe habla de "segun el punteo de Gesia".

  2. Indice=0 significa "no punteado", no "pendiente". Si la cobertura de una
     cuenta no llega al umbral, su antiguedad se calcula pero NO se publica con
     cifra de cabecera: se muestran la distribucion y la lista.

  3. El punteo se apoya en la apertura. Sin apertura importada, los pagos que
     cancelan facturas del ejercicio anterior se quedan sin contrapartida y
     apareceren como abiertos. En ese caso el aging no se publica.

Uso:
    analizar_punteo.py <diario.smn> [--cierre AAAA-MM-DD] [--ir-t 200000]
                       [--cobertura 80] [--dias-alerta 180] [--json salida.json]

Codigos de salida:
    0  punteo completo y aging publicable
    1  publicable con limitaciones (cobertura baja en alguna cuenta)
    2  sin punteo, o aging suprimido por falta de apertura
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

import lib_diario as LD

MAX_LISTA = 10
UMBRAL_COBERTURA = 80.0
DIAS_ALERTA = 180
MIN_LINEAS = 30          # cuentas con menos lineas no se evaluan por cobertura
MIN_PARTIDAS = 5         # una mediana sobre menos partidas que esto no es un dato

# Tramos de antiguedad, en dias. El ultimo recoge lo que viene de la apertura,
# cuya antiguedad real es desconocida y en todo caso mayor.
TRAMOS = [(0, 30), (31, 60), (61, 90), (91, 180), (181, 365)]

# La antiguedad de partidas abiertas solo tiene sentido en cuentas de terceros y
# tesoreria. En una cuenta de resultados el saldo no son "partidas pendientes":
# es el gasto o el ingreso del ejercicio, y presentarlo como aging es un error
# conceptual, no de calculo.
GRUPOS_AGING = ("4", "5")
MIN_SALDO_AGING = 1000.0   # grupos con menos saldo abierto no se dibujan


def eur(v: float) -> str:
    return f"{v:,.2f}".replace(",", " ").replace(".", ",") + " EUR"


def num(v) -> str:
    """Miles con punto. Se formatea aparte porque aplicar .replace(",", ".")
    sobre la linea entera rompia los decimales de eur() y hasta las comas del
    texto."""
    return f"{int(v):,}".replace(",", ".")


def _num(txt) -> float:
    if txt in (None, ""):
        return 0.0
    return float(str(txt).strip().replace(" ", "").replace(",", "."))


# ------------------------------------------------------------- cobertura ----


def cobertura(df: pd.DataFrame, g: pd.DataFrame, nivel: int) -> pd.DataFrame:
    """
    Dos coberturas distintas, y no hay que confundirlas.

    pct_cancelado : lineas con Indice>0 sobre el total, sean de un grupo masivo
        o no. Es la que gobierna el AGING: una linea punteada esta cancelada
        aunque su grupo sea la cuenta neteandose consigo misma, y por tanto no
        es una partida abierta.

    pct_partidas : solo las lineas de grupos que son emparejamientos de verdad.
        Es la que dice hasta que punto los PLAZOS de ese grupo son
        representativos. Si una cuenta cancela casi todo en grupos masivos, su
        plazo se calcula sobre una minoria de sus movimientos.
    """
    col = f"G{nivel}"
    tot = df.groupby(col, sort=True).size().rename("lineas")

    utiles = g[~g["masivo"]].reset_index()[["CUENTA", "Indice"]]
    marca = df.merge(utiles, on=["CUENTA", "Indice"], how="inner")
    pun = marca.groupby(col, sort=True).size().rename("punteadas")
    masivas = (
        df.merge(g[g["masivo"]].reset_index()[["CUENTA", "Indice"]],
                 on=["CUENTA", "Indice"], how="inner")
        .groupby(col, sort=True).size().rename("en_masivos")
    )

    c = pd.concat([tot, pun, masivas], axis=1).fillna(0)
    for k in ("punteadas", "en_masivos"):
        c[k] = c[k].astype(int)
    c["canceladas"] = c["punteadas"] + c["en_masivos"]
    c["pct_cancelado"] = (c["canceladas"] / c["lineas"] * 100).round(1)
    c["pct_partidas"] = (c["punteadas"] / c["lineas"] * 100).round(1)
    c = c[c["canceladas"] > 0]
    return c.sort_values(["pct_cancelado", "lineas"], ascending=[False, False])


# ------------------------------------------------------------ liquidacion ----


def plazos(df: pd.DataFrame, g: pd.DataFrame, nivel: int) -> pd.DataFrame:
    """Estadisticos de dias hasta la cancelacion, por grupo de cuenta."""
    gg = g[~g["masivo"]].reset_index()
    if gg.empty:
        return pd.DataFrame()
    gg["grupo"] = gg["CUENTA"].str[:nivel]
    out = gg.groupby("grupo", sort=True).agg(
        grupos=("dias", "size"),
        mediana=("dias", "median"),
        media=("dias", "mean"),
        p90=("dias", lambda s: s.quantile(0.9)),
        maximo=("dias", "max"),
        importe=("importe", "sum"),
    )
    out["media"] = out["media"].round(1)
    out["p90"] = out["p90"].round(0)
    # Una mediana calculada sobre una o dos partidas no es un estadistico: se
    # deja fuera del cuadro y se cuenta aparte.
    out["muestra_suficiente"] = out["grupos"] >= MIN_PARTIDAS
    return out.sort_values("importe", ascending=False)


# ----------------------------------------------------------------- aging ----


def aging(df: pd.DataFrame, cierre: pd.Timestamp, ap_mask: pd.Series | None,
          grupos_punteables: set[str], nivel: int) -> pd.DataFrame:
    """
    Antiguedad de las lineas sin puntear en los grupos donde hay punteo.

    Las lineas que vienen de la apertura se separan en su propio tramo: su
    antiguedad real es desconocida y siempre mayor que la calculada.
    """
    col = f"G{nivel}"
    abiertas = df[
        (df["Indice"] == 0)
        & (df[col].isin(grupos_punteables))
        & (df["G1"].isin(GRUPOS_AGING))
    ].copy()
    if abiertas.empty:
        return pd.DataFrame()
    abiertas["dias"] = (cierre - abiertas["FECHA"]).dt.days
    abiertas["es_apertura"] = (
        ap_mask.reindex(abiertas.index).fillna(False) if ap_mask is not None else False
    )

    def tramo(r):
        if r["es_apertura"]:
            return "de apertura (>365)"
        for lo, hi in TRAMOS:
            if lo <= r["dias"] <= hi:
                return f"{lo}-{hi}"
        return ">365"

    abiertas["tramo"] = abiertas.apply(tramo, axis=1)
    out = abiertas.groupby([col, "tramo"], sort=True).agg(
        apuntes=("NETO", "size"), neto=("NETO", "sum")
    ).reset_index().rename(columns={col: "grupo"})
    out["neto"] = out["neto"].round(2)
    # Fuera los grupos cuyo saldo abierto es irrelevante: llenaban el grafico de
    # barras invisibles.
    saldo = out.groupby("grupo")["neto"].apply(lambda s: s.abs().sum())
    return out[out["grupo"].isin(saldo[saldo >= MIN_SALDO_AGING].index)]


def orden_tramo(t: str) -> int:
    orden = {f"{lo}-{hi}": i for i, (lo, hi) in enumerate(TRAMOS)}
    orden[">365"] = len(TRAMOS)
    orden["de apertura (>365)"] = len(TRAMOS) + 1
    return orden.get(t, 99)


# ================================================================= salida ==


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("diario")
    p.add_argument("--cierre", help="fecha de referencia del aging (AAAA-MM-DD)")
    p.add_argument("--ir-t", type=_num, default=None)
    p.add_argument("--cobertura", type=float, default=UMBRAL_COBERTURA)
    p.add_argument("--dias-alerta", type=int, default=DIAS_ALERTA)
    p.add_argument("--nivel", type=int, default=3)
    p.add_argument("--json")
    args = p.parse_args()

    df, _ = LD.cargar(args.diario)
    an = "=" * 76
    print(an)
    print("PUNTEO, PLAZOS DE LIQUIDACION Y PARTIDAS ABIERTAS")
    print(an)

    g = LD.grupos_punteo(df)
    if g is None:
        motivo = ("el diario no trae columna Indice"
                  if "Indice" not in df.columns else
                  "la columna Indice esta toda a cero")
        print(f"  SIN PUNTEO: {motivo}.")
        print("  La opcion de punteo no se activo al importar el diario en Gesia.")
        print("  El panel saldra sin plazos de liquidacion ni antiguedad de")
        print("  partidas abiertas. Reimportar con la opcion activada los recupera.")
        print(an)
        print("VEREDICTO: SIN PUNTEO")
        print(an)
        if args.json:
            Path(args.json).write_text(
                json.dumps({"punteo": False, "motivo": motivo}, indent=2,
                           ensure_ascii=False), encoding="utf-8")
        return 2

    ap = LD.detectar_apertura(df)
    cierre = pd.Timestamp(args.cierre) if args.cierre else df["FECHA"].max()

    cob = cobertura(df, g, args.nivel)
    evaluables = cob[cob["lineas"] >= MIN_LINEAS]
    suficientes = set(evaluables[evaluables["pct_cancelado"] >= args.cobertura].index)
    insuficientes = set(evaluables[evaluables["pct_cancelado"] < args.cobertura].index)
    punteables = set(cob.index)
    # Grupos cuyo plazo se apoya en pocas partidas reales: la mayor parte de su
    # punteo es masivo, asi que el plazo es poco representativo.
    plazo_debil = set(
        evaluables[evaluables["pct_partidas"] < args.cobertura / 2].index
    )

    pl = plazos(df, g, args.nivel)
    ag = aging(df, cierre, ap["mask"] if ap["verificada"] else None,
               punteables, args.nivel)

    descuadrados = int((~g["cuadra"]).sum())
    masivos = g[g["masivo"]]
    utiles = g[~g["masivo"]]
    multiples = utiles[utiles["lineas"] > 2]

    # ---------------------------------------------------------- resumen ----
    print(f"  grupos de punteo        {num(len(g))}")
    print(f"  de ellos, partidas      {num(len(utiles))}")
    print(f"  de ellos, masivos       {len(masivos)}   (la cuenta neteandose "
          "consigo misma: excluidos)")
    print(f"  importe de partidas     {eur(float(utiles['importe'].sum()))}")
    print(f"  grupos sin netear       {descuadrados}")
    print(f"  punteos multiples       {len(multiples)} partidas con mas de dos lineas")
    print(f"  apertura                {'verificada' if ap['verificada'] else 'NO detectada'}")
    print(f"  fecha de referencia     {cierre.date()}")
    print()

    print(f"COBERTURA DE PUNTEO (nivel {args.nivel}, minimo {MIN_LINEAS} lineas)")
    print(f"  {'grupo':6s} {'cancelado':>10s} {'en partidas':>12s} "
          f"{'lineas':>8s}  para el aging")
    for grupo, r in evaluables.head(MAX_LISTA).iterrows():
        marca = ("suficiente" if r["pct_cancelado"] >= args.cobertura
                 else "INSUFICIENTE")
        print(f"  {grupo:6s} {r['pct_cancelado']:>9.1f}% {r['pct_partidas']:>11.1f}% "
              f"{num(r['lineas']):>8s}  {marca}")
    if len(cob) > len(evaluables):
        print(f"  ({len(cob) - len(evaluables)} grupos con menos de {MIN_LINEAS} "
              "lineas no se evaluan)")
    print()

    print("PLAZOS DE LIQUIDACION SEGUN EL PUNTEO DE GESIA")
    print(f"  {'grupo':6s} {'partidas':>9s} {'mediana':>8s} {'media':>8s} "
          f"{'p90':>7s} {'maximo':>7s}  {'> ' + str(args.dias_alerta) + ' d':>8s}")
    con_muestra = pl[pl["muestra_suficiente"]]
    for grupo, r in con_muestra.head(MAX_LISTA).iterrows():
        sub = utiles.reset_index()
        sub = sub[sub["CUENTA"].str[:args.nivel] == grupo]
        lentas = int((sub["dias"] > args.dias_alerta).sum())
        nota = "  (poco representativo: casi todo su punteo es masivo)" \
            if grupo in plazo_debil else ""
        print(f"  {grupo:6s} {num(r['grupos']):>9s} {r['mediana']:>8.0f} "
              f"{r['media']:>8.1f} {r['p90']:>7.0f} {num(r['maximo']):>7s} "
              f"{num(lentas):>8s}{nota}")
    sin_muestra = pl[~pl["muestra_suficiente"]]
    if len(sin_muestra):
        print(f"  ({len(sin_muestra)} grupos con menos de {MIN_PARTIDAS} partidas "
              "no se resumen: "
              + ", ".join(sin_muestra.index.tolist()[:MAX_LISTA]) + ")")
    print()

    # ------------------------------------------------------------ aging ----
    publicable = ap["verificada"]
    if not publicable:
        print("ANTIGUEDAD DE PARTIDAS ABIERTAS: SUPRIMIDA")
        print("  No hay apertura verificada. Los pagos que cancelan facturas del")
        print("  ejercicio anterior se quedan sin contrapartida y apareceren como")
        print("  abiertos, de modo que la antiguedad estaria sobreestimada de forma")
        print("  sistematica. Reimportar el diario con la opcion de apertura")
        print("  activada la habilita.")
        print()
    elif ag.empty:
        print("ANTIGUEDAD DE PARTIDAS ABIERTAS: no hay partidas sin puntear.")
        print()
    else:
        print("ANTIGUEDAD DE PARTIDAS ABIERTAS")
        for grupo in ag["grupo"].drop_duplicates().tolist()[:6]:
            sub = ag[ag["grupo"] == grupo].copy()
            sub["ord"] = sub["tramo"].map(orden_tramo)
            sub = sub.sort_values("ord")
            total = float(sub["neto"].sum())
            pct = float(cob.loc[grupo, "pct_cancelado"]) if grupo in cob.index else 0.0
            con_cifra = grupo in suficientes
            cab = (f"  {grupo}  cobertura {pct:.1f}%  ->  "
                   + (f"saldo abierto {eur(total)}" if con_cifra
                      else "SIN CIFRA DE CABECERA (cobertura por debajo del "
                           f"{args.cobertura:.0f}%)"))
            print(cab)
            for _, r in sub.iterrows():
                # El separador de miles de eur() ya es un espacio: aplicar
                # .replace(",", ".") sobre la linea completa le rompia los
                # decimales, asi que el recuento se formatea aparte.
                print(f"        {r['tramo']:>20s}  {num(r['apuntes']):>5s} apuntes  "
                      f"{eur(r['neto']):>18s}")
        print()

    if len(masivos):
        print("PUNTEOS MASIVOS EXCLUIDOS")
        print("  Grupos que absorben mas de la mitad de las lineas de su cuenta:")
        print("  no son emparejamientos de partidas, sino la cuenta neteandose")
        print("  consigo misma. Su 'plazo' es solo la duracion del ejercicio.")
        for (cuenta, indice), r in masivos.sort_values(
                "lineas", ascending=False).head(6).iterrows():
            print(f"    {cuenta}  Indice {indice:>4}  {num(r['lineas']):>5s} de "
                  f"{num(r['lineas_cuenta'])} lineas "
                  f"({r['peso_en_cuenta'] * 100:.0f}%)  {eur(r['importe'])}")
        print()

    if len(multiples):
        print("PUNTEOS MULTIPLES (mas de dos lineas: pagos parciales o agrupados)")
        top = multiples.sort_values("importe", ascending=False).head(5)
        for (cuenta, indice), r in top.iterrows():
                print(f"    {cuenta}  Indice {indice:>4}  {int(r['lineas']):>3} lineas  "
                  f"{eur(r['importe']):>16s}  {int(r['dias']):>4} dias")
        print()

    veredicto = ("SIN AGING (falta apertura)" if not publicable else
                 "PUBLICABLE CON LIMITACIONES" if insuficientes else "PUBLICABLE")
    print(an)
    print(f"VEREDICTO: {veredicto}")
    print(an)

    if args.json:
        Path(args.json).write_text(
            json.dumps(
                {
                    "punteo": True,
                    "nivel": args.nivel,
                    "fecha_referencia": str(cierre.date()),
                    "umbral_cobertura": args.cobertura,
                    "dias_alerta": args.dias_alerta,
                    "ir_t": args.ir_t,
                    "apertura_verificada": ap["verificada"],
                    "aging_publicable": publicable,
                    "advertencia": "los plazos y la antiguedad proceden del punteo "
                                   "automatico de Gesia: son una lista de revision, "
                                   "no una medida contable",
                    "resumen": {
                        "grupos_punteo": int(len(g)),
                        "importe_punteado": round(float(g["importe"].sum()), 2),
                        "grupos_sin_netear": descuadrados,
                        "partidas": int(len(utiles)),
                    "punteos_masivos": int(len(masivos)),
                    "importe_partidas": round(float(utiles["importe"].sum()), 2),
                    "punteos_multiples": int(len(multiples)),
                        "grupos_cobertura_suficiente": sorted(suficientes),
                        "grupos_cobertura_insuficiente": sorted(insuficientes),
                    },
                    "cobertura": cob.reset_index().to_dict(orient="records"),
                    "plazos": pl.reset_index().to_dict(orient="records"),
                    "aging": ag.to_dict(orient="records"),
                },
                indent=2, ensure_ascii=False, default=str,
            ),
            encoding="utf-8",
        )
        print(f"punteo escrito en {args.json}")

    return 0 if veredicto == "PUBLICABLE" else (2 if not publicable else 1)


if __name__ == "__main__":
    sys.exit(main())
