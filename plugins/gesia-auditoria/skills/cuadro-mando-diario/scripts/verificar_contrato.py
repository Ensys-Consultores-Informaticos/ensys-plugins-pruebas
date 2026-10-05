#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fase 1 del cuadro de mando Gesia: VERIFICACION DEL CONTRATO DE DATOS.

Se ejecuta antes de calcular un solo indicador. Su unico trabajo es decidir si
el diario importado permite construir el panel y con que alcance, y abortar si
no lo permite. Un panel bonito sobre datos mal entendidos es peor que no tener
panel.

Uso:
    verificar_contrato.py <ruta.smn|.mdb> [--json salida.json] [--cierre AAAA-MM-DD]

Codigos de salida:
    0  contrato conforme
    1  conforme con avisos: el panel se construye pero degradado
    2  abortar: no se puede construir el panel

Todo lo que imprime esta acotado: ninguna lista supera MAX_LISTA elementos.
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from pathlib import Path

import pandas as pd

import lib_diario as LD

MAX_LISTA = 8          # tope de elementos en cualquier lista impresa
UMBRAL_COBERTURA = 80.0  # % de punteo por debajo del cual el aging no concluye
MIN_LINEAS_GRUPO = 50    # grupos con menos lineas no se evaluan por cobertura

ABORTA, AVISO, INFO, OK = "ABORTA", "AVISO", "INFO", "OK"


class Informe:
    """Acumula hallazgos y decide el veredicto."""

    def __init__(self) -> None:
        self.hallazgos: list[dict] = []

    def add(self, nivel: str, codigo: str, texto: str, datos: dict | None = None) -> None:
        self.hallazgos.append(
            {"nivel": nivel, "codigo": codigo, "texto": texto, "datos": datos or {}}
        )

    @property
    def veredicto(self) -> str:
        if any(h["nivel"] == ABORTA for h in self.hallazgos):
            return "ABORTAR"
        if any(h["nivel"] == AVISO for h in self.hallazgos):
            return "CONFORME CON AVISOS"
        return "CONFORME"

    @property
    def codigo_salida(self) -> int:
        return {"ABORTAR": 2, "CONFORME CON AVISOS": 1, "CONFORME": 0}[self.veredicto]


def _importe(txt: str) -> float:
    """Acepta 591138,25 y 591138.25: Gesia devuelve los importes con coma."""
    return float(str(txt).strip().replace(" ", "").replace(",", "."))


def eur(v: float) -> str:
    return f"{v:,.2f}".replace(",", " ").replace(".", ",") + " EUR"


# ============================================================ comprobaciones ==


def comprobar_estructura(meta: dict, inf: Informe) -> bool:
    faltan = meta["columnas_obligatorias_ausentes"]
    if faltan:
        inf.add(
            ABORTA, "C01",
            "faltan columnas obligatorias: " + ", ".join(faltan),
            {"ausentes": faltan},
        )
        return False
    if meta["filas_crudas"] == 0:
        inf.add(ABORTA, "C02", "la tabla del diario esta vacia")
        return False
    inf.add(
        OK, "C01",
        f"tabla '{meta['tabla']}' ({meta['jet'] or 'version desconocida'}) "
        f"con las {len(LD.COLUMNAS_OBLIGATORIAS)} columnas obligatorias",
    )
    if meta["columnas_opcionales_ausentes"]:
        inf.add(
            INFO, "C03",
            "columnas opcionales ausentes: "
            + ", ".join(meta["columnas_opcionales_ausentes"]),
            {"ausentes": meta["columnas_opcionales_ausentes"]},
        )
    return True


