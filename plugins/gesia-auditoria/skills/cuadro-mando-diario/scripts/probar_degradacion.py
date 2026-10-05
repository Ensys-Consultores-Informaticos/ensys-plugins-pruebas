#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Arnes de pruebas del verificador de contrato.

Carga un diario real una sola vez y lo muta para reproducir los escenarios que
se dan de verdad en los expedientes, comprobando que el veredicto degrada como
debe en vez de seguir calculando sobre supuestos.

Uso:  probar_degradacion.py <ruta.smn|.mdb>
Salida: una linea por escenario y un recuento de fallos. Codigo 0 si todo pasa.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

import lib_diario as LD
import verificar_contrato as VC


# Datos que aporta un expediente real (cuenta 08 e IR_T).
GESIA = {"resultado_08": 591138.25, "anterior": 92832.36,
         "ajustes": -98481.72, "ir_t": 200000.0}


def codigos(inf: VC.Informe) -> set[str]:
    return {h["codigo"] for h in inf.hallazgos if h["nivel"] in (VC.ABORTA, VC.AVISO)}


# ------------------------------------------------------------- escenarios ----


def esc_real(df):
    """Como viene el expediente: punteo y apertura activos."""
    return df.copy(), {}


def esc_apertura_sin_marcar(df):
    """La opcion no se activo pero el asiento de apertura si esta en el diario.
    La cascada debe rescatarlo por fecha minima."""
    d = df.copy()
    d["APERTURA"] = 0.0
    return d, {}


def esc_sin_apertura(df):
    """El asiento de apertura no se importo. El punteo que se apoyaba en el
    queda huerfano y el aging no debe publicarse."""
    d = df.copy()
    ap = d["APERTURA"] != 0
    return d[~ap].reset_index(drop=True), {}


def esc_sin_punteo(df):
    """La opcion de punteo no se activo."""
    d = df.copy()
    d["Indice"] = 0
    return d, {}


def esc_sin_ninguna(df):
    d = df.copy()
    d["Indice"] = 0
    ap = d["APERTURA"] != 0
    return d[~ap].reset_index(drop=True), {}


def esc_sin_columnas_opcionales(df):
    """Diario minimo: solo las cinco columnas obligatorias."""
    d = df.copy()
    return d.drop(columns=[c for c in ("APERTURA", "Indice", "SALDO", "NOMBRE",
                                       "CONCEPTO", "DEBESA", "HABERSA")
                          if c in d.columns]), {
        "columnas_opcionales_ausentes": ["APERTURA", "Indice", "SALDO",
                                         "NOMBRE", "CONCEPTO"],
    }


