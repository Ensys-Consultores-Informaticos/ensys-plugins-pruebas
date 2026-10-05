# -*- coding: utf-8 -*-
"""Comprueba en ejecucion lo que la revision de estados financieros asume. Puede abortar.

No fiarse de la documentacion: lo que se asume, se comprueba. Un papel de trabajo bonito
sobre datos mal entendidos es peor que no tener papel.

    python verificar_contrato.py --estructura estructura.json --cuentas cuentas.json
                                 --ejercicios ejercicios.json

Codigos de salida:
  0  todo encaja
  1  avisos: se puede seguir, pero hay que leerlos y contarlos al entregar
  2  no se puede hacer la revision. No se genera nada.
"""

from __future__ import annotations

import argparse
import sys

from lib_eeff import (
    exigir_tokens,
    COLUMNAS_SALDO,
    DECIMALES,
    ESTADO_BALANCE,
    ESTADO_PYG,
    TOLERANCIA,
    a_float,
    cadena_del_saldo,
    cuadre_balance,
    cuentas_por_epigrafe,
    ejercicios,
    es_si,
    hojas,
    leer_json,
    salida_utf8,
    saldo,
    texto,
)

COLUMNAS_ESTRUCTURA = ("CodigoCCAA", "Estado", "Concepto", "CuentasAsignables")
COLUMNAS_CUENTAS = ("Cuenta", "CodigoCCAA", "AsignadaCCAA", "SaldoAuditoria")