def comprobar_tipos(df: pd.DataFrame, inf: Informe) -> bool:
    nulas = int(df["FECHA"].isna().sum())
    if nulas:
        pct = nulas / len(df) * 100
        nivel = ABORTA if pct > 1 else AVISO
        inf.add(
            nivel, "C04",
            f"{nulas} apuntes con FECHA ilegible ({pct:.2f}% del diario)",
            {"apuntes": nulas, "pct": round(pct, 3)},
        )
        if nivel == ABORTA:
            return False

    neg_mask = (df["DEBE"] < 0) | (df["HABER"] < 0)
    negativos = int(neg_mask.sum())
    if negativos:
        desfase = float(df["VOL"].sum() - df["BRUTO"].sum())
        top = df.loc[neg_mask, "G2"].value_counts().head(4)
        inf.add(
            AVISO, "C05",
            f"{negativos} apuntes con DEBE o HABER negativo (abonos anotados en "
            "la columna contraria). Medir el volumen como Debe+Haber los RESTA "
            f"y deja el total {eur(desfase)} por debajo de la realidad: el panel "
            "mide en neto. Concentrados en los grupos "
            + ", ".join(f"{g} ({n})" for g, n in top.items()),
            {"apuntes": negativos, "desfase_bruto_vs_neto": round(desfase, 2),
             "grupos": {str(k): int(v) for k, v in top.items()}},
        )

    ambos = int(((df["DEBE"] != 0) & (df["HABER"] != 0)).sum())
    if ambos:
        inf.add(
            AVISO, "C06",
            f"{ambos} apuntes con importe simultaneo en DEBE y HABER",
            {"apuntes": ambos},
        )

    vacios = int((df["BRUTO"] == 0).sum())
    if vacios:
        inf.add(
            INFO, "C07",
            f"{vacios} apuntes con importe cero",
            {"apuntes": vacios},
        )

    sin_cuenta = int((df["CUENTA"] == "").sum())
    if sin_cuenta:
        inf.add(
            ABORTA, "C08",
            f"{sin_cuenta} apuntes sin codigo de cuenta",
            {"apuntes": sin_cuenta},
        )
        return False

    if "SALDO" in df.columns:
        desv = (df["SALDO"] - df["NETO"]).abs()
        discrepan = int((desv > LD.TOLERANCIA).sum())
        if discrepan:
            inf.add(
                AVISO, "C16",
                f"SALDO no es Debe-Haber en {discrepan} apuntes (desviacion "
                f"maxima {eur(float(desv.max()))}): en este diario SALDO "
                "significa otra cosa, asi que no se usa. El panel mide siempre "
                "sobre Debe-Haber recalculado",
                {"apuntes": discrepan, "desviacion_max": round(float(desv.max()), 2)},
            )
        else:
            inf.add(
                OK, "C16",
                f"SALDO coincide con Debe-Haber en los {len(df)} apuntes "
                "(desviacion maxima 0,00): confirmada la semantica de linea, "
                "no de acumulado",
            )

    longitudes = sorted(df["CUENTA"].str.len().unique().tolist())
    if len(longitudes) > 1:
        inf.add(
            AVISO, "C09",
            "el plan de cuentas mezcla longitudes de codigo "
            f"({longitudes[:MAX_LISTA]}): los grupos por Left(CUENTA,n) siguen "
            "siendo validos, pero comparar cuentas completas puede no serlo",
            {"longitudes": longitudes[:MAX_LISTA]},
        )
    else:
        inf.add(OK, "C09", f"codigos de cuenta uniformes de {longitudes[0]} digitos")
    return True


def comprobar_cuadres(df: pd.DataFrame, inf: Informe) -> None:
    d, h = df["DEBE"].sum(), df["HABER"].sum()
    dif = d - h
    if abs(dif) > LD.TOLERANCIA:
        inf.add(
            ABORTA, "C10",
            f"el diario no cuadra: Debe {eur(d)} frente a Haber {eur(h)}, "
            f"diferencia {eur(dif)}",
            {"debe": round(d, 2), "haber": round(h, 2), "dif": round(dif, 2)},
        )
    else:
        inf.add(OK, "C10", f"cuadre global exacto: {eur(d)} por lado")

    por_asiento = df.groupby("ASIENTO", sort=True)["NETO"].sum()
    malos = por_asiento[por_asiento.abs() > LD.TOLERANCIA]
    if len(malos):
        peores = (
            malos.abs().sort_values(ascending=False).head(MAX_LISTA).index.tolist()
        )
        inf.add(
            AVISO, "C11",
            f"{len(malos)} asientos descuadrados de {len(por_asiento)} "
            f"(mayor descuadre {eur(malos.abs().max())}). Asientos: "
            + ", ".join(map(str, peores)),
            {"asientos_descuadrados": int(len(malos)),
             "asientos_totales": int(len(por_asiento)),
             "muestra": peores},
        )
    else:
        inf.add(
            OK, "C11",
            f"los {len(por_asiento)} asientos cuadran individualmente al centimo",
        )