def esc_descuadrado(df):
    """Un apunte alterado: el diario global ya no cuadra."""
    d = df.copy()
    d.loc[d.index[len(d) // 2], "DEBE"] += 1000.0
    d["NETO"] = d["DEBE"] - d["HABER"]
    d["VOL"] = d["NETO"].abs()
    d["BRUTO"] = d["DEBE"] + d["HABER"]
    return d, {}


def esc_falta_obligatoria(df):
    d = df.copy().drop(columns=["HABER"])
    return d, {"columnas_obligatorias_ausentes": ["HABER"]}


def esc_asiento_no_numerico(df):
    """Numeracion alfanumerica: la correlatividad no se puede comprobar."""
    d = df.copy()
    d["ASIENTO"] = "A" + d["ASIENTO"].astype(str)
    return d, {}


def esc_fuera_de_orden(df):
    """El fichero no esta grabado cronologicamente."""
    d = df.copy()
    d = pd.concat([d.iloc[len(d) // 2:], d.iloc[:len(d) // 2]]).reset_index(drop=True)
    return d, {}


def _reclasificar_a_ingresos(df, minimo, maximo):
    """
    Mueve una linea de balance al grupo 7 cambiandole la cuenta.

    Asi el resultado se desvia SIN romper el cuadre global: Debe y Haber no se
    tocan, solo la clasificacion. Es ademas un error realista (cuenta mal
    asignada en la importacion).
    """
    d = df.copy()
    cand = d[(d["G1"].isin(list("12345"))) & (d["HABER"] > minimo) & (d["HABER"] < maximo)]
    if "APERTURA" in d.columns:
        # Fuera las lineas de apertura: reclasificar una de ellas contaminaria
        # la comprobacion de la apertura y abortaria por otro motivo.
        cand = cand[cand["APERTURA"] == 0]
    if cand.empty:
        raise RuntimeError("sin linea candidata para el escenario")
    victima = cand.index[0]
    d.loc[victima, "CUENTA"] = "70000000"
    for n in (1, 2, 3, 4):
        d[f"G{n}"] = d["CUENTA"].str[:n]
    return d, {}


def esc_resultado_desviado(df):
    """Desviacion del resultado por debajo de la importancia relativa: aviso,
    no aborto, porque puede tratarse de un diario preliminar."""
    return _reclasificar_a_ingresos(df, 50_000, 150_000)


def esc_resultado_incoherente(df):
    """Desviacion por encima de la importancia relativa: el panel contradiria
    al expediente y hay que abortar."""
    return _reclasificar_a_ingresos(df, 250_000, 10_000_000)


def esc_apertura_contaminada(df):
    """Alguien marco como apertura un apunte de resultados: no es una apertura
    y hay que abortar, no seguir."""
    d = df.copy()
    victima = d.index[d["G1"] == "6"][0]
    d.loc[victima, "APERTURA"] = d.loc[victima, "NETO"]
    d.loc[victima, "APERTURA"] = d.loc[victima, "DEBE"] - d.loc[victima, "HABER"]
    return d, {}


ESCENARIOS = [
    # (nombre, funcion, veredicto esperado, codigos que deben aparecer,
    #  aging publicable esperado)
    ("real (punteo + apertura)",      esc_real,                     "CONFORME CON AVISOS", {"P04"},        True),
    ("apertura sin marcar",           esc_apertura_sin_marcar,      "CONFORME CON AVISOS", {"P04"},        True),
    ("sin apertura importada",        esc_sin_apertura,             "CONFORME CON AVISOS", {"P02", "P05"}, False),
    ("sin punteo",                    esc_sin_punteo,               "CONFORME CON AVISOS", set(),          False),
    ("sin punteo ni apertura",        esc_sin_ninguna,              "CONFORME CON AVISOS", set(),          False),
    ("solo columnas obligatorias",    esc_sin_columnas_opcionales,  "CONFORME CON AVISOS", set(),          False),
    ("asiento no numerico",            esc_asiento_no_numerico,      "CONFORME CON AVISOS", {"C12"},        True),
    ("fichero fuera de orden",        esc_fuera_de_orden,           "CONFORME CON AVISOS", {"C13"},        True),
    ("resultado desviado < IR_T",     esc_resultado_desviado,       "CONFORME CON AVISOS", {"C18"},        True),
    ("resultado desviado > IR_T",     esc_resultado_incoherente,    "ABORTAR",             {"C18"},        False),
    ("diario descuadrado",            esc_descuadrado,              "ABORTAR",             {"C10"},        False),
    ("falta columna obligatoria",     esc_falta_obligatoria,        "ABORTAR",             {"C01"},        None),
    ("apertura contaminada con 6xx",  esc_apertura_contaminada,     "ABORTAR",             {"A04"},        False),
]


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    base_df, base_meta = LD.cargar(Path(sys.argv[1]))
    print(f"diario base: {len(base_df):,} apuntes\n".replace(",", "."))

    fallos = 0
    print(f"{'escenario':32s} {'veredicto':22s} {'aging':10s} resultado")
    print("-" * 92)
    for nombre, fn, esperado, codigos_esperados, aging_esperado in ESCENARIOS:
        df, ajustes = fn(base_df)
        meta = dict(base_meta)
        meta["columnas_presentes"] = list(df.columns)
        meta["columnas_obligatorias_ausentes"] = [
            c for c in LD.COLUMNAS_OBLIGATORIAS if c not in df.columns
        ]
        meta["columnas_opcionales_ausentes"] = [
            c for c in LD.COLUMNAS_OPCIONALES if c not in df.columns
        ]
        meta["filas_crudas"] = len(df)
        meta.update({k: v for k, v in ajustes.items() if k != "columnas_obligatorias_ausentes"})

        inf, resumen = VC.analizar(df, meta, cierre="2025-12-31", gesia=GESIA)
        obtenidos = codigos(inf)
        aging = resumen.get("punteo", {}).get("aging_publicable")

        problemas = []
        if inf.veredicto != esperado:
            problemas.append(f"veredicto={inf.veredicto}")
        faltan = codigos_esperados - obtenidos
        if faltan:
            problemas.append("sin " + ",".join(sorted(faltan)))
        if aging_esperado is not None and bool(aging) != aging_esperado:
            problemas.append(f"aging={aging}")

        estado = "OK" if not problemas else "FALLO: " + "; ".join(problemas)
        if problemas:
            fallos += 1
        aging_txt = {True: "publicable", False: "suprimido", None: "-"}[bool(aging) if aging is not None else None]
        print(f"{nombre:32s} {inf.veredicto:22s} {aging_txt:10s} {estado}")

    print("-" * 92)
    print(f"{len(ESCENARIOS) - fallos}/{len(ESCENARIOS)} escenarios correctos")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
