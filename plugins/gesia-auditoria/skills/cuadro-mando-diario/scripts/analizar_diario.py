#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fase 2c: ANALISIS DEL DIARIO — evolucion, actividad y apuntes atipicos.

Principio de diseno: los atipicos se miden contra la linea base DEL PROPIO
CLIENTE, no contra reglas universales. Un diario con 5.567 apuntes en fin de
semana no tiene 5.567 hallazgos: tiene un cliente que trabaja los fines de
semana. Lo que interesa es el sabado que se sale de su propia distribucion de
sabados.

Secciones:
  A  evolucion mensual
  B  perfil semanal y dias con actividad anomala (z robusto por dia de semana)
  C  tipo de asiento por firma de contrapartidas del PGC, no por el concepto
     (el concepto de un ERP real es intratable: "TALON", "CARPETA DIA", vacio)
  D  atipicos: apuntes materiales, duplicados, importes redondos, Benford,
     concentracion en el cierre y contrapartidas raras

Uso:
    analizar_diario.py <diario.smn> [--cierre AAAA-MM-DD] [--ir-t 200000]
                       [--json salida.json]

Codigo de salida: 0 siempre que el diario se pueda leer. Este modulo describe,
no dictamina: el que dictamina es el verificador de contrato.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

import lib_diario as LD

MAX_LISTA = 10
Z_ATIPICO = 3.5          # z robusto (Iglewicz-Hoaglin) para marcar un dia
PCT_TRIVIAL_IR_T = 5.0   # % de IR_T por debajo del cual un apunte no interesa
DIAS_CIERRE = 7          # ultimos dias del ejercicio que cuentan como "cierre"
REDONDO = 1000.0
TOPE_MARCADOS = 150      # filas por marca que se exportan al panel

DIAS = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]

# Frecuencias esperadas del primer digito segun Benford.
BENFORD = {d: math.log10(1 + 1 / d) for d in range(1, 10)}


def eur(v: float) -> str:
    return f"{v:,.2f}".replace(",", " ").replace(".", ",") + " EUR"


def num(v) -> str:
    return f"{int(v):,}".replace(",", ".")


def _num(txt) -> float:
    if txt in (None, ""):
        return 0.0
    return float(str(txt).strip().replace(" ", "").replace(",", "."))


# =============================================================== A. mensual ==


def mensual(df: pd.DataFrame) -> pd.DataFrame:
    m = df.groupby(df["FECHA"].dt.month, sort=True).agg(
        apuntes=("NETO", "size"),
        asientos=("ASIENTO", "nunique"),
        volumen=("VOL", "sum"),
    )
    m["pct_volumen"] = (m["volumen"] / m["volumen"].sum() * 100).round(1)
    return m


# ============================================================== B. semanal ==


def perfil_semanal(df: pd.DataFrame) -> pd.DataFrame:
    return df.groupby("DOW", sort=True).agg(
        apuntes=("NETO", "size"),
        asientos=("ASIENTO", "nunique"),
        volumen=("VOL", "sum"),
    )


def serie_diaria(df: pd.DataFrame, atipicos: pd.DataFrame) -> pd.DataFrame:
    """Un registro por dia con movimiento: es lo que dibuja el calendario."""
    d = (
        df.groupby(df["FECHA"].dt.normalize().rename("fecha"), sort=True)
        .agg(apuntes=("NETO", "size"), asientos=("ASIENTO", "nunique"),
             volumen=("VOL", "sum"))
        .reset_index()
    )
    d["volumen"] = d["volumen"].round(2)
    d["dow"] = d["fecha"].dt.dayofweek
    marcados = dict(zip(atipicos["fecha"], atipicos["z"])) if not atipicos.empty else {}
    # NaN no es JSON valido: JSON.parse lo rechaza y el panel no cargaria. Los
    # dias sin marca llevan None explicito.
    d["z"] = d["fecha"].map(marcados).astype(object).where(
        d["fecha"].isin(marcados.keys()), None
    )
    d["fin_de_mes"] = d["fecha"].dt.is_month_end
    return d