def comprobar_asiento_y_orden(df: pd.DataFrame, inf: Informe) -> None:
    no_num = df.loc[~df["ASIENTO"].str.fullmatch(r"\s*-?\d+\s*", na=False), "ASIENTO"]
    if len(no_num):
        pct = len(no_num) / len(df) * 100
        inf.add(
            AVISO, "C12",
            f"{len(no_num)} apuntes ({pct:.1f}%) con numero de asiento no "
            "numerico: la correlatividad no se puede comprobar. Ejemplos: "
            + ", ".join(no_num.drop_duplicates().head(MAX_LISTA).tolist()),
            {"apuntes": int(len(no_num)), "pct": round(pct, 2)},
        )
    else:
        inf.add(OK, "C12", "todos los numeros de asiento son numericos")

    if "Diario_ID" in df.columns:
        fechas = df["FECHA"]
        retrocesos = int((fechas.diff() < pd.Timedelta(0)).sum())
        if retrocesos:
            inf.add(
                AVISO, "C13",
                f"{retrocesos} saltos hacia atras en la fecha siguiendo el orden "
                "fisico del fichero: el diario no esta grabado cronologicamente",
                {"retrocesos": retrocesos},
            )
        else:
            inf.add(OK, "C13", "el diario esta grabado en orden cronologico estricto")
    else:
        inf.add(INFO, "C13", "sin Diario_ID: no se puede comprobar el orden fisico")


def comprobar_ejercicio(df: pd.DataFrame, inf: Informe, cierre: str | None) -> dict:
    f1, f2 = df["FECHA"].min(), df["FECHA"].max()
    dias = int(df["FECHA"].dt.normalize().nunique())
    span = (f2 - f1).days
    if span > 400:
        inf.add(
            AVISO, "C14",
            f"el diario abarca {span} dias ({f1.date()} a {f2.date()}): mas de un "
            "ejercicio. Las medidas de antiguedad y los totales anuales se "
            "refieren al conjunto, no a un ejercicio",
            {"dias_span": span},
        )
    if cierre:
        esperado = pd.Timestamp(cierre)
        if f2 > esperado:
            inf.add(
                AVISO, "C15",
                f"hay apuntes posteriores a la fecha de cierre del expediente "
                f"({f2.date()} > {esperado.date()})",
                {"ultima_fecha": str(f2.date()), "cierre": str(esperado.date())},
            )
        elif f2 < esperado:
            inf.add(
                INFO, "C15",
                f"el ultimo apunte ({f2.date()}) es anterior al cierre "
                f"({esperado.date()}): puede ser un diario preliminar",
                {"ultima_fecha": str(f2.date()), "cierre": str(esperado.date())},
            )
    return {"desde": str(f1.date()), "hasta": str(f2.date()), "dias_con_movimiento": dias}


# -------------------------------------------------------------- resultado ----


