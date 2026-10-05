#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Arnes de pruebas de la conciliacion diario <-> Gesia.

Parte del expediente real y va desviando los saldos de Gesia para comprobar que
cada tipo de descuadre se clasifica donde debe. Los casos que mas importan no
son los descuadres, sino los dos que NO deben marcarse: la cuenta que Gesia
calcula y el grupo con saldo cero.

Uso:  probar_conciliacion.py <diario.smn> <cuentas_gesia.json>
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import lib_diario as LD
import conciliar_gesia as CG

IR_T = 200_000.0
UMBRAL = IR_T * CG.TRIVIAL_PCT_IR_T / 100.0     # 10.000 EUR
CALCULADAS = {"080", "129"}


def estado_de(m, cuenta: str) -> str:
    fila = m[m["cuenta"] == cuenta]
    return fila["estado"].iloc[0] if len(fila) else "(ausente)"


def sin(datos, cuenta):
    return [d for d in datos if d["Cuenta"] != cuenta]


def desviar(datos, cuenta, delta):
    d2 = copy.deepcopy(datos)
    for d in d2:
        if d["Cuenta"] == cuenta:
            d["SaldoCliente"] = CG._num(d["SaldoCliente"]) + delta
    return d2


def main() -> int:
    diario, cuentas = sys.argv[1], sys.argv[2]
    df, _ = LD.cargar(diario)
    base = json.loads(Path(cuentas).read_text(encoding="utf-8"))

    def correr(datos):
        tmp = Path("/tmp/_cuentas_prueba.json")
        tmp.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
        g = CG.cargar_cuentas_gesia(tmp)
        return CG.conciliar(df, g, 3, CALCULADAS, UMBRAL)

    casos = [
        # (nombre, datos de Gesia, cuenta a inspeccionar, estado esperado)
        ("expediente sin tocar: 400 Proveedores",
         base, "400", CG.CONFORME),
        ("cuenta calculada por Gesia (080)",
         base, "080", CG.CALCULADA),
        ("cuenta calculada por Gesia (129)",
         base, "129", CG.CALCULADA),
        ("grupo con movimiento y saldo cero (472 IVA soportado)",
         base, "472", CG.CERO),
        ("desvio de 9.000 EUR en 400 (por debajo del umbral)",
         desviar(base, "400", 9_000), "400", CG.TRIVIAL),
        ("desvio de 25.000 EUR en 400 (material)",
         desviar(base, "400", 25_000), "400", CG.MATERIAL),
        ("desvio justo en el umbral (10.000 EUR)",
         desviar(base, "400", UMBRAL), "400", CG.TRIVIAL),
        ("desvio un centimo por encima del umbral",
         desviar(base, "400", UMBRAL + 0.01), "400", CG.MATERIAL),
        ("cuenta con saldo en Gesia que falta en el diario",
         base + [{"Cuenta": "999", "Nombre": "Inventada",
                  "SaldoCliente": "50000", "SaldoAnterior": "0", "SaldoAj": "0"}],
         "999", CG.MATERIAL),
        ("cuenta con saldo real que Gesia no trae (430 Clientes)",
         sin(base, "430"), "430", CG.MATERIAL),
    ]

    print(f"{'caso':56s} {'esperado':22s} resultado")
    print("-" * 100)
    fallos = 0
    for nombre, datos, cuenta, esperado in casos:
        m = correr(datos)
        obtenido = estado_de(m, cuenta)
        ok = obtenido == esperado
        fallos += 0 if ok else 1
        print(f"{nombre:56s} {esperado:22s} {obtenido:22s} {'OK' if ok else 'FALLO'}")

    # Comprobacion global sobre el expediente intacto.
    m = correr(base)
    materiales = int((m["estado"] == CG.MATERIAL).sum())
    triviales = int((m["estado"] == CG.TRIVIAL).sum())
    print("-" * 100)
    print(f"expediente intacto: {materiales} materiales, {triviales} triviales "
          f"-> {'OK' if materiales == 0 and triviales == 0 else 'FALLO'}")
    if materiales or triviales:
        fallos += 1
    print(f"{len(casos) - fallos}/{len(casos)} casos correctos")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