def dias_atipicos(df: pd.DataFrame) -> pd.DataFrame:
    """
    Dias cuya actividad se sale de la distribucion de SU MISMO dia de la semana.

    Se usa z robusto (mediana y desviacion absoluta mediana) porque la media y
    la desviacion tipica las arrastra cualquier pico de cierre, y precisamente
    los picos son lo que se busca.
    """
    por_dia = (
        df.groupby([df["FECHA"].dt.normalize().rename("fecha"), "DOW"], sort=True)
        .size().rename("apuntes").reset_index()
    )
    filas = []
    for dow, sub in por_dia.groupby("DOW", sort=True):
        med = sub["apuntes"].median()
        mad = (sub["apuntes"] - med).abs().median()
        if mad == 0:
            continue
        z = 0.6745 * (sub["apuntes"] - med) / mad
        s = sub.assign(mediana=med, z=z.round(1))
        filas.append(s[s["z"].abs() >= Z_ATIPICO])
    if not filas:
        return pd.DataFrame()
    out = pd.concat(filas)
    # Marcar el ultimo dia natural del mes: en la practica casi todos los picos
    # de un diario real son cierres mensuales, y decirlo convierte una lista de
    # fechas en una explicacion.
    out["fin_de_mes"] = out["fecha"].dt.is_month_end
    return out.sort_values("z", ascending=False, key=lambda s: s.abs())


# ================================================== C. tipo por firma PGC ==


def _empieza(grupos: frozenset, *prefijos: str) -> bool:
    return any(g.startswith(p) for g in grupos for p in prefijos)


def clasificar(debe: frozenset, haber: frozenset, es_apertura: bool) -> str:
    """
    Tipo de asiento deducido de QUE grupos del PGC toca en cada lado.

    Es robusto donde el concepto no lo es: un asiento que carga un 6 y abona un
    40 es una compra, escriba el ERP lo que quiera en la descripcion.
    """
    if es_apertura:
        return "Apertura"
    d, h = debe, haber
    # Nomina y amortizacion ANTES de compra/gasto: un asiento de nomina carga un
    # 64 y abona 465/476/475, asi que la regla generica de gasto se lo tragaba y
    # la nomina desaparecia del cuadro.
    if _empieza(d, "64", "642", "649"):
        return "Nomina y personal"
    if _empieza(d, "68"):
        return "Amortizacion"
    if _empieza(d, "6") and _empieza(h, "40", "41", "47", "46"):
        return "Compra / gasto"
    if _empieza(d, "40", "41") and _empieza(h, "57", "52", "56"):
        return "Pago a proveedor"
    if _empieza(d, "43", "44") and _empieza(h, "70", "71", "74", "75", "77"):
        return "Venta / ingreso"
    if _empieza(d, "57") and _empieza(h, "43", "44"):
        return "Cobro de cliente"
    if _empieza(d, "2") or _empieza(h, "2"):
        return "Inmovilizado"
    if _empieza(d, "47") or _empieza(h, "47"):
        return "Liquidacion fiscal"
    if _empieza(d, "10", "11", "12", "13") or _empieza(h, "10", "11", "12", "13"):
        return "Patrimonio neto"
    if _empieza(d, "66") or _empieza(h, "76"):
        return "Financiero"
    if _empieza(d, "3") or _empieza(h, "3"):
        return "Existencias"
    if _empieza(d, "57") or _empieza(h, "57"):
        return "Movimiento de tesoreria"
    return "Otros"


def tipos_asiento(df: pd.DataFrame, ap_asientos: set[str]) -> pd.DataFrame:
    d = df[df["NETO"] > 0].groupby("ASIENTO", sort=True)["G2"].apply(frozenset)
    h = df[df["NETO"] < 0].groupby("ASIENTO", sort=True)["G2"].apply(frozenset)
    vacio = frozenset()
    asientos = sorted(set(df["ASIENTO"]))
    tipo = {
        a: clasificar(d.get(a, vacio), h.get(a, vacio), a in ap_asientos)
        for a in asientos
    }
    t = df.assign(tipo=df["ASIENTO"].map(tipo))
    out = t.groupby("tipo", sort=True).agg(
        apuntes=("NETO", "size"),
        asientos=("ASIENTO", "nunique"),
        volumen=("VOL", "sum"),
    )
    out["pct_volumen"] = (out["volumen"] / out["volumen"].sum() * 100).round(1)
    # Tambien por mes: sin esto el filtro de meses del panel no podria alcanzar
    # a este cuadro, y una fila de filtros que no afecta a todo lo que tiene
    # debajo engana.
    por_mes = (
        t.groupby([t["FECHA"].dt.month.rename("mes"), "tipo"], sort=True)
        .agg(apuntes=("NETO", "size"), asientos=("ASIENTO", "nunique"),
             volumen=("VOL", "sum"))
        .reset_index()
    )
    por_mes["volumen"] = por_mes["volumen"].round(2)
    return out.sort_values("volumen", ascending=False), por_mes