def comprobar_resultado(df: pd.DataFrame, inf: Informe, g: dict) -> dict:
    """
    Resultado del ejercicio y cuadre con la cuenta 08 de Gesia.

    En Gesia el resultado vive en la cuenta 08 ('Explotacion'), que agrega los
    grupos 6 y 7. El diario normalmente NO trae asiento de regularizacion, asi
    que el resultado se calcula: ingresos (7) menos gastos (6).

    Si el expediente aporta el saldo de la 08, se contrasta. Un desfase por
    encima de la importancia relativa significa que el panel contradiria al
    expediente, y entonces no se publica.
    """
    gastos = float(df.loc[df["G1"] == "6", "NETO"].sum())
    ingresos = float(df.loc[df["G1"] == "7", "NETO"].sum())
    resultado = -(gastos + ingresos)

    res: dict = {
        "gastos_grupo_6": round(gastos, 2),
        "ingresos_grupo_7": round(-ingresos, 2),
        "resultado_diario": round(resultado, 2),
        "resultado_gesia_08": None,
        "resultado_anterior": None,
        "ajustes_auditoria": None,
        "resultado_auditoria": None,
        "cuadra_con_gesia": None,
    }

    if not len(df[df["G1"].isin(["6", "7"])]):
        inf.add(
            AVISO, "C17",
            "el diario no contiene cuentas de los grupos 6 ni 7: no se puede "
            "calcular el resultado del ejercicio",
        )
        return res

    regularizado = abs(resultado) <= LD.TOLERANCIA
    if regularizado:
        inf.add(
            AVISO, "C17",
            "los grupos 6 y 7 netean a cero: el diario ya incluye la "
            "regularizacion, asi que el resultado hay que leerlo de la cuenta "
            "129 y no de la diferencia entre gastos e ingresos",
        )
    else:
        inf.add(
            OK, "C17",
            f"resultado del ejercicio segun el diario: {eur(resultado)} "
            f"(ingresos {eur(-ingresos)} menos gastos {eur(gastos)}), sin "
            "asiento de regularizacion",
        )

    if g.get("resultado_08") is None:
        inf.add(
            INFO, "C18",
            "no se ha aportado el saldo de la cuenta 08 de Gesia: el resultado "
            "del panel sale solo del diario, sin contraste con el expediente",
        )
        return res

    res["resultado_gesia_08"] = round(g["resultado_08"], 2)
    res["resultado_anterior"] = (
        round(g["anterior"], 2) if g.get("anterior") is not None else None
    )
    res["ajustes_auditoria"] = (
        round(g["ajustes"], 2) if g.get("ajustes") is not None else None
    )
    if g.get("ajustes") is not None:
        res["resultado_auditoria"] = round(g["resultado_08"] + g["ajustes"], 2)

    desfase = resultado - g["resultado_08"]
    res["cuadra_con_gesia"] = abs(desfase) <= LD.TOLERANCIA
    ir_t = g.get("ir_t")

    if res["cuadra_con_gesia"]:
        inf.add(
            OK, "C18",
            f"el resultado del diario cuadra al centimo con la cuenta 08 de "
            f"Gesia ({eur(g['resultado_08'])}): el diario analizado es el mismo "
            "que sostiene los saldos del expediente",
        )
    else:
        supera_ir = ir_t is not None and abs(desfase) > ir_t
        inf.add(
            ABORTA if supera_ir else AVISO, "C18",
            f"el resultado del diario ({eur(resultado)}) no coincide con la "
            f"cuenta 08 de Gesia ({eur(g['resultado_08'])}): desfase "
            f"{eur(desfase)}"
            + (f", por encima de la importancia relativa ({eur(ir_t)}). El panel "
               "contradiria al expediente" if supera_ir else
               ". Puede tratarse de un diario preliminar"),
            {"desfase": round(desfase, 2), "ir_t": ir_t},
        )

    if res["ajustes_auditoria"] is not None and ir_t:
        pct = abs(res["ajustes_auditoria"]) / ir_t * 100
        inf.add(
            INFO if pct < 100 else AVISO, "C19",
            f"ajustes de auditoria propuestos por {eur(res['ajustes_auditoria'])}, "
            f"un {pct:.0f}% de la importancia relativa. Resultado tras ajustes: "
            f"{eur(res['resultado_auditoria'])}",
            {"ajustes": res["ajustes_auditoria"], "pct_ir_t": round(pct, 1)},
        )
    return res