def main() -> int:
    salida_utf8()
    p = argparse.ArgumentParser()
    p.add_argument("--estructura", required=True, help="JSON de EstructuraBalance + EstructuraPyG")
    p.add_argument("--cuentas", required=True, help="JSON del plan con su epigrafe y saldos")
    p.add_argument("--ejercicios", required=True, help="JSON de Auditorias: codigo y año")
    p.add_argument("--nombres-en-claro", action="store_true",
                   help="solo si el auditor ha apagado la tokenizacion: configurar dice «forzado por el auditor»")
    a = p.parse_args()

    errores: list = []
    avisos: list = []

    # ── 1 · los ficheros y sus columnas ─────────────────────────────────────
    try:
        estructura = leer_json(a.estructura)
        cuentas = leer_json(a.cuentas)
        anios = ejercicios(leer_json(a.ejercicios))
    except Exception as exc:
        print("❌ no se han podido leer los datos exportados: " + str(exc))
        return 2

    if not isinstance(estructura, list) or not estructura:
        errores.append("la estructura viene vacia: el expediente no tiene balance ni PyG cargados")
    if not isinstance(cuentas, list) or not cuentas:
        errores.append("el plan de cuentas viene vacio")
    if errores:
        for e in errores:
            print("❌ " + e)
        return 2

    if not exigir_tokens(cuentas, a.nombres_en_claro):
        return 2

    faltan = [c for c in COLUMNAS_ESTRUCTURA if c not in estructura[0]]
    if faltan:
        errores.append("a la estructura le faltan columnas: " + ", ".join(faltan))
    faltan_c = [c for c in COLUMNAS_CUENTAS if c not in cuentas[0]]
    if faltan_c:
        errores.append("al plan de cuentas le faltan columnas: " + ", ".join(faltan_c))
    if errores:
        for e in errores:
            print("❌ " + e)
        return 2

    # ── 2 · que ejercicio es cada columna ───────────────────────────────────
    if not anios:
        errores.append("no se sabe que ejercicio es cada columna de saldo: sin eso, toda cifra "
                       "que se etiquete con un año seria inventada")
    else:
        print(f"✔ ejercicios: " + ", ".join(f"SaldoAuditoria{k}={v}" for k, v in sorted(anios.items())))

    cargados = [i for i in range(1, 6)
                if any(abs(saldo(f, i)) > 0 for f in estructura)]
    if not cargados:
        errores.append("ningun ejercicio tiene cifras: no hay nada que revisar")
    else:
        print(f"✔ ejercicios con cifras: {len(cargados)} "
              + ", ".join(anios.get(str(i), f"col{i}") for i in cargados))
    sin_anio = [i for i in cargados if str(i) not in anios]
    if sin_anio:
        errores.append("hay columnas con cifras y sin año conocido: " + ", ".join(map(str, sin_anio)))

    # ── 3 · los dos estados estan ───────────────────────────────────────────
    estados = {texto(f.get("Estado")) for f in estructura}
    if ESTADO_BALANCE not in estados:
        errores.append("no hay lineas de Balance en la estructura")
    if ESTADO_PYG not in estados:
        avisos.append("no hay lineas de PyG: el papel saldra solo con el balance")

    n_hojas = len(hojas(estructura))
    if not n_hojas:
        errores.append("ninguna linea admite cuentas (CuentasAsignables): no se puede sumar nada")
    else:
        print(f"✔ estructura: {len(estructura)} lineas, {n_hojas} admiten cuentas")

    # ── 4 · EL CUADRE del balance, por ejercicio ────────────────────────────
    for i in cargados:
        etiqueta = anios.get(str(i), f"columna {i}")
        d = cuadre_balance(estructura, i)
        if abs(d) > TOLERANCIA:
            errores.append(f"el balance de {etiqueta} NO cuadra: activo y pasivo difieren en "
                           f"{d:,.2f}. Con un balance descuadrado no se emite papel")
        else:
            print(f"✔ el balance de {etiqueta} cuadra")

    # ── 5 · las cuentas asignadas y su epigrafe ─────────────────────────────
    asignadas = [c for c in cuentas if es_si(c.get("AsignadaCCAA"))]
    if not asignadas:
        errores.append("ninguna cuenta esta asignada a un epigrafe (AsignadaCCAA): el papel no "
                       "podria explicar de que cuentas sale cada linea")
    else:
        print(f"✔ cuentas asignadas a un epigrafe: {len(asignadas)} de {len(cuentas)}")

    codigos_estructura = {texto(f.get("CodigoCCAA")) for f in estructura}
    huerfanas = sorted({texto(c.get("CodigoCCAA")) for c in asignadas} - codigos_estructura - {""})
    if huerfanas:
        errores.append(f"{len(huerfanas)} epigrafes de cuentas no existen en la estructura "
                       f"({', '.join(huerfanas[:4])}…): el mapeo no es de este modelo de cuentas")

    # ── 6 · la cadena del saldo: cliente + ajustes + reclasif = auditoria ───
    if "SaldoCliente" in (cuentas[0] if cuentas else {}):
        rotas = []
        con_ajuste = 0
        for c in cuentas:
            cli, aj, rec, aud = cadena_del_saldo(c)
            if abs(aj) > TOLERANCIA or abs(rec) > TOLERANCIA:
                con_ajuste += 1
            if abs((cli + aj + rec) - aud) > TOLERANCIA:
                rotas.append(texto(c.get("Cuenta")))
        if rotas:
            avisos.append(f"en {len(rotas)} cuentas el saldo de auditoria no es cliente mas "
                          f"ajustes mas reclasificaciones ({', '.join(rotas[:4])}…): la columna "
                          "de conciliacion de esas filas no se puede sostener")
        else:
            print(f"✔ la cadena del saldo cuadra en las {len(cuentas)} cuentas "
                  f"({con_ajuste} con ajuste o reclasificacion)")
    else:
        avisos.append("el plan exportado no trae el saldo del cliente: el papel podra comparar "
                      "ejercicios pero NO lo presentado frente a lo auditado")

    # ── 7 · lo que suman las cuentas contra lo que dice el epigrafe ─────────
    por_epigrafe = cuentas_por_epigrafe(cuentas)
    if por_epigrafe and cargados:
        i = cargados[0]
        descuadres = []
        for f in hojas(estructura):
            cod = texto(f.get("CodigoCCAA"))
            if cod in por_epigrafe:
                d = round(abs(saldo(f, i)) - abs(por_epigrafe[cod]), DECIMALES)
                if abs(d) > TOLERANCIA:
                    descuadres.append((cod, d))
        if descuadres:
            avisos.append(f"en {len(descuadres)} epigrafes la suma de sus cuentas no coincide con "
                          f"el importe del epigrafe (el mayor, {max(descuadres, key=lambda x: abs(x[1]))[0]}): "
                          "el desglose por cuenta de esas lineas no se publica")
        else:
            print(f"✔ la suma de las cuentas coincide con el epigrafe en "
                  f"{sum(1 for f in hojas(estructura) if texto(f.get('CodigoCCAA')) in por_epigrafe)} lineas")

    # ── veredicto ───────────────────────────────────────────────────────────
    print()
    for e in errores:
        print("❌ " + e)
    for v in avisos:
        print("⚠ " + v)
    if errores:
        print("\nNO se puede hacer la revision. No se genera nada.")
        return 2
    if avisos:
        print("\nSe puede seguir, PERO estos avisos van al auditor en la entrega.")
        return 1
    print("\nTodo encaja.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