# ============================================================= D. atipicos ==


def apuntes_materiales(df: pd.DataFrame, ir_t: float | None) -> pd.DataFrame:
    if not ir_t:
        return pd.DataFrame()
    sel = df[df["VOL"] >= ir_t]
    return sel.sort_values("VOL", ascending=False)


def duplicados(df: pd.DataFrame, minimo: float) -> pd.DataFrame:
    """
    Mismo dia, misma cuenta, mismo importe y mismo concepto, en asientos
    distintos. Filtrado por importe para que no lo inunden las cuotas
    recurrentes de tres euros.
    """
    cols = ["FECHA", "CUENTA", "DEBE", "HABER"]
    if "CONCEPTO" in df.columns:
        cols.append("CONCEPTO")
    sel = df[df["VOL"] >= minimo]
    if sel.empty:
        return pd.DataFrame()
    g = sel.groupby(cols, sort=True).agg(
        veces=("ASIENTO", "nunique"), importe=("VOL", "first"),
        asientos=("ASIENTO", lambda s: sorted(set(s))[:4]),
    )
    g = g[g["veces"] > 1].reset_index()
    return g.sort_values("importe", ascending=False)


def redondos(df: pd.DataFrame) -> dict:
    sel = df[(df["VOL"] >= REDONDO) & (df["VOL"] % REDONDO == 0)]
    grandes = df[df["VOL"] >= REDONDO]
    return {
        "apuntes": int(len(sel)),
        "sobre_apuntes_de_mas_de_mil": int(len(grandes)),
        "pct": round(len(sel) / len(grandes) * 100, 2) if len(grandes) else 0.0,
        "importe": round(float(sel["VOL"].sum()), 2),
        "grupos": {str(k): int(v) for k, v in
                   sel["G2"].value_counts().head(5).items()},
    }


def benford(df: pd.DataFrame) -> dict:
    """
    Primer digito frente a Benford, con la desviacion media absoluta (MAD) y
    los cortes de Nigrini. Solo sobre importes de tres cifras o mas: por debajo
    la ley no aplica bien.
    """
    v = df.loc[df["VOL"] >= 100, "VOL"]
    if len(v) < 500:
        return {"aplicable": False, "motivo": "menos de 500 importes >= 100 EUR"}
    primero = v.map(lambda x: int(str(int(x))[0]))
    obs = primero.value_counts(normalize=True).reindex(range(1, 10)).fillna(0)
    mad = float((obs - pd.Series(BENFORD)).abs().mean())
    if mad < 0.006:
        ajuste = "conforme"
    elif mad < 0.012:
        ajuste = "aceptable"
    elif mad < 0.015:
        ajuste = "dudoso"
    else:
        ajuste = "NO CONFORME"
    desv = (obs - pd.Series(BENFORD)) * 100
    peores = desv.abs().sort_values(ascending=False).head(3).index.tolist()
    return {
        "aplicable": True,
        "importes": int(len(v)),
        "mad": round(mad, 5),
        "ajuste": ajuste,
        "digitos_mas_desviados": [
            {"digito": int(d), "observado_pct": round(float(obs[d]) * 100, 2),
             "esperado_pct": round(BENFORD[d] * 100, 2),
             "desviacion_pp": round(float(desv[d]), 2)} for d in peores
        ],
        "observado": {str(d): round(float(obs[d]) * 100, 2) for d in range(1, 10)},
        "esperado": {str(d): round(BENFORD[d] * 100, 2) for d in range(1, 10)},
    }