# --------------------------------------------------------------- apertura ----


def detectar_apertura(df: pd.DataFrame, inf: Informe) -> dict:
    """
    Traduce a hallazgos lo que observa lib_diario.detectar_apertura.

    La deteccion vive en la libreria porque el modulo de punteo tambien la
    necesita: el aging de partidas abiertas depende de que la apertura este.
    """
    a = LD.detectar_apertura(df)
    res = {
        "activa": a["mask"] is not None,
        "via": a["via"],
        "apuntes": a["apuntes"],
        "asientos": a["asientos"][:MAX_LISTA],
        "verificada": a["verificada"],
    }

    if a["mask"] is None:
        if a["columna_vacia"]:
            inf.add(
                INFO, "A01",
                "la columna APERTURA existe pero esta toda a cero: la opcion de "
                "apertura no se activo al importar el diario en Gesia",
            )
        elif not a["columna_presente"]:
            inf.add(INFO, "A01", "el diario no trae columna APERTURA")
        if a["candidato_debil"]:
            c = a["candidato_debil"]
            inf.add(
                AVISO, "A02",
                f"no se ha identificado la apertura con confianza: el mejor "
                f"candidato (asiento {c['asiento']}, {c['lineas']} lineas) solo "
                f"abre {c['grupos']} grupos de cuenta",
                c,
            )
        inf.add(
            AVISO, "A03",
            "apertura no detectada: los saldos iniciales no se pueden separar "
            "del movimiento del ejercicio",
        )
        return res

    if a["problemas"]:
        inf.add(
            ABORTA, "A04",
            "lo identificado como apertura no lo es: " + "; ".join(a["problemas"])
            + ". Revisar la importacion antes de construir el panel",
            {"problemas": a["problemas"]},
        )
        return res

    inf.add(
        OK, "A05",
        f"apertura detectada y verificada por {a['via']}: {a['apuntes']} "
        f"apuntes, {eur(a['importe'])} por lado, sin cuentas de resultados",
    )
    return res


# ----------------------------------------------------------------- punteo ----


