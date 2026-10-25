"""Apertura del diario y mapeo de cuentas para la prueba de continuidad de saldos.

No imprime: devuelve datos. Quien llama decide que hacer con ellos.

Desde la 1.25.0 del MCP el diario NO sale entero del equipo del auditor. Antes el skill
comprimia el .smn y lo subia al contenedor de Cowork para leerlo con mdbtools: todas las
tablas y columnas, nombres y conceptos incluidos, para usar un solo asiento. Ahora el MCP
exporta dos cosas pequenas y nada mas:

  1. el FiltroDeApertura (campo Datos de CfgNormalizacion), con SQL_FILTRO;
  2. el asiento de apertura, con la consulta que arma sql_apertura() a partir de ese
     filtro: solo las columnas que la prueba usa, el filtro evaluado en JET como
     POR_FILTRO, y los nombres de terceros seudonimizados por el perfil.

Es la minimizacion del dato: a la herramienta solo va lo que el procedimiento necesita.
El expediente (.gs3) llega igual que siempre, en el JSON que exporta el MCP.
Ver docs/contrato-datos.md.
"""

from __future__ import annotations

import json
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

# El filtro vive en CfgNormalizacion, en el registro cuyo Concepto es FiltroDeApertura.
# Solo se pide Datos: Concepto se llama como la columna del diario que el MCP retiene.
SQL_FILTRO = "SELECT Datos FROM CfgNormalizacion WHERE Trim(Concepto) = 'FiltroDeApertura'"

# Las columnas del diario que la prueba usa. Ni CONCEPTO ni ninguna otra.
COLUMNAS_APERTURA = ("FECHA", "ASIENTO", "CUENTA", "NOMBRE", "DEBE", "HABER")


def salida_utf8() -> None:
    """La consola de Windows no es UTF-8 por defecto y parte los acentos."""
    for flujo in ("stdout", "stderr"):
        f = getattr(sys, flujo)
        if hasattr(f, "reconfigure"):
            f.reconfigure(encoding="utf-8")


def interpretar_filtro(crudo: str) -> dict:
    """Traduce el texto del FiltroDeApertura.

    El asiento de apertura se fija al normalizar el diario y NO tiene que ser el
    numero 1: en el expediente de calibracion era el 3495. El filtro tiene esta forma:

        CAMPO|Tipo|Operador|Valor||| descripcion legible

    Medido en un expediente real:  CONCEPTO|Texto|Es igual a|Apertura|||...
    El ejemplo de partida era por ASIENTO, asi que el campo, el operador y el
    valor son todos variables y hay que leerlos, no suponerlos.

    Devuelve {campo, tipo, operador, valor, crudo}, o {ausente: True, motivo}.
    """
    partes = str(crudo or "").split("|")
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
    campo = partes[0].strip()
    # el campo va a parar a una consulta: solo un nombre de columna, nada mas
    if not campo.replace("_", "").isalnum():
        return {"ausente": True, "motivo": "campo de filtro raro: " + repr(campo), "crudo": crudo}
    return {
        "campo": campo,
        "tipo": partes[1].strip(),
        "operador": operador,
        "valor": partes[3].strip(),
        "crudo": crudo,
    }


def leer_filtro(ruta) -> dict:
    """Lee el FiltroDeApertura del fichero que deja exportar_consulta con SQL_FILTRO."""
    try:
        filas = json.loads(Path(ruta).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"ausente": True, "motivo": "no se puede leer el filtro exportado: " + str(exc)}
    if not isinstance(filas, list):
        return {"ausente": True, "motivo": "el fichero del filtro no es una lista de filas"}
    if not filas:
        return {"ausente": True, "motivo": "CfgNormalizacion no tiene FiltroDeApertura"}
    if len(filas) > 1:
        return {"ausente": True,
                "motivo": "hay " + str(len(filas)) + " FiltroDeApertura, se esperaba 1"}
    clave = next((k for k in filas[0] if str(k).lower() == "datos"), None)
    if clave is None:
        return {"ausente": True, "motivo": "la fila del filtro no trae la columna Datos"}
    return interpretar_filtro(filas[0][clave])


def condicion_jet(filtro: dict) -> str:
    """El filtro como condicion de JET, con la misma semantica que aplicar_filtro():
    texto sin espacios a los lados y sin distinguir mayusculas; un nulo es texto vacio."""
    campo = "[" + filtro["campo"] + "]"
    col = "LCase(Trim(IIf(IsNull(" + campo + "), '', " + campo + ")))"
    valor = filtro["valor"].lower().replace("'", "''")
    op = OPERADORES[filtro["operador"]]
    if op in ("==", "!="):
        return col + (" = " if op == "==" else " <> ") + "'" + valor + "'"
    # en LIKE, % y _ son comodines: el valor se escapa entre corchetes
    lit = valor.replace("[", "[[]").replace("%", "[%]").replace("_", "[_]")
    patron = {"contiene": "%" + lit + "%", "empieza": lit + "%", "termina": "%" + lit}[op]
    return col + " LIKE '" + patron + "'"


def sql_apertura(filtro: dict, con_campo_apertura: bool = True) -> str:
    """La consulta del asiento de apertura: lo que el filtro selecciona y, si el diario
    trae el campo APERTURA, tambien lo que ese campo marca, para la comprobacion C06."""
    cond = condicion_jet(filtro)
    cols = ", ".join(COLUMNAS_APERTURA)
    if con_campo_apertura:
        return ("SELECT " + cols + ", APERTURA, IIf(" + cond + ", 1, 0) AS POR_FILTRO "
                "FROM Diario WHERE (" + cond + ") OR (APERTURA <> 0)")
    return "SELECT " + cols + ", 1 AS POR_FILTRO FROM Diario WHERE " + cond


def _numerica(serie: pd.Series) -> pd.Series:
    return (pd.to_numeric(serie.astype(str).str.replace(",", ".", regex=False), errors="coerce")
            .fillna(0.0).round(DECIMALES))


def cargar_apertura(ruta) -> pd.DataFrame:
    """Trae el asiento de apertura exportado, con los importes numericos y POR_FILTRO
    como booleano. Las columnas se normalizan a mayusculas."""
    filas = json.loads(Path(ruta).read_text(encoding="utf-8"))
    if not isinstance(filas, list):
        raise RuntimeError("el fichero de apertura no es una lista de filas")
    df = pd.DataFrame(filas)
    df.columns = [str(c).upper() for c in df.columns]
    for col in ("DEBE", "HABER", "APERTURA"):
        if col in df.columns:
            df[col] = _numerica(df[col])
    if "POR_FILTRO" in df.columns:
        df["POR_FILTRO"] = _numerica(df["POR_FILTRO"]) != 0
    for col in ("CUENTA", "ASIENTO", "NOMBRE"):
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str).str.strip()
    # el ASIENTO llega numerico desde ODBC: 3495.0 se escribe 3495
    if "ASIENTO" in df.columns:
        df["ASIENTO"] = df["ASIENTO"].str.replace(r"\.0$", "", regex=True)
    return df


def aplicar_filtro(df: pd.DataFrame, filtro: dict) -> pd.Series:
    """El filtro sobre un diario completo en pandas. Ya no lo usa la prueba -lo evalua JET
    al exportar-: lo usa el arnes para comprobar que condicion_jet() selecciona lo mismo."""
    campo = filtro["campo"]
    if campo not in df.columns:
        raise RuntimeError(
            "el filtro de apertura usa el campo " + repr(campo) + ", que no existe "
            "en el diario. Columnas: " + str(sorted(df.columns))
        )
    col = df[campo].fillna("").astype(str).str.strip().str.lower()
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
