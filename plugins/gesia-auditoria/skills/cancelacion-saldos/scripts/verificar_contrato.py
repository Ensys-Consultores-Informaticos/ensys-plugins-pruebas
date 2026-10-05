"""Comprueba en ejecucion lo que el emparejamiento de saldos asume.

No fiarse de la documentacion: lo que se asume, se comprueba. Un papel de
trabajo bonito sobre datos mal entendidos es peor que no tener papel.

    python verificar_contrato.py --entrada extracto.csv

Codigos de salida:
  0  todo encaja
  1  avisos: se puede seguir, pero hay que leerlos y contarlos en el papel
  2  no se puede hacer la prueba. No se genera nada.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_cancelacion import MAX_LEFTOVER_FOR_COMBOS, TOL, cargar_extracto  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--entrada", required=True,
                    help="fichero exportado con exportar_consulta (.csv o .json)")
    args = p.parse_args()

    errores: list[str] = []
    avisos: list[str] = []

    # C01 · el extracto se lee y trae las columnas obligatorias
    try:
        df = cargar_extracto(args.entrada)
    except (ValueError, FileNotFoundError) as exc:
        print("C01 ERROR: " + str(exc))
        return 2

    if df.empty:
        print("C01 ERROR: el extracto no trae ninguna fila.")
        return 2
    print("C01 · " + str(len(df)) + " apuntes, " + str(df["CUENTA"].nunique())
          + " cuenta(s)")

    # C02 · las fechas se interpretan
    malas_fechas = int(df["FECHA"].isna().sum())
    if malas_fechas:
        errores.append("C02 · " + str(malas_fechas) + " apunte(s) con FECHA vacia "
                        "o no interpretable.")
    else:
        print("C02 · todas las fechas se interpretan")

    # C03 · SALDO es numerico
    malos_saldos = int(df["SALDO"].isna().sum())
    if malos_saldos:
        errores.append("C03 · " + str(malos_saldos) + " apunte(s) con SALDO no "
                        "numerico (o DEBE/HABER del que se deriva).")
    else:
        print("C03 · SALDO es numerico en todos los apuntes")

    # C04 · todas las filas tienen CUENTA
    vacias = df["CUENTA"].isna() | (df["CUENTA"].astype(str).str.strip() == "")
    if vacias.any():
        errores.append("C04 · " + str(int(vacias.sum())) + " apunte(s) sin CUENTA.")
    else:
        print("C04 · todas las filas tienen CUENTA")

    if errores:
        for e in errores:
            print("\n" + e)
        print("\nNo se puede hacer la prueba.")
        return 2

    # C05 · punteo previo: si el extracto trae la columna Indice del .smn,
    # los apuntes con indice > 0 se respetan como ya cancelados y el
    # emparejamiento trabaja solo sobre el resto. Su ausencia es normal
    # (es una opcion de importacion del diario).
    hay_punteo = "INDICE_PREVIO" in df.columns
    if hay_punteo:
        punteados = df["INDICE_PREVIO"] > 0
        n_grupos = df.loc[punteados].groupby(
            ["CUENTA", "INDICE_PREVIO"]).ngroups if punteados.any() else 0
        print("C05 · punteo previo (columna Indice): " + str(int(punteados.sum()))
              + " de " + str(len(df)) + " apuntes ya punteados, en "
              + str(n_grupos) + " grupo(s). Se respetan tal cual.")
        pendientes = df.loc[~punteados]
    else:
        print("C05 · el extracto no trae punteo previo (columna Indice): el "
              "emparejamiento parte de cero. Es normal si el diario se "
              "importo sin esa opcion.")
        pendientes = df

    # A04 · grupos del punteo previo que no suman 0. Se avisa y se respeta:
    # el punteo es del cliente y lo juzga el auditor, pero tiene que constar.
    if hay_punteo:
        descuadrados = []
        sumas = (df[df["INDICE_PREVIO"] > 0]
                 .groupby(["CUENTA", "INDICE_PREVIO"])["SALDO"].sum().round(2))
        for (cuenta, idx), s in sumas.items():
            if abs(s) > TOL:
                descuadrados.append((cuenta, int(idx), float(s)))
        if descuadrados:
            avisos.append(
                "A04 · " + str(len(descuadrados)) + " grupo(s) del punteo previo "
                "no suman 0 ("
                + ", ".join(f"{c} idx {i}: {s:,.2f}" for c, i, s in descuadrados[:5])
                + ("..." if len(descuadrados) > 5 else "")
                + "). Se respetan tal cual y el papel los lista como descuadre "
                "del punteo contable: los juzga el auditor."
            )

    # A01 · CONCEPTO vacio no rompe el emparejamiento (va por fecha e importe,
    # no por texto) pero hace el papel menos legible para revisar a mano.
    # Lo normal desde el MCP 1.11.0 es que el extracto NO traiga CONCEPTO y si
    # FechaEnConcepto/NumeroEnConcepto: eso no es un aviso, es el diseño.
    if "FECHA_DOC" not in df.columns:
        avisos.append(
            "A01 · el extracto no trae fecha de documento: ni FechaEnConcepto -que el MCP "
            "deriva en local si el SELECT pide CONCEPTO- ni CONCEPTO. El emparejamiento "
            "no la necesita, pero los hallazgos por fecha de documento y el plazo de pago "
            "quedaran SIN EVALUAR: hay que decirlo al entregar, y la proxima vez pedir "
            "CONCEPTO en el SELECT (el texto no viaja; la fecha y el numero, si)."
        )
        vacio_concepto = 0.0
    elif int(df["FECHA_DOC"].notna().sum()) == 0:
        # La columna esta pero ninguna fila trae fecha: en este diario el concepto no la
        # lleva. Decir «se evaluan igual» aqui era falso (registro del 10/09/2026): los
        # pagos anteriores solo se comparan con la fecha CONTABLE y van a su propia fila.
        avisos.append(
            "A01 · ninguna de las " + str(len(df)) + " filas trae fecha de documento (la columna "
            + str(df.attrs.get("fuente_fecha_doc")) + " existe pero viene vacia: este diario no "
            "escribe la fecha en el concepto). Los pagos anteriores a su factura solo se pueden "
            "comparar con la fecha CONTABLE: el papel los lista en «Solo con la fecha contable» y "
            "NO son hallazgos confirmados, y no hay plazo de pago medido. Dilo al entregar."
        )
        vacio_concepto = 0.0
    elif "CONCEPTO" not in df.columns:
        n_fd = int(df["FECHA_DOC"].notna().sum())
        print("A01 · el extracto no trae el texto del CONCEPTO, y si la fecha y el numero "
              "derivados de el (" + str(df.attrs.get("fuente_fecha_doc")) + "): " + str(n_fd)
              + " de " + str(len(df)) + " filas con fecha de documento. El papel no lleva la "
              "columna de texto y los hallazgos por fecha se evaluan con esas.")
        vacio_concepto = 0.0
    else:
        vacio_concepto = (
            df["CONCEPTO"].isna() | (df["CONCEPTO"].astype(str).str.strip() == "")
        ).mean()
    if vacio_concepto > 0.3:
        avisos.append(
            "A01 · el " + format(vacio_concepto * 100, ".0f") + "% de los apuntes "
            "no trae CONCEPTO. No afecta al resultado (el emparejamiento no lee "
            "texto), pero el papel sera mas dificil de revisar."
        )

    # A02 · cuentas grandes: la combinatoria del 2.4 se acota. Lo que importa
    # es lo que queda POR emparejar, asi que se mide sobre los apuntes sin
    # puntear, no sobre el total de la cuenta.
    grandes = []
    for cuenta, grupo in pendientes.groupby("CUENTA"):
        if len(grupo) > 500:
            grandes.append((cuenta, len(grupo)))
    if grandes:
        avisos.append(
            "A02 · " + str(len(grandes)) + " cuenta(s) con mas de 500 apuntes "
            "sin puntear (" + ", ".join(c for c, _ in grandes[:5])
            + ("..." if len(grandes) > 5 else "")
            + "). La busqueda combinatoria del procedimiento 2.4 solo se intenta "
            "con hasta " + str(MAX_LEFTOVER_FOR_COMBOS) + " apuntes sin cancelar a "
            "la vez: en cuentas grandes es esperable que queden mas apuntes en "
            "INDICE 0 de los que un auditor resolveria a mano."
        )

    # A03 · cuentas donde ni siquiera el signo esta claro (todo lo pendiente
    # del mismo signo, nada que cancelar en absoluto) -- no es un error,
    # pero conviene saberlo
    solo_un_signo = []
    for cuenta, grupo in pendientes.groupby("CUENTA"):
        signos = set()
        if (grupo["SALDO"] > TOL).any():
            signos.add("+")
        if (grupo["SALDO"] < -TOL).any():
            signos.add("-")
        if len(signos) < 2:
            solo_un_signo.append(cuenta)
    if solo_un_signo:
        avisos.append(
            "A03 · " + str(len(solo_un_signo)) + " cuenta(s) con apuntes sin "
            "puntear de un solo signo (" + ", ".join(solo_un_signo[:5])
            + ("..." if len(solo_un_signo) > 5 else "") + "): ahi no hay nada "
            "nuevo que cancelar, todo quedara en INDICE 0. Puede ser correcto "
            "(cuenta con un unico movimiento pendiente) o señal de que falta "
            "traer mas ejercicios/periodos al extracto."
        )

    if avisos:
        for a in avisos:
            print("\n" + a)
        print("\nSe puede seguir, pero hay " + str(len(avisos))
              + " aviso(s) que tienen que constar en el papel.")
        return 1

    print("\nContrato verificado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