def detectar_punteo(df: pd.DataFrame, apertura: dict, inf: Informe) -> dict:
    res: dict = {"activo": False, "grupos": 0, "cobertura": {}, "aging_publicable": False}

    g = LD.grupos_punteo(df)
    if g is None:
        if "Indice" in df.columns:
            inf.add(
                INFO, "P01",
                "la columna Indice existe pero esta toda a cero: la opcion de "
                "punteo no se activo al importar. El panel saldra sin plazos "
                "reales de liquidacion ni antiguedad de partidas abiertas",
            )
        else:
            inf.add(INFO, "P01", "el diario no trae columna Indice: sin punteo")
        return res

    res["activo"] = True
    res["grupos"] = int(len(g))
    descuadrados = int((~g["cuadra"]).sum())
    if descuadrados:
        inf.add(
            AVISO, "P02",
            f"{descuadrados} de los {len(g)} grupos de punteo no netean a cero: "
            "el punteo es inconsistente y los plazos que salgan de el no son "
            "fiables",
            {"grupos_descuadrados": descuadrados, "grupos": int(len(g))},
        )
    else:
        inf.add(
            OK, "P02",
            f"{len(g)} grupos de punteo (CUENTA, Indice), todos netean a cero",
        )

    # --- cobertura por grupo de 2 digitos --------------------------------
    tot = df.groupby("G2", sort=True).size()
    pun = df[df["Indice"] > 0].groupby("G2", sort=True).size()
    cob = (pun / tot * 100).dropna().sort_values(ascending=False)
    cob = cob[tot.reindex(cob.index) >= MIN_LINEAS_GRUPO]

    bajos, altos = [], []
    for grupo, pct in cob.items():
        entrada = {"grupo": grupo, "pct": round(float(pct), 1), "lineas": int(tot[grupo])}
        (altos if pct >= UMBRAL_COBERTURA else bajos).append(entrada)
    res["cobertura"] = {"suficiente": altos[:MAX_LISTA * 2], "insuficiente": bajos[:MAX_LISTA * 2]}

    if altos:
        inf.add(
            OK, "P03",
            "cobertura de punteo suficiente (>= "
            f"{UMBRAL_COBERTURA:.0f}%) en los grupos "
            + ", ".join(f"{a['grupo']} ({a['pct']}%)" for a in altos[:MAX_LISTA]),
            {"grupos": altos[:MAX_LISTA]},
        )
    if bajos:
        inf.add(
            AVISO, "P04",
            f"cobertura por debajo del {UMBRAL_COBERTURA:.0f}% en "
            + ", ".join(f"{b['grupo']} ({b['pct']}%)" for b in bajos[:MAX_LISTA])
            + ". En estos grupos, Indice=0 significa 'no punteado', no "
            "'pendiente': el panel mostrara la distribucion y la lista, pero "
            "SIN cifra de cabecera",
            {"grupos": bajos[:MAX_LISTA]},
        )

    # --- acoplamiento punteo / apertura ----------------------------------
    if not apertura.get("verificada"):
        inf.add(
            AVISO, "P05",
            "hay punteo pero no hay apertura verificada. Los pagos que cancelan "
            "facturas del ejercicio anterior se quedan sin contrapartida y "
            "apareceran como partidas abiertas que en realidad estan "
            "liquidadas: EL AGING NO SE PUBLICA",
        )
    else:
        ap_mask = (
            df["APERTURA"] != 0
            if ("APERTURA" in df.columns and (df["APERTURA"] != 0).any())
            else df["ASIENTO"].isin(apertura["asientos"])
        )
        ap = df[ap_mask]
        ap_punteados = int((ap["Indice"] > 0).sum())
        pct = ap_punteados / len(ap) * 100 if len(ap) else 0.0
        idx = set(map(tuple, df.loc[ap_mask & (df["Indice"] > 0), ["CUENTA", "Indice"]].values))
        importe = float(g.loc[g.index.isin(idx), "importe"].sum()) if idx else 0.0
        res["aging_publicable"] = True
        res["apertura_punteada"] = {
            "apuntes": ap_punteados, "pct": round(pct, 1), "importe": round(importe, 2)
        }
        inf.add(
            OK, "P06",
            f"el punteo se apoya en la apertura: {ap_punteados} de {len(ap)} "
            f"lineas de apertura estan punteadas ({pct:.1f}%), por {eur(importe)}. "
            "El aging de partidas abiertas es publicable",
        )
    return res


# --------------------------------------------------------------- linea base --


def linea_base(df: pd.DataFrame) -> dict:
    """Estadisticos del propio cliente, para que las fases siguientes midan
    contra su comportamiento y no contra reglas universales."""
    por_dia = df.groupby(df["FECHA"].dt.normalize()).size()
    dow = df.groupby("DOW").size()
    dias_naturales = pd.date_range(df["FECHA"].min(), df["FECHA"].max(), freq="D")
    return {
        "apuntes_por_dia": {
            "media": round(float(por_dia.mean()), 1),
            "mediana": round(float(por_dia.median()), 1),
            "p90": round(float(por_dia.quantile(0.9)), 1),
            "maximo": int(por_dia.max()),
            "dia_maximo": str(por_dia.idxmax().date()),
        },
        "dias_con_movimiento": int(len(por_dia)),
        "dias_naturales": int(len(dias_naturales)),
        "apuntes_por_dia_semana": {
            ["lun", "mar", "mie", "jue", "vie", "sab", "dom"][int(k)]: int(v)
            for k, v in dow.items()
        },
        "apuntes_fin_de_semana": int(df["DOW"].isin([5, 6]).sum()),
        "pct_fin_de_semana": round(float(df["DOW"].isin([5, 6]).mean() * 100), 2),
        "asientos_fin_de_semana": int(
            df.loc[df["DOW"].isin([5, 6]), "ASIENTO"].nunique()
        ),
    }


