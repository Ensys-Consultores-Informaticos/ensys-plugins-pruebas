#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lectura determinista del diario contable de un expediente Gesia (.smn / .mdb).

El .smn es una base Access JET4. Se lee con mdbtools (mdb-tables / mdb-export),
forzando formatos de fecha ISO y escapado de caracteres invisibles para que el
CSV intermedio no se rompa con conceptos que contengan saltos de linea.

Ninguna funcion de este modulo imprime nada: devuelven datos. El que imprime es
el verificador, y lo hace acotado.
"""

from __future__ import annotations

import io
import subprocess
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------- contrato ---

# Sin estas columnas no hay nada que analizar.
COLUMNAS_OBLIGATORIAS = ["FECHA", "CUENTA", "DEBE", "HABER", "ASIENTO"]

# Estas amplian el analisis si estan, pero su ausencia no es un error.
# APERTURA e Indice dependen de opciones que el auditor activa (o no) al
# importar el diario en Gesia, asi que faltan con normalidad.
COLUMNAS_OPCIONALES = [
    "Diario_ID",
    "NOMBRE",
    "CONCEPTO",
    "SALDO",
    "APERTURA",
    "Indice",
    "DEBESA",
    "HABERSA",
]

# Campos "no normalizados" de Gesia. Pueden no existir y su semantica no esta
# garantizada, asi que NUNCA se usan para calcular: los grupos de cuenta se
# derivan siempre de Left(CUENTA, n).
COLUMNAS_NN = ["NN_APUNTE", "NN_CTA1", "NN_CTA2", "NN_CTA3", "NN_CTA4", "NN_SALDO"]

TOLERANCIA = 0.01  # euros

# Un grupo de punteo que se lleva mas de esta parte de las lineas de su cuenta,
# y tiene al menos este numero de lineas, no es un emparejamiento de partidas:
# es la cuenta neteandose consigo misma. Se marca y se excluye de los plazos.
MIN_LINEAS_MASIVO = 10
PESO_MASIVO = 0.50


class DiarioIlegible(Exception):
    """No se ha podido leer el fichero como base Access."""


# ------------------------------------------------------------------ lectura ---


def _ejecutar(cmd: list[str]) -> str:
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except FileNotFoundError as exc:
        raise DiarioIlegible(
            "mdbtools no esta instalado en este entorno "
            "(hace falta mdb-tables y mdb-export)"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise DiarioIlegible("mdbtools ha excedido el tiempo de espera") from exc
    if res.returncode != 0:
        raise DiarioIlegible(
            f"mdbtools ha fallado ({res.returncode}): {res.stderr.strip()[:300]}"
        )
    return res.stdout


def version_jet(ruta: Path) -> str:
    """Version del motor Access del fichero, o cadena vacia si no se reconoce."""
    try:
        return _ejecutar(["mdb-ver", str(ruta)]).strip()
    except DiarioIlegible:
        return ""


def tablas(ruta: Path) -> list[str]:
    salida = _ejecutar(["mdb-tables", "-1", str(ruta)])
    return [t for t in (linea.strip() for linea in salida.splitlines()) if t]


def localizar_tabla(ruta: Path) -> str:
    """
    Devuelve el nombre de la tabla del diario.

    Se espera 'Diario'. Si no esta, se busca sin distinguir mayusculas antes de
    rendirse, pero no se adivina entre varias candidatas: es mejor fallar que
    analizar la tabla equivocada.
    """
    disponibles = tablas(ruta)
    if not disponibles:
        raise DiarioIlegible("el fichero no contiene ninguna tabla legible")
    for nombre in disponibles:
        if nombre == "Diario":
            return nombre
    coincidencias = [n for n in disponibles if n.lower() == "diario"]
    if len(coincidencias) == 1:
        return coincidencias[0]
    raise DiarioIlegible(
        "no hay tabla 'Diario' en el fichero. Tablas presentes: "
        + ", ".join(disponibles[:10])
    )


def exportar_csv(ruta: Path, tabla: str) -> str:
    return _ejecutar(
        [
            "mdb-export",
            "-D", "%Y-%m-%d",
            "-T", "%Y-%m-%d %H:%M:%S",
            "-e",                # escapa \r \n \t dentro de los campos de texto
            "-0", "",            # NULL como cadena vacia
            str(ruta),
            tabla,
        ]
    )


def cargar(ruta: str | Path) -> tuple[pd.DataFrame, dict]:
    """
    Carga el diario y devuelve (DataFrame, metadatos).

    El DataFrame lleva anadidas columnas derivadas y estables:
      G1..G4  grupo PGC por Left(CUENTA, n), como texto
      NETO    DEBE - HABER  (equivale al campo SALDO de Gesia)
      VOL     |NETO|        (volumen movido, robusto ante abonos negativos)
      BRUTO   DEBE + HABER  (solo diagnostico)
      DOW     dia de la semana, 0=lunes .. 6=domingo
    """
    ruta = Path(ruta)
    if not ruta.exists():
        raise DiarioIlegible(f"no existe el fichero {ruta}")

    tabla = localizar_tabla(ruta)
    crudo = exportar_csv(ruta, tabla)
    df = pd.read_csv(
        io.StringIO(crudo),
        dtype=str,
        keep_default_na=False,
        na_values=[],
        escapechar="\\",
        low_memory=False,
    )

    meta = {
        "fichero": ruta.name,
        "bytes": ruta.stat().st_size,
        "jet": version_jet(ruta),
        "tabla": tabla,
        "tablas_en_fichero": tablas(ruta),
        "columnas_presentes": list(df.columns),
        "columnas_obligatorias_ausentes": [
            c for c in COLUMNAS_OBLIGATORIAS if c not in df.columns
        ],
        "columnas_opcionales_ausentes": [
            c for c in COLUMNAS_OPCIONALES if c not in df.columns
        ],
        "columnas_nn_presentes": [c for c in COLUMNAS_NN if c in df.columns],
        "filas_crudas": len(df),
    }

    if meta["columnas_obligatorias_ausentes"]:
        return df, meta

    # --- tipado explicito, sin inferencia --------------------------------
    # mdb-export escribe las columnas DateTime con hora y las Date sin ella,
    # segun el tipo declarado en Access. Se prueban los dos formatos de forma
    # explicita: nunca se deja que pandas infiera, porque la inferencia puede
    # cambiar de resultado entre ficheros (y confunde dia con mes).
    crudo_fecha = df["FECHA"].astype(str).str.strip()
    fechas = pd.to_datetime(crudo_fecha, format="%Y-%m-%d %H:%M:%S", errors="coerce")
    pendientes = fechas.isna() & (crudo_fecha != "")
    if pendientes.any():
        fechas.loc[pendientes] = pd.to_datetime(
            crudo_fecha[pendientes], format="%Y-%m-%d", errors="coerce"
        )
    df["FECHA"] = fechas
    for col in ("DEBE", "HABER", "SALDO", "APERTURA", "DEBESA", "HABERSA"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    if "Indice" in df.columns:
        df["Indice"] = pd.to_numeric(df["Indice"], errors="coerce").fillna(0).astype("int64")
    if "Diario_ID" in df.columns:
        df["Diario_ID"] = pd.to_numeric(df["Diario_ID"], errors="coerce")

    df["CUENTA"] = df["CUENTA"].astype(str).str.strip()
    df["ASIENTO"] = df["ASIENTO"].astype(str).str.strip()

    # --- derivadas: los grupos SIEMPRE desde CUENTA, nunca desde NN_ -----
    for n in (1, 2, 3, 4):
        df[f"G{n}"] = df["CUENTA"].str[:n]
    # NETO es la magnitud sobre la que mide todo el panel. Equivale al campo
    # SALDO de Gesia, que es Debe-Haber de la propia linea (no un acumulado);
    # se recalcula en vez de leerlo para que funcione aunque SALDO no venga, y
    # el verificador comprueba que ambos coinciden.
    df["NETO"] = df["DEBE"] - df["HABER"]
    # VOL es el volumen movido por la linea. Se mide como |NETO| y NO como
    # Debe+Haber: cuando un abono se anota como Debe negativo, la suma bruta lo
    # RESTA del volumen y lo deja por debajo de la realidad.
    df["VOL"] = df["NETO"].abs()
    # Solo para diagnostico (detectar lineas con importe en las dos columnas).
    df["BRUTO"] = df["DEBE"] + df["HABER"]
    df["DOW"] = df["FECHA"].dt.dayofweek

    # Orden estable y reproducible para cualquier calculo posterior.
    clave = ["Diario_ID"] if "Diario_ID" in df.columns else ["FECHA", "ASIENTO"]
    df = df.sort_values(clave, kind="mergesort").reset_index(drop=True)
    meta["orden"] = clave

    return df, meta


# --------------------------------------------------------------- apertura ---


def detectar_apertura(df: pd.DataFrame) -> dict:
    """
    Localiza el asiento de apertura y lo verifica. Funcion pura: no imprime ni
    juzga, solo devuelve lo observado para que quien llame decida.

    APERTURA es una opcion de importacion de Gesia, asi que puede venir vacia o
    no venir. Cuando falta se busca el asiento de la fecha minima que cuadra, no
    toca cuentas de resultados y abre muchos grupos.

    Devuelve un dict con:
      columna_presente / columna_vacia  estado de la columna APERTURA
      mask          Series booleana con las lineas de apertura, o None
      via           como se ha identificado
      apuntes       numero de lineas
      asientos      numeros de asiento implicados
      verificada    True solo si supera las tres comprobaciones
      problemas     motivos por los que no lo es
      candidato_debil  candidato descartado por abrir pocos grupos
    """
    res: dict = {
        "columna_presente": "APERTURA" in df.columns,
        "columna_vacia": False,
        "mask": None,
        "via": None,
        "apuntes": 0,
        "asientos": [],
        "verificada": False,
        "problemas": [],
        "candidato_debil": None,
    }

    if res["columna_presente"] and (df["APERTURA"] != 0).any():
        res["mask"] = df["APERTURA"] != 0
        res["via"] = "columna APERTURA"
    else:
        res["columna_vacia"] = res["columna_presente"]
        fmin = df["FECHA"].min()
        candidatos = []
        for asi in df.loc[df["FECHA"] == fmin, "ASIENTO"].drop_duplicates():
            g = df[df["ASIENTO"] == asi]
            if (g["FECHA"] != fmin).any():
                continue
            if g["G1"].isin(["6", "7"]).any():
                continue
            if abs(g["NETO"].sum()) > TOLERANCIA:
                continue
            candidatos.append((asi, len(g), int(g["G2"].nunique())))
        if candidatos:
            # Orden determinista: mas lineas primero, y el codigo como desempate.
            candidatos.sort(key=lambda x: (-x[1], str(x[0])))
            asi, n_lineas, n_grupos = candidatos[0]
            if n_grupos >= 5:
                res["mask"] = df["ASIENTO"] == asi
                res["via"] = f"asiento {asi} en la fecha minima ({fmin.date()})"
            else:
                res["candidato_debil"] = {
                    "asiento": str(asi), "lineas": n_lineas, "grupos": n_grupos
                }

    if res["mask"] is None:
        return res

    ap = df[res["mask"]]
    res["apuntes"] = int(len(ap))
    res["asientos"] = sorted(ap["ASIENTO"].drop_duplicates().tolist())
    res["importe"] = round(float(ap.loc[ap["NETO"] > 0, "NETO"].sum()), 2)

    if abs(ap["NETO"].sum()) > TOLERANCIA:
        res["problemas"].append(f"no cuadra ({ap['NETO'].sum():.2f})")
    resultados = ap[ap["G1"].isin(["6", "7"])]
    if len(resultados):
        res["problemas"].append(
            f"contiene {len(resultados)} apuntes de cuentas de resultados "
            f"(grupos {sorted(resultados['G2'].unique())[:4]})"
        )
    if ap["FECHA"].nunique() > 1:
        res["problemas"].append(f"reparte {ap['FECHA'].nunique()} fechas distintas")

    res["verificada"] = not res["problemas"]
    return res


# ----------------------------------------------------------------- punteo ---


def grupos_punteo(df: pd.DataFrame) -> pd.DataFrame | None:
    """
    Grupos de punteo de Gesia.

    La clave es (CUENTA, Indice): la numeracion de Indice es POR CUENTA, no
    global, de modo que agrupar solo por Indice mezcla partidas de cuentas
    distintas. Devuelve None si el diario no trae punteo.
    """
    if "Indice" not in df.columns:
        return None
    punteado = df[df["Indice"] > 0]
    if punteado.empty:
        return None
    g = punteado.groupby(["CUENTA", "Indice"], sort=True).agg(
        lineas=("NETO", "size"),
        neto=("NETO", "sum"),
        # Volumen de las dos patas del grupo. El importe economico es la mitad
        # (ver abajo): como el grupo netea a cero, cargos y abonos coinciden.
        # Se mide sobre VOL (=|NETO|) y no sobre Debe ni Debe+Haber, para no
        # perder los abonos anotados como Debe negativo.
        volumen=("VOL", "sum"),
        f_ini=("FECHA", "min"),
        f_fin=("FECHA", "max"),
    )
    g["dias"] = (g["f_fin"] - g["f_ini"]).dt.days
    g["cuadra"] = g["neto"].abs() <= TOLERANCIA
    # Importe de la partida punteada: la mitad del volumen de sus dos patas.
    g["importe"] = g["volumen"] / 2.0

    # --- punteos "masivos": la cuenta entera en un solo grupo ---------------
    # Cuando una cuenta netea a cero en el ejercicio (caja, IVA soportado y
    # repercutido...), el algoritmo de Gesia la casa consigo misma y produce un
    # unico grupo con miles de lineas y un "plazo" que no es mas que la duracion
    # del ejercicio. Eso no es un emparejamiento partida a partida y no puede
    # entrar en los plazos de liquidacion.
    lineas_cuenta = df.groupby("CUENTA", sort=True).size().rename("lineas_cuenta")
    g = g.join(lineas_cuenta, on="CUENTA")
    g["peso_en_cuenta"] = (g["lineas"] / g["lineas_cuenta"]).round(3)
    g["masivo"] = (g["lineas"] >= MIN_LINEAS_MASIVO) & (
        g["peso_en_cuenta"] > PESO_MASIVO
    )
    return g