def cierre_concentrado(df: pd.DataFrame, cierre: pd.Timestamp, dias: int) -> dict:
    ini = cierre - pd.Timedelta(days=dias - 1)
    sel = df[df["FECHA"] >= ini]
    return {
        "desde": str(ini.date()),
        "apuntes": int(len(sel)),
        "pct_apuntes": round(len(sel) / len(df) * 100, 2),
        "volumen": round(float(sel["VOL"].sum()), 2),
        "pct_volumen": round(float(sel["VOL"].sum() / df["VOL"].sum() * 100), 2),
        "asientos": int(sel["ASIENTO"].nunique()),
    }


def marcados(df: pd.DataFrame, dup: pd.DataFrame, ir_t: float | None,
             trivial: float) -> dict:
    """
    Apuntes con marca, para que el panel pueda mostrarlos uno a uno.

    Se exporta el TOTAL de cada marca y solo las TOPE_MARCADOS filas de mayor
    importe. Un diario puede tener miles de apuntes en fin de semana —el de
    un expediente real tenia 5.567— y volcarlos todos ni cabe ni se lee; pero el recuento
    completo tiene que viajar, porque es el que dice si la marca es una
    excepcion o el modo de operar del cliente.
    """
    marcas: dict[str, pd.DataFrame] = {}

    marcas["fin de semana"] = df[df["DOW"].isin([5, 6])]
    marcas["importe redondo"] = df[(df["VOL"] >= REDONDO) & (df["VOL"] % REDONDO == 0)]
    if ir_t:
        marcas["supera IR_T"] = df[df["VOL"] >= ir_t]
    if not dup.empty:
        clave = [c for c in ("FECHA", "CUENTA", "DEBE", "HABER", "CONCEPTO")
                 if c in dup.columns and c in df.columns]
        marcas["duplicado"] = df.merge(dup[clave].drop_duplicates(), on=clave,
                                       how="inner")

    cols = [c for c in ("FECHA", "ASIENTO", "CUENTA", "NOMBRE", "CONCEPTO",
                        "DOW", "VOL", "NETO") if c in df.columns]
    salida: dict = {"tope_por_marca": TOPE_MARCADOS, "totales": {}, "apuntes": []}
    vistos: dict[tuple, dict] = {}
    for nombre, sel in marcas.items():
        salida["totales"][nombre] = {
            "apuntes": int(len(sel)),
            "importe": round(float(sel["VOL"].sum()), 2),
        }
        for _, r in sel.nlargest(TOPE_MARCADOS, "VOL")[cols].iterrows():
            # La clave incluye NETO con signo: las dos patas de un asiento
            # comparten fecha, cuenta e importe y se pisaban entre si.
            k = (str(r["FECHA"]), str(r["ASIENTO"]), str(r["CUENTA"]),
                 float(r["NETO"]), str(r.get("CONCEPTO", "")))
            if k not in vistos:
                vistos[k] = {
                    "fecha": str(r["FECHA"])[:10],
                    "asiento": str(r["ASIENTO"]),
                    "cuenta": str(r["CUENTA"]),
                    "nombre": str(r.get("NOMBRE", "") or ""),
                    "concepto": str(r.get("CONCEPTO", "") or ""),
                    "dow": int(r["DOW"]),
                    "importe": round(float(r["VOL"]), 2),
                    "neto": round(float(r["NETO"]), 2),
                    "marcas": [],
                }
            if nombre not in vistos[k]["marcas"]:
                vistos[k]["marcas"].append(nombre)
    salida["apuntes"] = sorted(vistos.values(), key=lambda x: -x["importe"])
    return salida