# ==================================================================== salida ==


def imprimir(inf: Informe, meta: dict, resumen: dict) -> None:
    an = "=" * 72
    print(an)
    print("VERIFICACION DEL CONTRATO DEL DIARIO")
    print(an)
    print(f"  fichero        {meta['fichero']}  ({meta['bytes'] / 1_048_576:.1f} MB, "
          f"{meta['jet']})")
    print(f"  tabla          {meta['tabla']}")
    print(f"  apuntes        {resumen['apuntes']:,}".replace(",", "."))
    print(f"  asientos       {resumen['asientos']:,}".replace(",", "."))
    print(f"  cuentas        {resumen['cuentas']:,}".replace(",", "."))
    ej = resumen.get("ejercicio") or {}
    if ej:
        print(f"  ejercicio      {ej['desde']} a {ej['hasta']} "
              f"({ej['dias_con_movimiento']} dias con movimiento)")
    else:
        print("  ejercicio      no determinable")
    print()

    r = resumen.get("resultado") or {}
    if r.get("resultado_diario") is not None:
        print("RESULTADO DEL EJERCICIO")
        print(f"  segun el diario        {eur(r['resultado_diario']):>20s}"
              f"   (ingresos {eur(r['ingresos_grupo_7'])} - gastos "
              f"{eur(r['gastos_grupo_6'])})")
        if r.get("resultado_gesia_08") is not None:
            marca = "cuadra" if r["cuadra_con_gesia"] else "DESCUADRA"
            print(f"  cuenta 08 de Gesia     {eur(r['resultado_gesia_08']):>20s}"
                  f"   {marca}")
        if r.get("resultado_anterior") is not None:
            ant = r["resultado_anterior"]
            var = ((r["resultado_diario"] / ant - 1) * 100) if ant else None
            print(f"  ejercicio anterior     {eur(ant):>20s}"
                  + (f"   {var:+.0f}%" if var is not None else ""))
        if r.get("ajustes_auditoria") is not None:
            print(f"  ajustes de auditoria   {eur(r['ajustes_auditoria']):>20s}")
            print(f"  resultado auditoria    {eur(r['resultado_auditoria']):>20s}")
        print()

    print("OPCIONES DE IMPORTACION DETECTADAS")
    ap, pu = resumen["apertura"], resumen["punteo"]
    print(f"  apertura       {'SI' if ap['verificada'] else 'NO'}"
          + (f"  ({ap['via']}, {ap['apuntes']} apuntes)" if ap["verificada"] else ""))
    print(f"  punteo         {'SI' if pu['activo'] else 'NO'}"
          + (f"  ({pu['grupos']} grupos)" if pu["activo"] else ""))
    print(f"  aging          {'publicable' if pu['aging_publicable'] else 'suprimido'}")
    print()

    orden = {ABORTA: 0, AVISO: 1, INFO: 2, OK: 3}
    etiqueta = {ABORTA: "[ABORTA]", AVISO: "[AVISO] ", INFO: "[info]  ", OK: "[ok]    "}
    print("COMPROBACIONES")
    for h in sorted(inf.hallazgos, key=lambda x: (orden[x["nivel"]], x["codigo"])):
        cabeza = f"  {etiqueta[h['nivel']]} {h['codigo']}  "
        cuerpo = textwrap.wrap(h["texto"], width=70 - len(cabeza)) or [""]
        print(cabeza + cuerpo[0])
        for extra in cuerpo[1:]:
            print(" " * len(cabeza) + extra)
    print()
    print(an)
    print(f"VEREDICTO: {inf.veredicto}")
    print(an)


