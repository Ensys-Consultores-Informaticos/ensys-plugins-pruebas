"""Lectura del diario y mapeo de cuentas para la prueba de continuidad de saldos.

No imprime: devuelve datos. Quien llama decide que hacer con ellos.

El diario (.smn) es una base Access sin proteccion, asi que se lee con mdbtools
dentro del contenedor. El expediente (.gs3) NO: es un .mdb con contrasena y solo
se abre por el API de Gesia, asi que sus datos llegan en un JSON que prepara el
modelo con el MCP. Ver docs/contrato-datos.md.
"""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd

# Redondeo del euro. Los importes del diario llegan con error de coma flotante
# (86863532.92000002 frente a 86863532.92000031 para el mismo numero), asi que
# todo se redondea a 2 decimales ANTES de comparar. Decidido en cliente.
DECIMALES = 2

# Grupos que entran en la prueba: solo balance. Los grupos 6 y 7 se regularizan
# contra resultados al cierre y no tienen saldo de apertura; el 0, el 8 y el 9
# quedan fuera (23/08/2026).
GRUPOS_BALANCE = ("1", "2", "3", "4", "5")

# Operadores del FiltroDeApertura que este skill sabe traducir. La notacion la
# genera el modulo .NET de importacion de Gesia (ForSampling) y no esta
# especificada, asi que ante un operador desconocido se ABORTA en vez de
# adivinar: interpretar mal el filtro selecciona el asiento equivocado y el
# resultado sale plausible y falso.
OPERADORES = {
    "es igual a": "==",
    "es distinto de": "!=",
    "contiene": "contiene",
    "empieza por": "empieza",
    "termina por": "termina",
}


def salida_utf8() -> None:
    """La consola de Windows no es UTF-8 por defecto y parte los acentos."""
    for flujo in ("stdout", "stderr"):
        f = getattr(sys, flujo)
        if hasattr(f, "reconfigure"):
            f.reconfigure(encoding="utf-8")


def _hay_mdbtools() -> bool:
    return shutil.which("mdb-tables") is not None


def _conexion_odbc(ruta):
    """Lector alternativo para Windows, donde no hay mdbtools.

    El proyecto esta pensado para Cowork, donde el diario se sube al contenedor y
    se lee con mdbtools. Pero el skill tambien tiene que poder ejecutarse en la
    maquina del auditor, y ahi el camino es el driver de Access de 64 bits, el
    mismo que usa el MCP. Es un camino alternativo, no un requisito nuevo: si
    mdbtools esta, se usa mdbtools.
    """
    import pyodbc

    cadena = (
        "DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=" + str(ruta) + ";"
    )
    return pyodbc.connect(cadena, readonly=True)