def contrapartidas_raras(df: pd.DataFrame, minimo: float) -> pd.DataFrame:
    """Pares (grupo al debe, grupo al haber) que apenas se repiten."""
    pares = Counter()
    importes: dict = {}
    ejemplos: dict = {}
    for asi, g in df[df["VOL"] >= minimo].groupby("ASIENTO", sort=True):
        D = sorted(set(g.loc[g["NETO"] > 0, "G2"]))
        H = sorted(set(g.loc[g["NETO"] < 0, "G2"]))
        vol = float(g["VOL"].sum()) / 2
        for a in D:
            for b in H:
                if a == b:
                    # Un asiento que toca el mismo grupo en los dos lados genera
                    # un par consigo mismo que no dice nada.
                    continue
                pares[(a, b)] += 1
                # El importe es el del mayor asiento con esa combinacion, no la
                # suma: un asiento con seis grupos al debe y ocho al haber
                # generaria 48 pares y sumar su volumen en cada uno lo
                # multiplicaria por 48.
                if vol > importes.get((a, b), 0.0):
                    importes[(a, b)] = vol
                    ejemplos[(a, b)] = str(asi)
    if not pares:
        return pd.DataFrame()
    filas = [
        {"debe": a, "haber": b, "veces": n,
         "importe_mayor_asiento": round(importes[(a, b)], 2),
         "ejemplo": ejemplos[(a, b)]}
        for (a, b), n in pares.items()
    ]
    out = pd.DataFrame(filas)
    out = out[out["veces"] <= 2].sort_values("importe_mayor_asiento",
                                             ascending=False)
    # Un solo asiento con varios grupos a cada lado produce varios pares unicos
    # que son el mismo hallazgo. De los que aparecen una sola vez se conserva
    # una fila por asiento.
    unicos = out[out["veces"] == 1].drop_duplicates(subset="ejemplo", keep="first")
    return pd.concat([out[out["veces"] > 1], unicos]).sort_values(
        "importe_mayor_asiento", ascending=False)