def analizar(df: pd.DataFrame, meta: dict, cierre: str | None = None,
             gesia: dict | None = None) -> tuple[Informe, dict]:
    """
    Ejecuta la bateria completa sobre un diario ya cargado.

    Aislada de main() a proposito: asi el arnes de pruebas puede pasarle
    variantes del diario (sin punteo, sin apertura, descuadrado) y comprobar
    que el veredicto degrada como debe.
    """
    inf = Informe()

    if not comprobar_estructura(meta, inf):
        return inf, {"apuntes": int(len(df))}

    tipos_ok = comprobar_tipos(df, inf)
    if tipos_ok:
        ejercicio = comprobar_ejercicio(df, inf, cierre)
        comprobar_cuadres(df, inf)
        comprobar_asiento_y_orden(df, inf)
        resultado = comprobar_resultado(df, inf, gesia or {})
        apertura = detectar_apertura(df, inf)
        punteo = detectar_punteo(df, apertura, inf)
        base = linea_base(df)
    else:
        ejercicio = {}
        resultado = {}
        apertura = {"activa": False, "verificada": False, "via": None,
                    "apuntes": 0, "asientos": []}
        punteo = {"activo": False, "grupos": 0, "aging_publicable": False,
                  "cobertura": {}}
        base = {}

    resumen = {
        "base_de_medida": "neto (Debe-Haber); volumen como |neto|",
        "apuntes": int(len(df)),
        "asientos": int(df["ASIENTO"].nunique()),
        "cuentas": int(df["CUENTA"].nunique()),
        "debe": round(float(df["DEBE"].sum()), 2),
        "haber": round(float(df["HABER"].sum()), 2),
        "volumen_neto": round(float(df["VOL"].sum()), 2),
        "volumen_bruto": round(float(df["BRUTO"].sum()), 2),
        "ejercicio": ejercicio,
        "resultado": resultado,
        "apertura": apertura,
        "punteo": punteo,
        "linea_base": base,
    }
    # Si hay que abortar, nada de lo calculado es publicable: que el JSON no
    # deje una bandera en verde que una fase posterior pueda creerse.
    if inf.veredicto == "ABORTAR":
        resumen["punteo"]["aging_publicable"] = False
    return inf, resumen


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("diario", help="ruta al .smn o .mdb del diario")
    p.add_argument("--json", help="ruta donde escribir el contrato en JSON")
    p.add_argument("--cierre", help="fecha de cierre del expediente (AAAA-MM-DD)")
    p.add_argument("--resultado-08", type=_importe,
                   help="SaldoCliente de la cuenta 08 de Gesia, para contrastar")
    p.add_argument("--resultado-anterior", type=_importe,
                   help="SaldoAnterior de la cuenta 08 (ejercicio precedente)")
    p.add_argument("--ajustes", type=_importe,
                   help="SaldoAj de la cuenta 08 (ajustes de auditoria)")
    p.add_argument("--ir-t", type=_importe, help="importancia relativa de trabajo")
    args = p.parse_args()

    gesia = {
        "resultado_08": args.resultado_08,
        "anterior": args.resultado_anterior,
        "ajustes": args.ajustes,
        "ir_t": args.ir_t,
    }

    try:
        df, meta = LD.cargar(args.diario)
    except LD.DiarioIlegible as exc:
        print(f"  [ABORTA] C00  {exc}")
        print("VEREDICTO: ABORTAR")
        return 2

    inf, resumen = analizar(df, meta, args.cierre, gesia)

    if inf.veredicto == "ABORTAR" and meta["columnas_obligatorias_ausentes"]:
        for h in inf.hallazgos:
            print(f"  [{h['nivel']}] {h['codigo']}  {h['texto']}")
        print("VEREDICTO: ABORTAR")
        return 2

    imprimir(inf, meta, resumen)

    if args.json:
        salida = {
            "veredicto": inf.veredicto,
            "umbral_cobertura": UMBRAL_COBERTURA,
            "fichero": meta,
            "resumen": resumen,
            "hallazgos": inf.hallazgos,
        }
        Path(args.json).write_text(
            json.dumps(salida, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        print(f"contrato escrito en {args.json}")

    return inf.codigo_salida


if __name__ == "__main__":
    sys.exit(main())
