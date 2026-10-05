#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fase 3: GENERACION DEL PANEL HTML.

Une los cuatro JSON de las fases anteriores en un unico payload y lo inyecta en
la plantilla. El modelo no escribe HTML en tiempo de ejecucion: la plantilla y
el JavaScript son activos del skill, y este script solo pega los datos.

El panel es un papel de trabajo, no una publicacion: se escribe como fichero y
lleva sellado en cabecera de que fichero sale, con que opciones de importacion
y cuando. Sin ese sello no se puede explicar seis meses despues.

Uso:
    generar_panel.py --contrato c.json --conciliacion o.json --punteo p.json
                     --analisis a.json --cliente "CLIENTE, S.A."
                     --cierre 2025-12-31 --generado 2026-08-21
                     --salida panel.html
                     [--resultado-08 ...] [--resultado-anterior ...] [--ajustes ...]

La fecha de generacion se pasa como parametro y no se toma del reloj: asi dos
ejecuciones del mismo expediente producen ficheros identicos.
"""

from __future__ import annotations

import argparse
import json
import sys

import hechos as HECHOS
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PLANTILLA = RAIZ / "assets" / "panel_estilo.html"
JS = RAIZ / "assets" / "panel.js"

CONFORMES = ("conforme", "conforme (saldo cero)")


def leer(ruta: str | None) -> dict | None:
    if not ruta:
        return None
    return json.loads(Path(ruta).read_text(encoding="utf-8"))


def _num(txt) -> float | None:
    if txt in (None, ""):
        return None
    return float(str(txt).strip().replace(" ", "").replace(",", "."))


def normalizar_cobertura(filas: list[dict]) -> list[dict]:
    """
    La cobertura sale de un DataFrame indexado por G2/G3, asi que la primera
    clave se llama 'G3' o 'G2' segun el nivel. Se renombra a 'grupo' aqui para
    que el JavaScript no tenga que adivinarlo.
    """
    out = []
    for f in filas:
        d = dict(f)
        for k in ("G1", "G2", "G3", "G4", "grupo"):
            if k in d:
                d["grupo"] = str(d.pop(k)) if k != "grupo" else str(d["grupo"])
                break
        out.append(d)
    return out


def construir(args) -> dict:
    contrato = leer(args.contrato)
    conc = leer(args.conciliacion)
    punt = leer(args.punteo)
    ana = leer(args.analisis)

    res_contrato = contrato["resumen"] if contrato else {}
    res_fase1 = res_contrato.get("resultado", {}) if contrato else {}

    meta = {
        "cliente": args.cliente,
        "cierre": args.cierre,
        "generado": args.generado,
        "fichero": (contrato or {}).get("fichero", {}).get("fichero", "diario"),
        "apuntes": res_contrato.get("apuntes", 0),
        "asientos": res_contrato.get("asientos", 0),
        "cuentas": res_contrato.get("cuentas", 0),
        "volumen_neto": res_contrato.get("volumen_neto", 0.0),
        "ir_t": _num(args.ir_t),
        "veredicto_contrato": (contrato or {}).get("veredicto", "no verificado"),
        "opciones": {
            "apertura": bool(res_contrato.get("apertura", {}).get("verificada")),
            "punteo": bool(res_contrato.get("punteo", {}).get("activo")),
            "aging_publicable": bool(res_contrato.get("punteo", {}).get("aging_publicable")),
        },
    }

    resultado = {
        "diario": res_fase1.get("resultado_diario"),
        "gesia_08": res_fase1.get("resultado_gesia_08"),
        "anterior": res_fase1.get("resultado_anterior"),
        "ajustes": res_fase1.get("ajustes_auditoria"),
        "auditoria": res_fase1.get("resultado_auditoria"),
        "cuadra": res_fase1.get("cuadra_con_gesia"),
        "ingresos": res_fase1.get("ingresos_grupo_7", 0.0),
        "gastos": res_fase1.get("gastos_grupo_6", 0.0),
    }

    payload: dict = {
        "meta": meta,
        "resultado": resultado,
        "contrato": {"hallazgos": (contrato or {}).get("hallazgos", [])},
        "conciliacion": None,
        "punteo": None,
        "diario": None,
    }

    if conc:
        grupos = conc.get("grupos", [])
        conciliado = sum(g.get("volumen", 0.0) for g in grupos
                         if g.get("estado") in CONFORMES)
        total = meta["volumen_neto"] or 1.0
        payload["conciliacion"] = {
            "resumen": conc.get("resumen", {}),
            "umbral_trivial": conc.get("umbral_trivial", 0.0),
            "nivel": conc.get("nivel", 3),
            "calculadas_excluidas": conc.get("calculadas_excluidas", []),
            "pct_volumen_conciliado": round(conciliado / total * 100, 2),
            "grupos": grupos,
        }

    if punt:
        payload["punteo"] = {
            "punteo": punt.get("punteo", False),
            "motivo": punt.get("motivo"),
            "aging_publicable": punt.get("aging_publicable", False),
            "umbral_cobertura": punt.get("umbral_cobertura", 80.0),
            "min_partidas": args.min_partidas,
            "resumen": punt.get("resumen", {}),
            "cobertura": normalizar_cobertura(punt.get("cobertura", [])),
            "plazos": punt.get("plazos", []),
            "aging": punt.get("aging", []),
        }

    if ana:
        payload["diario"] = {
            "mensual": ana.get("mensual", []),
            "perfil_semanal": ana.get("perfil_semanal", []),
            "serie_diaria": ana.get("serie_diaria", []),
            "dias_atipicos": ana.get("dias_atipicos", []),
            "tipos_asiento": ana.get("tipos_asiento", []),
            "atipicos": ana.get("atipicos", {}),
        }

    payload["hechos"] = HECHOS.construir(
        payload["meta"], payload["resultado"], payload["contrato"] or {},
        payload["conciliacion"], payload["punteo"], payload["diario"],
    )
    return payload


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--contrato", required=True)
    p.add_argument("--conciliacion")
    p.add_argument("--punteo")
    p.add_argument("--analisis", required=True)
    p.add_argument("--cliente", required=True)
    p.add_argument("--cierre", required=True)
    p.add_argument("--generado", required=True,
                   help="fecha de generacion (no se toma del reloj, para que el "
                        "resultado sea reproducible)")
    p.add_argument("--ir-t")
    p.add_argument("--min-partidas", type=int, default=5)
    p.add_argument("--salida", required=True)
    args = p.parse_args()

    datos = construir(args)
    if not datos["diario"]:
        print("[ABORTA] sin el analisis del diario no hay panel que generar")
        return 2

    plantilla = PLANTILLA.read_text(encoding="utf-8")
    js = JS.read_text(encoding="utf-8")
    titulo = f"{args.cliente} — Panel del diario {args.cierre}"

    # El payload va como JSON literal: separadores compactos y sin NaN, que
    # JSON.parse no acepta.
    crudo = json.dumps(datos, ensure_ascii=False, separators=(",", ":"),
                       allow_nan=False, default=str)

    html = (plantilla
            .replace("__TITULO__", titulo)
            .replace("__DATOS__", crudo)
            .replace("__JS__", js))

    salida = Path(args.salida)
    # El entregable vive en AsistenteIA/<carpeta-del-skill>/, que puede no existir aun:
    # la crea el script, no se confia en un mkdir previo.
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(html, encoding="utf-8")
    kb = salida.stat().st_size / 1024
    print(f"panel escrito en {salida}  ({kb:.0f} KB)")
    print(f"  cliente   {args.cliente}")
    print(f"  cierre    {args.cierre}")
    print(f"  contrato  {datos['meta']['veredicto_contrato']}")
    print(f"  opciones  apertura={datos['meta']['opciones']['apertura']}  "
          f"punteo={datos['meta']['opciones']['punteo']}  "
          f"aging={datos['meta']['opciones']['aging_publicable']}")
    print(f"  hechos    {len(datos['hechos'])} tarjetas: "
          + ", ".join(f"{s}={sum(1 for h in datos['hechos'] if h['severidad']==s)}"
                      for s in ("critico","alto","medio","bajo","correcto")))
    if datos["conciliacion"]:
        r = datos["conciliacion"]["resumen"]
        print(f"  conciliacion  {r.get('conformes', 0)} conformes, "
              f"{r.get('materiales', 0)} materiales, "
              f"{datos['conciliacion']['pct_volumen_conciliado']}% del volumen")
    return 0


if __name__ == "__main__":
    sys.exit(main())