def _ejecutar(cmd: list) -> str:
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except FileNotFoundError:
        raise RuntimeError(
            "No se encuentra " + cmd[0] + " (hacen falta mdb-tables y mdb-export)"
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(cmd[0] + " ha agotado el tiempo") from exc
    if res.returncode != 0:
        raise RuntimeError(cmd[0] + " ha fallado: " + res.stderr.strip())
    return res.stdout


def tablas(ruta) -> list:
    if _hay_mdbtools():
        return [t for t in _ejecutar(["mdb-tables", "-1", str(ruta)]).split("\n") if t]
    con = _conexion_odbc(ruta)
    try:
        return [f.table_name for f in con.cursor().tables(tableType="TABLE")]
    finally:
        con.close()


def _localizar_tabla(ruta, nombre: str):
    """Devuelve el nombre real de una tabla, sin distinguir mayusculas, o None."""
    for t in tablas(ruta):
        if t.strip().lower() == nombre.strip().lower():
            return t
    return None


def _exportar(ruta, tabla: str) -> pd.DataFrame:
    """Trae una tabla entera como texto. Todo str: convertir es de quien escribe."""
    if _hay_mdbtools():
        csv = _ejecutar(["mdb-export", "-D", "%Y-%m-%d", str(ruta), tabla])
        return pd.read_csv(io.StringIO(csv), dtype=str, keep_default_na=False)

    con = _conexion_odbc(ruta)
    try:
        cur = con.cursor()
        cur.execute("SELECT * FROM [" + tabla + "]")
        cols = [d[0] for d in cur.description]
        filas = [
            ["" if v is None else str(v) for v in fila] for fila in cur.fetchall()
        ]
    finally:
        con.close()
    return pd.DataFrame(filas, columns=cols, dtype=str)


def leer_filtro_apertura(ruta) -> dict:
    """Lee el FiltroDeApertura de cfgnormalizacion y lo traduce.

    El asiento de apertura se fija al normalizar el diario y NO tiene que ser el
    numero 1: en el expediente de calibracion era el 3495. La identificacion vive en
    cfgnormalizacion, en el registro cuyo Concepto es FiltroDeApertura, con el
    filtro en el campo Datos y esta forma:

        CAMPO|Tipo|Operador|Valor||| descripcion legible

    Medido en un expediente real:  CONCEPTO|Texto|Es igual a|Apertura|||...
    El ejemplo de partida era por ASIENTO, asi que el campo, el operador y el
    valor son todos variables y hay que leerlos, no suponerlos.

    Devuelve {campo, tipo, operador, valor, crudo}, o {ausente: True, motivo}
    si la tabla, el registro o el operador no permiten seguir.
    """
    # El nombre real es 'CfgNormalizacion' con mayusculas, pero Access no
    # distingue el caso en SQL y Python si: comparar en minusculas o el skill
    # decide que el diario no tiene la tabla que si tiene.
    tabla = _localizar_tabla(ruta, "cfgnormalizacion")
    if tabla is None:
        return {"ausente": True, "motivo": "el diario no tiene tabla CfgNormalizacion"}

    cfg = _exportar(ruta, tabla)
    if "Concepto" not in cfg.columns or "Datos" not in cfg.columns:
        return {
            "ausente": True,
            "motivo": "cfgnormalizacion no tiene las columnas Concepto y Datos",
        }

    filas = cfg[cfg["Concepto"].str.strip().str.lower() == "filtrodeapertura"]
    if filas.empty:
        return {"ausente": True, "motivo": "cfgnormalizacion no tiene FiltroDeApertura"}
    if len(filas) > 1:
        return {
            "ausente": True,
            "motivo": "hay " + str(len(filas)) + " FiltroDeApertura, se esperaba 1",
        }

    crudo = filas.iloc[0]["Datos"]
    partes = crudo.split("|")
    if len(partes) < 4:
        return {"ausente": True, "motivo": "filtro ilegible: " + repr(crudo)}

    operador = partes[2].strip().lower()
    if operador not in OPERADORES:
        return {
            "ausente": True,
            "motivo": (
                "operador no soportado: " + repr(partes[2]) + ". Los conocidos son "
                + str(sorted(OPERADORES)) + ". Se para en vez de adivinar."
            ),
            "crudo": crudo,
        }

    return {
        "campo": partes[0].strip(),
        "tipo": partes[1].strip(),
        "operador": operador,
        "valor": partes[3].strip(),
        "crudo": crudo,
    }


def aplicar_filtro(df: pd.DataFrame, filtro: dict) -> pd.Series:
    """Traduce el filtro leido a una mascara booleana sobre el diario."""
    campo = filtro["campo"]
    if campo not in df.columns:
        raise RuntimeError(
            "el filtro de apertura usa el campo " + repr(campo) + ", que no existe "
            "en el diario. Columnas: " + str(sorted(df.columns))
        )
    col = df[campo].astype(str).str.strip().str.lower()
    valor = filtro["valor"].lower()
    op = OPERADORES[filtro["operador"]]
    if op == "==":
        return col == valor
    if op == "!=":
        return col != valor
    if op == "contiene":
        return col.str.contains(valor, regex=False)
    if op == "empieza":
        return col.str.startswith(valor)
    return col.str.endswith(valor)


def hay_diario(ruta) -> bool:
    return _localizar_tabla(ruta, "Diario") is not None


def cargar_diario(ruta) -> pd.DataFrame:
    """Trae el Diario con los importes ya numericos y redondeados."""
    tabla = _localizar_tabla(ruta, "Diario")
    if tabla is None:
        raise RuntimeError("el fichero no tiene tabla Diario")
    df = _exportar(ruta, tabla)
    for col in ("DEBE", "HABER", "APERTURA", "SALDO"):
        if col in df.columns:
            df[col] = (
                pd.to_numeric(
                    df[col].str.replace(",", ".", regex=False), errors="coerce"
                )
                .fillna(0.0)
                .round(DECIMALES)
            )
    for col in ("CUENTA", "CONCEPTO", "ASIENTO", "NOMBRE"):
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
    return df


def saldos_apertura(df: pd.DataFrame, mascara: pd.Series) -> pd.DataFrame:
    """Saldo de apertura por cuenta del cliente, al maximo desglose del diario.

    El saldo es DEBE - HABER, no el campo APERTURA: APERTURA es una opcion de
    importacion y puede venir vacia, mientras que DEBE y HABER estan siempre.
    Cuando APERTURA si viene, verificar_contrato comprueba que ambos coinciden.
    """
    ap = df[mascara].copy()
    ap["SALDO_AP"] = (ap["DEBE"] - ap["HABER"]).round(DECIMALES)
    agr = ap.groupby("CUENTA", as_index=False)["SALDO_AP"].sum()
    agr["SALDO_AP"] = agr["SALDO_AP"].round(DECIMALES)
    return agr


def mapear_a_maximo_nivel(cuentas: list, nivel: set) -> dict:
    """Asigna cada cuenta del diario a su cuenta de maximo nivel del expediente.

    Regla fijada en cliente: el prefijo mas largo que exista como
    cuenta de maximo nivel. Hace falta porque el maximo nivel NO es un numero
    fijo de digitos: en el expediente de calibracion hay 204 cuentas de maximo nivel
    a 3 digitos
    y 234 a 4, segun la rama del plan contable. Truncar el diario a N digitos
    daria mal el resultado en una de las dos.

    Devuelve {cuenta_diario: cuenta_maximo_nivel o None}. El None no es un error
    del skill: es una cuenta abierta que el expediente no reconoce, y se informa.
    """
    mapa = {}
    for cta in cuentas:
        destino = None
        for corte in range(len(cta), 0, -1):
            if cta[:corte] in nivel:
                destino = cta[:corte]
                break
        mapa[cta] = destino
    return mapa


def _num_es(v) -> float:
    """Los saldos del expediente llegan como texto con coma decimal."""
    return round(float(str(v).replace(",", ".").strip() or 0), DECIMALES)


def leer_cierre(ruta, ejercicio: str = "", anterior: str = "",
                cliente: str = "") -> dict:
    """Lee el cierre auditado, en cualquiera de las dos formas que puede venir.

    1. Lista cruda de filas, tal como la deja `exportar_consulta` del MCP:
       [{"Cuenta": "100", "Nombre": "...", "SaldoAuditoria": "-12149313,0000"}]
       Es la forma preferida: el dato va del expediente al fichero sin pasar por
       el contexto del modelo. Los metadatos -ejercicios y cliente- se pasan como
       argumento, porque la consulta no los trae.

    2. Objeto con metadatos, que es como se escribia a mano antes de que el MCP
       supiera exportar. Se mantiene para no romper lo que ya funciona.
    """
    datos = json.loads(Path(ruta).read_text(encoding="utf-8"))

    if isinstance(datos, list):
        if not datos:
            raise RuntimeError("el fichero de cierre no trae ninguna fila")
        faltan = [c for c in ("Cuenta", "SaldoAuditoria") if c not in datos[0]]
        if faltan:
            raise RuntimeError(
                "a las filas del cierre les faltan columnas: " + str(faltan)
                + ". La consulta tiene que pedir Cuenta, Nombre y SaldoAuditoria."
            )
        if not ejercicio or not anterior:
            raise RuntimeError(
                "con un fichero de filas crudas hay que indicar el ejercicio y el "
                "anterior: la consulta no los trae."
            )
        return {
            "cliente": cliente,
            "ejercicio": str(ejercicio),
            "ejercicio_anterior": str(anterior),
            "cuentas": [
                {"cuenta": str(f["Cuenta"]).strip(),
                 "nombre": str(f.get("Nombre") or "").strip(),
                 "saldo": _num_es(f["SaldoAuditoria"])}
                for f in datos
            ],
        }

    for clave in ("ejercicio", "ejercicio_anterior", "cuentas"):
        if clave not in datos:
            raise RuntimeError("el JSON de cierre no trae " + repr(clave))
    if not datos["cuentas"]:
        raise RuntimeError("el JSON de cierre no trae ninguna cuenta")
    for c in datos["cuentas"]:
        c["cuenta"] = str(c["cuenta"]).strip()
        c["nombre"] = str(c.get("nombre", "")).strip()
        c["saldo"] = round(float(c["saldo"]), DECIMALES)
    return datos