# ================================================================= salida ==


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("diario")
    p.add_argument("--cierre")
    p.add_argument("--ir-t", type=_num, default=None)
    p.add_argument("--json")
    args = p.parse_args()

    df, _ = LD.cargar(args.diario)
    cierre = pd.Timestamp(args.cierre) if args.cierre else df["FECHA"].max()
    trivial = (args.ir_t * PCT_TRIVIAL_IR_T / 100.0) if args.ir_t else 1000.0
    ap = LD.detectar_apertura(df)
    ap_asientos = set(ap["asientos"]) if ap["verificada"] else set()

    an = "=" * 78
    print(an)
    print("ANALISIS DEL DIARIO")
    print(an)
    print(f"  apuntes {num(len(df))}   asientos {num(df['ASIENTO'].nunique())}   "
          f"volumen neto {eur(float(df['VOL'].sum()))}")
    print(f"  umbral de interes: {eur(trivial)}"
          + (f"  ({PCT_TRIVIAL_IR_T:.0f}% de IR_T)" if args.ir_t else "  (sin IR_T)"))
    print()

    # ------------------------------------------------------------- A ------
    m = mensual(df)
    print("A. EVOLUCION MENSUAL")
    print(f"  {'mes':>4s} {'apuntes':>9s} {'asientos':>9s} {'volumen':>20s} {'%':>6s}")
    for mes, r in m.iterrows():
        print(f"  {mes:>4d} {num(r['apuntes']):>9s} {num(r['asientos']):>9s} "
              f"{eur(r['volumen']):>20s} {r['pct_volumen']:>5.1f}%")
    print()

    # ------------------------------------------------------------- B ------
    ps = perfil_semanal(df)
    print("B. PERFIL SEMANAL")
    for dow, r in ps.iterrows():
        pct = r["apuntes"] / len(df) * 100
        print(f"  {DIAS[int(dow)]:>10s} {num(r['apuntes']):>8s} apuntes "
              f"({pct:>4.1f}%)  {eur(r['volumen']):>20s}")
    fin_de_semana = int(df["DOW"].isin([5, 6]).sum())
    print(f"  fin de semana: {num(fin_de_semana)} apuntes "
          f"({fin_de_semana / len(df) * 100:.1f}%). Es el patron habitual de este "
          "cliente,")
    print("  no un hallazgo: lo que se marca abajo son los dias que se salen de su")
    print("  propia distribucion.")
    print()

    da = dias_atipicos(df)
    print(f"   DIAS CON ACTIVIDAD ANOMALA (z robusto >= {Z_ATIPICO})")
    if da.empty:
        print("   ninguno: la actividad diaria es homogenea dentro de cada dia "
              "de la semana")
    else:
        fdm = int(da["fin_de_mes"].sum())
        print(f"   {len(da)} dias anomalos, de los cuales {fdm} son el ultimo dia "
              "natural del mes:")
        print("   el cliente concentra trabajo en el cierre mensual. Los que NO "
              "son fin de mes")
        print("   son los que merecen una explicacion.")
        for _, r in da.head(MAX_LISTA).iterrows():
            marca = "cierre de mes" if r["fin_de_mes"] else "<-- REVISAR"
            print(f"   {r['fecha'].date()}  {DIAS[int(r['DOW'])]:>10s}  "
                  f"{num(r['apuntes']):>5s} apuntes frente a una mediana de "
                  f"{num(r['mediana']):>4s}   z={r['z']:+6.1f}   {marca}")
        otros = da[~da["fin_de_mes"]]
        if len(otros) > MAX_LISTA:
            print(f"   (hay {len(otros)} dias anomalos que no son cierre de mes; "
                  "todos en el JSON)")
    print()

    # ------------------------------------------------------------- C ------
    tp, tp_mes = tipos_asiento(df, ap_asientos)
    print("C. TIPO DE ASIENTO (deducido de las contrapartidas del PGC)")
    print(f"  {'tipo':26s} {'asientos':>9s} {'apuntes':>9s} {'volumen':>20s} {'%':>6s}")
    for tipo, r in tp.head(MAX_LISTA + 2).iterrows():
        print(f"  {tipo:26s} {num(r['asientos']):>9s} {num(r['apuntes']):>9s} "
              f"{eur(r['volumen']):>20s} {r['pct_volumen']:>5.1f}%")
    print()

    # ------------------------------------------------------------- D ------
    # El asiento de apertura no es una transaccion: son saldos iniciales. Si se
    # deja dentro, copa los apuntes materiales y genera cientos de
    # contrapartidas "raras" que no son mas que la apertura cruzando todos los
    # grupos entre si.
    sin_ap = df[~ap["mask"]] if ap["mask"] is not None else df
    print("D. APUNTES ATIPICOS")
    if ap["mask"] is not None:
        print(f"   (excluido el asiento de apertura: {ap['apuntes']} apuntes de "
              "saldos iniciales, que no son transacciones)")

    mat = apuntes_materiales(sin_ap, args.ir_t)
    print(f"   D1 apuntes de importe superior a IR_T: {len(mat)}")
    for _, r in mat.head(6).iterrows():
        con = (r.get("CONCEPTO") or "")[:34]
        print(f"      {r['FECHA'].date()}  as.{r['ASIENTO']:>7s}  {r['CUENTA']}  "
              f"{eur(r['VOL']):>18s}  {con}")

    dup = duplicados(sin_ap, trivial)
    print(f"   D2 duplicados exactos por encima del umbral: {len(dup)} grupos")
    for _, r in dup.head(5).iterrows():
        print(f"      {r['FECHA'].date()}  {r['CUENTA']}  {eur(r['importe']):>16s}  "
              f"x{int(r['veces'])}  asientos {r['asientos']}")

    rd = redondos(sin_ap)
    print(f"   D3 importes multiplo de 1.000: {num(rd['apuntes'])} de "
          f"{num(rd['sobre_apuntes_de_mas_de_mil'])} apuntes de mas de 1.000 EUR "
          f"({rd['pct']}%)")

    bf = benford(sin_ap)
    if bf["aplicable"]:
        print(f"   D4 Benford del primer digito: MAD {bf['mad']:.5f} -> "
              f"{bf['ajuste']}  ({num(bf['importes'])} importes)")
        for d in bf["digitos_mas_desviados"]:
            print(f"      digito {d['digito']}: {d['observado_pct']:.1f}% "
                  f"observado frente a {d['esperado_pct']:.1f}% esperado "
                  f"({d['desviacion_pp']:+.1f} pp)")
        print("      La no conformidad NO es por si misma un indicio de "
              "manipulacion: en un")
        print("      negocio con importes repetidos (cobros diarios, cuotas "
              "fijas) es frecuente.")
        print("      Es una pregunta que hacer, no una conclusion.")
    else:
        print(f"   D4 Benford: no aplicable ({bf['motivo']})")

    cc = cierre_concentrado(df, cierre, DIAS_CIERRE)
    print(f"   D5 ultimos {DIAS_CIERRE} dias del ejercicio: {num(cc['apuntes'])} "
          f"apuntes ({cc['pct_apuntes']}%) y {cc['pct_volumen']}% del volumen")

    mk = marcados(sin_ap, dup, args.ir_t, trivial)
    print(f"   D7 apuntes con marca: "
          + ", ".join(f"{k} {num(v['apuntes'])}" for k, v in mk["totales"].items())
          + f"  (se exportan las {TOPE_MARCADOS} mayores de cada marca)")
    cr = contrapartidas_raras(sin_ap, trivial)
    print(f"   D6 contrapartidas que apenas se repiten: {len(cr)} pares")
    for _, r in cr.head(6).iterrows():
        print(f"      {r['debe']} -> {r['haber']}   {int(r['veces'])}x   "
              f"{eur(r['importe_mayor_asiento']):>16s}   ej. asiento {r['ejemplo']}")
    print()
    print(an)

    def limpio(o):
        """Sustituye NaN e Infinity por None en todo el arbol: json.dumps los
        escribe como literales que JSON.parse no acepta."""
        if isinstance(o, dict):
            return {k: limpio(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [limpio(v) for v in o]
        if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
            return None
        return o

    if args.json:
        Path(args.json).write_text(
            json.dumps(
                {
                    "ir_t": args.ir_t,
                    "umbral_interes": round(trivial, 2),
                    "fecha_cierre": str(cierre.date()),
                    "mensual": m.reset_index().rename(
                        columns={"FECHA": "mes"}).to_dict(orient="records"),
                    "perfil_semanal": [
                        {"dia": DIAS[int(k)], **{c: (round(float(v), 2)
                                                    if c == "volumen" else int(v))
                                                 for c, v in r.items()}}
                        for k, r in ps.iterrows()
                    ],
                    "serie_diaria": (
                        serie_diaria(df, da)
                        .assign(fecha=lambda x: x["fecha"].astype(str).str[:10])
                        .to_dict(orient="records")
                    ),
                    "dias_atipicos": (
                        da.assign(fecha=da["fecha"].astype(str))
                        .to_dict(orient="records") if not da.empty else []
                    ),
                    "tipos_asiento": tp.reset_index().to_dict(orient="records"),
                    "tipos_por_mes": tp_mes.to_dict(orient="records"),
                    "atipicos": {
                        "materiales": len(mat),
                        # Sin --ir-t, apuntes_materiales devuelve un frame vacio
                        # y SIN columnas, asi que el assign de FECHA petaba con
                        # KeyError. Y no pasar --ir-t es el uso normal cuando el
                        # expediente tiene IR_T = 0, que ocurre siempre que no se
                        # ha fijado materialidad de trabajo. Visto en cliente el
                        # 23/08/2026; los tres bloques vecinos ya se guardaban.
                        "materiales_detalle": (
                            mat.head(30)[
                                [c for c in ("FECHA", "ASIENTO", "CUENTA", "NOMBRE",
                                             "CONCEPTO", "VOL") if c in mat.columns]
                            ].assign(FECHA=lambda x: x["FECHA"].astype(str))
                            .to_dict(orient="records") if not mat.empty else []
                        ),
                        "duplicados": len(dup),
                        "duplicados_detalle": (
                            dup.head(30).assign(
                                FECHA=lambda x: x["FECHA"].astype(str)
                            ).to_dict(orient="records") if not dup.empty else []
                        ),
                        "redondos": rd,
                        "benford": bf,
                        "cierre": cc,
                        "marcados": mk,
                        "contrapartidas_raras": (
                            cr.head(30).to_dict(orient="records")
                            if not cr.empty else []
                        ),
                    },
                },
                indent=2, ensure_ascii=False, default=str,
            ).replace(": NaN", ": null").replace(": Infinity", ": null")
             .replace(": -Infinity", ": null"),
            encoding="utf-8",
        )
        print(f"analisis escrito en {args.json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

# NOTA SOBRE EL RECUENTO DE IMPORTES REDONDOS
# ------------------------------------------------------------------------------
# Este modulo cuenta los multiplos exactos con aritmetica decimal. Si se
# comprueba la misma cifra con SQL en Access (JET) usando el operador Mod, sale
# mas alta: Mod es un operador ENTERO y redondea sus operandos, de modo que
# 1.999,83 o 10.000,40 se cuentan como "redondos" sin serlo. En el diario de
# un expediente real eso son 17 falsos positivos sobre 28 reales (45 segun JET). Cualquier
# comprobacion cruzada contra el MCP tiene que tenerlo en cuenta.
