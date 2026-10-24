# -*- coding: utf-8 -*-
"""Genera el cuadro de mando del expediente: un unico HTML que se abre sin internet.

    python generar_cuadro.py --datos <carpeta> --generado <AAAA-MM-DD> --salida <fichero.html>

<carpeta> lleva lo que exporta el MCP (ver SKILL.md, paso 2):

    contexto.json   exportar_consulta(entidad='contexto'): cliente, cierre, IR y avance por area
    ir_areas.json   la importancia relativa por area (ETAreas)
    riesgos.json    los riesgos del encargo (RiesgosNIAS)
    cedula.json     las cuentas con AsignadaCedulaPrincipal, sus cinco ejercicios
    ratios.json     exportar_consulta(entidad='ratios')

Replica el Excel «Cuadro de mando Gesia» que usa la firma (Power Query sobre el API de Gesia),
sin modelo de datos: los filtros son JavaScript dentro de la pagina. Medido contra ese Excel en
el expediente de prueba el 22/10/2026: IR, avance, riesgos, cedula y ratios cuadran al centimo.

Nada lee el reloj: la fecha de generacion la pone quien llama.
Salida 0 = escrito; 2 = falta un fichero o no tiene la forma esperada (no se escribe nada).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FICHEROS = ("contexto", "ir_areas", "riesgos", "cedula", "ratios")

# Escala de valoracion de RiesgosNIAS. VA AL REVES de lo que parece: el 1 es lo peor. Contrastada
# con la pantalla de Gesia (un riesgo con 2 se muestra «Alto»; ver la ayuda de obtener_entidad).
VALORACION = {"1": "Máximo", "2": "Alto", "3": "Moderado", "4": "Poco"}
TIPO_RIESGO = {"1": "En las afirmaciones", "2": "General"}
CLASIFICACION = {"R": "Relevancia", "I": "Incorrección", "A": "Relevancia e incorrección"}


def _salida_utf8() -> None:
    for f in (sys.stdout, sys.stderr):
        try:
            f.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def numero(v):
    """Un importe de Gesia -texto con coma decimal- a float. Vacio es None: no se pudo calcular,
    que no es lo mismo que cero."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s:
        return None
    s = s.replace(".", "").replace(",", ".") if "," in s else s
    try:
        return float(s)
    except ValueError:
        return None


def booleano(v) -> bool:
    return str(v).strip().lower() in ("true", "1", "-1", "si", "sí")


def cargar(carpeta: Path) -> tuple[dict, list[str]]:
    datos, defectos = {}, []
    for nombre in FICHEROS:
        ruta = carpeta / f"{nombre}.json"
        if not ruta.exists():
            defectos.append(f"falta {ruta.name}")
            continue
        try:
            datos[nombre] = json.loads(ruta.read_text(encoding="utf-8-sig"))
        except ValueError as exc:
            defectos.append(f"{ruta.name} no es JSON: {exc}")
    if "contexto" in datos and not isinstance(datos["contexto"], dict):
        defectos.append("contexto.json tiene que ser el objeto de contexto_expediente")
    for nombre in ("ir_areas", "riesgos", "cedula", "ratios"):
        if nombre in datos and not isinstance(datos[nombre], list):
            defectos.append(f"{nombre}.json tiene que ser una lista de filas")
    return datos, defectos


def preparar(datos: dict) -> tuple[dict, list[str]]:
    """Lo que la pagina necesita, ya convertido. Devuelve (modelo, avisos)."""
    avisos = []
    ctx = datos["contexto"]
    ir_t = numero(ctx.get("IR_T"))

    # los ejercicios: CodigoAuditoria 1 es el que se audita; la cedula trae el año de cada uno
    anios = {}
    for f in datos["cedula"]:
        cod, anio = str(f.get("CodigoAuditoria", "")).strip(), str(f.get("Año", "")).strip()
        if cod and anio:
            anios[cod] = anio
    codigos = sorted(anios, key=lambda c: int(c) if c.isdigit() else 99)
    ejercicios = [anios[c] for c in codigos]
    if not ejercicios:
        avisos.append("la cedula no trae ejercicios: el panel sale sin la evolucion de saldos")

    nombres_area = {}
    avance = []
    for a in ctx.get("areas") or []:
        cod = str(a.get("CodigoArea", "")).strip()
        nombres_area[cod] = str(a.get("Area", "")).strip()
        total = int(numero(a.get("Total")) or 0)
        avance.append({"codigo": cod, "area": nombres_area[cod], "total": total,
                       "realizadas": int(numero(a.get("Realizadas")) or 0),
                       "verificadas": int(numero(a.get("Verificadas")) or 0)})

    ir_areas = {}
    for f in datos["ir_areas"]:
        cod = str(f.get("CodigoArea", "")).strip()
        nombres_area.setdefault(cod, str(f.get("Area", "")).strip())
        ir_areas[cod] = {"trabajo": numero(f.get("IR_Trabajo")), "informe": numero(f.get("IR_Informe"))}

    riesgos = []
    for f in datos["riesgos"]:
        riesgos.append({
            "area": str(f.get("CodigoArea", "")).strip(),
            "riesgo": str(f.get("Riesgo", "")).strip(),
            "significativo": booleano(f.get("Significativo")),
            "amra": booleano(f.get("AMRA")),
            "tipo": TIPO_RIESGO.get(str(f.get("TipoRiesgo", "")).strip(), ""),
            "clasificacion": CLASIFICACION.get(str(f.get("Clasificacion", "")).strip(), ""),
            "ri": VALORACION.get(str(f.get("CodigoValorRIA_RI", "")).strip(), ""),
            "rci": VALORACION.get(str(f.get("CodigoValorRIA_RCI", "")).strip(), ""),
            "rim": VALORACION.get(str(f.get("CodigoValorRIA_RIM", "")).strip(), ""),
            "rim_n": int(numero(f.get("CodigoValorRIA_RIM")) or 9),
            "afirmaciones": [n for n, c in (("Integridad", "Integridad"), ("Existencia", "Existencia"),
                                            ("Exactitud", "Exactitud"), ("Valoración", "Valoracion"))
                             if booleano(f.get(c))],
            "referencia": str(f.get("CodigoReferencia", "")).strip(),
        })
    riesgos.sort(key=lambda r: (r["area"], r["rim_n"], r["riesgo"]))

    # la cedula: una fila por cuenta con sus saldos por ejercicio, en el orden de `ejercicios`
    cuentas = {}
    for f in datos["cedula"]:
        cta = str(f.get("Cuenta", "")).strip()
        if not cta:
            continue
        c = cuentas.setdefault(cta, {"cuenta": cta, "nombre": str(f.get("Nombre", "")).strip(),
                                     "area": str(f.get("CodigoAreaCP", "")).strip(), "saldos": {}})
        c["saldos"][str(f.get("CodigoAuditoria", "")).strip()] = numero(f.get("SaldoAuditoria"))
    cedula = []
    sin_area = 0
    for c in sorted(cuentas.values(), key=lambda x: x["cuenta"]):
        if not c["area"]:
            sin_area += 1
            continue
        c["saldos"] = [c["saldos"].get(cod) for cod in codigos]
        cedula.append(c)
    if sin_area:
        avisos.append(f"{sin_area} cuenta(s) de la cedula principal sin area asignada (CodigoAreaCP vacio): no salen en el panel")
    for c in cedula:
        nombres_area.setdefault(c["area"], c["area"])

    ratios = []
    for f in datos["ratios"]:
        valores = [numero(f.get(f"ValorAño{i}")) for i in range(1, len(ejercicios) + 1)] if ejercicios else []
        ratios.append({
            "codigo": str(f.get("CodigoElementoRA", "")).strip(),
            "elemento": str(f.get("Elemento", "")).strip(),
            "naturaleza": str(f.get("Naturaleza", "")).strip(),
            "familia": str(f.get("Familia", "")).strip(),
            "relevancia": str(f.get("Relevancia", "")).strip(),
            "fase": str(f.get("CodigoFaseRA", "")).strip(),
            "descripcion": str(f.get("Descripcion", "")).strip(),
            "valores": valores,
        })
    ratios.sort(key=lambda r: r["codigo"])

    areas = sorted(nombres_area.items())
    modelo = {
        "cliente": str(ctx.get("RazonSocialCliente", "")).strip(),
        "cierre": str(ctx.get("FechaCierre", "")).split()[0] if ctx.get("FechaCierre") else "",
        "ir": {"P": numero(ctx.get("IR_P")), "T": ir_t, "I": numero(ctx.get("IR_I"))},
        "ejercicios": ejercicios,
        "areas": [{"codigo": c, "area": n} for c, n in areas],
        "avance": avance,
        "ir_areas": ir_areas,
        "riesgos": riesgos,
        "cedula": cedula,
        "ratios": ratios,
    }
    if ir_t in (None, 0):
        avisos.append("la IR de trabajo viene a cero o vacia: no se ha calculado en Gesia, y la marca de "
                      "variacion se compara solo contra la IR de cada area")
    return modelo, avisos


def resumen(modelo: dict) -> list[str]:
    """Lo que el modelo cuenta al entregar: recuentos y variaciones que superan la IR del area."""
    lineas = [f"cliente: {modelo['cliente']} · cierre {modelo['cierre']} · ejercicios {', '.join(modelo['ejercicios'])}",
              f"areas: {len(modelo['areas'])} · riesgos: {len(modelo['riesgos'])} "
              f"({sum(r['significativo'] for r in modelo['riesgos'])} significativos) · "
              f"cuentas en la cedula principal: {len(modelo['cedula'])} · ratios: {len(modelo['ratios'])}"]
    superan = []
    for c in modelo["cedula"]:
        s = c["saldos"]
        if len(s) >= 2 and s[0] is not None and s[1] is not None:
            umbral = (modelo["ir_areas"].get(c["area"]) or {}).get("trabajo") or modelo["ir"]["T"]
            var = s[0] - s[1]
            if umbral and abs(var) > umbral:
                superan.append((c["area"], c["cuenta"], var))
    lineas.append(f"cuentas cuya variacion del ultimo ejercicio supera la IR de su area: {len(superan)}")
    for area, cta, var in superan[:15]:
        lineas.append(f"   {area} · {cta}: {var:,.2f}".replace(",", " "))
    return lineas


def escribir(modelo: dict, generado: str, salida: Path) -> None:
    datos = json.dumps(modelo, ensure_ascii=False, allow_nan=False).replace("</", "<\\/")
    titulo = f"Cuadro de mando · {modelo['cliente']}"
    html = (PLANTILLA.replace("{{TITULO}}", _esc(titulo)).replace("{{GENERADO}}", _esc(generado))
            .replace("{{DATOS}}", datos))
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(html, encoding="utf-8")


def _esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def main(argv=None) -> int:
    _salida_utf8()
    p = argparse.ArgumentParser(description="Cuadro de mando del expediente, en un HTML")
    p.add_argument("--datos", required=True, help="carpeta con contexto, ir_areas, riesgos, cedula y ratios .json")
    p.add_argument("--generado", required=True, help="fecha de hoy, AAAA-MM-DD: la pone quien llama")
    p.add_argument("--salida", required=True, help="el .html que se escribe")
    a = p.parse_args(argv)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", a.generado):
        print("ERROR: --generado tiene que ser AAAA-MM-DD")
        return 2
    datos, defectos = cargar(Path(a.datos))
    if defectos:
        print("NO SE ESCRIBE EL PANEL:")
        for d in defectos:
            print("   - " + d)
        return 2
    modelo, avisos = preparar(datos)
    salida = Path(a.salida)
    try:
        escribir(modelo, a.generado, salida)
    except PermissionError:
        print("ERROR: no se puede escribir " + str(salida))
        print("       O esta abierto (cierralo y repite), o el entorno no tiene permiso para escribir en")
        print("       esa carpeta (pide el permiso y repite).")
        return 2
    print("Panel escrito: " + str(salida))
    for linea in resumen(modelo):
        print("  " + linea)
    if avisos:
        print("PARA CONTAR AL ENTREGAR:")
        for av in avisos:
            print("  AVISO · " + av)
    return 0


# ── La pagina ─────────────────────────────────────────────────────────────────
# Una sola, sin recursos externos: se abre desde el disco del auditor y tiene que funcionar sin
# internet. Los graficos son SVG dibujados aqui; los filtros, el selector de area.
PLANTILLA = r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{TITULO}}</title>
<style>
/* Gesia: el morado del icono del producto (#4C0084) como color de marca; grises con un punto
   violeta; rojo y ambar solo para lo que pide atencion. Sin fuentes externas: se abre sin internet. */
:root {
  --marca: #4c0084; --marca-2: #6d2fa8; --marca-suave: #efe8f7; --marca-tenue: #b9a0d8;
  --bg: #f6f5f8; --panel: #ffffff; --fg: #1f1a26; --muted: #6a6375; --line: #e4e0ea; --chip: #f1eef5;
  --rojo: #b42318; --ambar: #b54708; --verde: #2f7d4f;
  --cab-fg: #ffffff; --cab-muted: #d9c9ee;
  --pal: #4c0084,#c77d1a,#1f8a84,#b23a6b,#5a6b7d,#7a8b2e,#9b6fd0,#8a5a2b;
  color-scheme: light;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --marca: #b48ce0; --marca-2: #c9a8ee; --marca-suave: #2a2136; --marca-tenue: #5e4580;
    --bg: #141118; --panel: #1c1822; --fg: #ebe7f0; --muted: #a59eb0; --line: #2f2938; --chip: #26202e;
    --rojo: #f0857a; --ambar: #e8a55c; --verde: #6fc493;
    --pal: #b48ce0,#e8a55c,#5cc4bc,#e07aa4,#9fb0c2,#b6c76a,#d6bdf2,#c99a6a;
    color-scheme: dark;
  }
}
:root[data-theme="dark"] {
  --marca: #b48ce0; --marca-2: #c9a8ee; --marca-suave: #2a2136; --marca-tenue: #5e4580;
  --bg: #141118; --panel: #1c1822; --fg: #ebe7f0; --muted: #a59eb0; --line: #2f2938; --chip: #26202e;
  --rojo: #f0857a; --ambar: #e8a55c; --verde: #6fc493;
  --pal: #b48ce0,#e8a55c,#5cc4bc,#e07aa4,#9fb0c2,#b6c76a,#d6bdf2,#c99a6a;
  color-scheme: dark;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--fg);
  font: 14px/1.5 "Segoe UI Variable Text", "Segoe UI", system-ui, -apple-system, Arial, sans-serif; }
header.cab { background: #4c0084; color: var(--cab-fg); }
.cab .dentro { max-width: 1180px; margin: 0 auto; padding: 18px 24px; display: flex; gap: 16px; align-items: center; flex-wrap: wrap; }
.cab .logo { width: 44px; height: 44px; flex: none; }
.cab .logo text { font-size: 27px; font-weight: 700; fill: #ffffff; }
.cab .textos { flex: 1 1 320px; min-width: 0; }
.cab .eyebrow { font-size: 11.5px; letter-spacing: .12em; text-transform: uppercase; color: var(--cab-muted); }
.cab h1 { margin: 1px 0 0; font-size: 23px; font-weight: 600; letter-spacing: .1px; text-wrap: balance; }
.cab .sub { color: var(--cab-muted); font-size: 13px; }
.cab .fecha { font-size: 12.5px; color: var(--cab-muted); text-align: right; font-variant-numeric: tabular-nums; }
select, button { font: inherit; color: var(--fg); background: var(--panel); border: 1px solid var(--line);
  border-radius: 6px; padding: 6px 10px; cursor: pointer; }
button:hover, select:hover { border-color: var(--marca-tenue); }
button.on { background: var(--marca); border-color: var(--marca); color: #fff; }
:root[data-theme="dark"] button.on { color: #141118; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) button.on { color: #141118; } }
button:focus-visible, select:focus-visible, input:focus-visible, a:focus-visible { outline: 2px solid var(--marca); outline-offset: 2px; }
main { max-width: 1180px; margin: 0 auto; padding: 20px 24px 48px; display: flex; flex-direction: column; gap: 16px; }
section.bloque { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 18px 20px; min-width: 0; }
section.bloque h2 { margin: 0 0 14px; font-size: 15.5px; font-weight: 600; color: var(--marca); display: flex; gap: 10px; align-items: baseline; flex-wrap: wrap; }
h2 .nota { font-weight: 400; font-size: 12.5px; color: var(--muted); }
.fila { display: flex; gap: 14px; flex-wrap: wrap; }
.fila > * { min-width: 0; }
.cifra { flex: 1 1 170px; background: var(--marca-suave); border-radius: 8px; padding: 12px 16px; }
.cifra .k { font-size: 11.5px; color: var(--muted); text-transform: uppercase; letter-spacing: .07em; }
.cifra .v { font-size: 24px; font-weight: 600; color: var(--marca); font-variant-numeric: tabular-nums; }
.tabla { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; }
th, td { padding: 7px 9px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
th { font-size: 11.5px; color: var(--muted); font-weight: 600; white-space: nowrap; text-transform: uppercase; letter-spacing: .04em; }
td.n, th.n { text-align: right; white-space: nowrap; }
tbody tr:hover td { background: var(--chip); }
tr.total td { font-weight: 600; border-top: 2px solid var(--marca-tenue); border-bottom: 0; }
a { color: var(--marca); text-decoration: none; }
a:hover { text-decoration: underline; }
.chip { display: inline-block; font-size: 11.5px; padding: 2px 8px; border-radius: 10px; background: var(--chip); margin: 1px 3px 1px 0; white-space: nowrap; }
.chip.sig { background: var(--rojo); color: #fff; }
.chip.amra { background: var(--ambar); color: #fff; }
.chip.ir { background: var(--marca-suave); color: var(--marca); font-weight: 600; }
.v-Máximo, .v-Alto { color: var(--rojo); font-weight: 600; }
.v-Moderado { color: var(--ambar); font-weight: 600; }
.v-Poco { color: var(--verde); }
.supera { color: var(--rojo); font-weight: 600; }
.marca { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: var(--rojo); margin-left: 6px; }
.barras { display: flex; flex-direction: column; gap: 7px; }
.barras .b { display: grid; grid-template-columns: minmax(120px, 290px) 1fr 220px; gap: 12px; align-items: center; }
.barras .nom { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pista { position: relative; height: 14px; background: var(--chip); border-radius: 7px; overflow: hidden; }
.pista .r { position: absolute; left: 0; top: 0; bottom: 0; background: var(--marca-tenue); border-radius: 7px; }
.pista .vv { position: absolute; left: 0; top: 4px; bottom: 4px; background: var(--marca); border-radius: 4px; }
.barras .pct { font-size: 12px; color: var(--muted); text-align: right; font-variant-numeric: tabular-nums; }
.leyenda { display: flex; gap: 16px; font-size: 12px; color: var(--muted); margin: 0 0 10px; flex-wrap: wrap; }
.leyenda i { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 6px; vertical-align: -1px; }
.vacio { color: var(--muted); font-style: italic; padding: 8px 0; }
.filtros { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 12px; align-items: center; }
.etq { font-size: 11.5px; text-transform: uppercase; letter-spacing: .07em; color: var(--muted); }
.slicer { display: flex; flex-wrap: wrap; gap: 4px; flex: 1 1 560px; min-width: 0; }
.slicer button { padding: 3px 10px; font-size: 12.5px; border-radius: 5px; font-variant-numeric: tabular-nums; }
.casilla { display: inline-flex; gap: 6px; align-items: center; font-size: 13px; cursor: pointer; }
input[type=checkbox] { accent-color: var(--marca); }
svg text { fill: var(--muted); font-size: 11px; }
svg .eje { stroke: var(--line); }
.spark { width: 90px; height: 22px; }
td input[type=checkbox] { margin: 0; }
footer { color: var(--muted); font-size: 12px; text-align: center; padding: 6px 24px 28px; }
@media (max-width: 640px) {
  .cab .dentro, main { padding-left: 14px; padding-right: 14px; }
  .cab .fecha { text-align: left; }
  .barras .b { grid-template-columns: 1fr; gap: 3px; }
  .barras .pct { text-align: left; }
}
@media (prefers-reduced-motion: no-preference) { button, select { transition: border-color .12s, background-color .12s; } }
</style>
</head>
<body>
<header class="cab">
  <div class="dentro">
    <svg class="logo" viewBox="0 0 44 44" aria-hidden="true"><rect width="44" height="44" rx="10" fill="#ffffff" fill-opacity=".14"/><text x="22" y="30" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" font-size="27" font-weight="700" fill="#ffffff">g</text></svg>
    <div class="textos">
      <div class="eyebrow">Cuadro de mando · Gesia</div>
      <h1 id="cliente"></h1>
      <div class="sub" id="subtitulo"></div>
    </div>
    <div class="fecha" id="generado"></div>
  </div>
</header>
<main>
  <section class="bloque" id="b-estado">
    <h2>Estado de la auditoría <span class="nota">referencias disponibles, realizadas y verificadas por área</span></h2>
    <div class="leyenda"><span><i style="background:var(--marca-tenue)"></i>Realizadas</span><span><i style="background:var(--marca)"></i>Verificadas</span></div>
    <div class="barras" id="estado"></div>
  </section>

  <section class="bloque" id="b-ir">
    <h2>Importancia relativa</h2>
    <div class="fila" id="ir-cifras"></div>
    <div class="tabla" style="margin-top:12px"><table id="ir-tabla"></table></div>
  </section>

  <section class="bloque" id="b-riesgos">
    <h2>Riesgos del encargo <span class="nota" id="riesgos-nota"></span></h2>
    <div class="tabla"><table id="riesgos"></table></div>
  </section>

  <section class="bloque" id="b-cedula">
    <h2>Análisis del área <span class="nota" id="cedula-nota"></span></h2>
    <div class="filtros">
      <span class="etq">Área</span>
      <div id="slicer" class="slicer" role="group" aria-label="Área"></div>
      <span id="area-ir" class="chip ir"></span>
    </div>
    <div id="area-riesgos" class="filtros"></div>
    <div class="filtros">
      <button id="invertir" type="button">Invertir signo</button>
      <span class="nota" style="font-size:12.5px;color:var(--muted)">Marca roja: la variación del último ejercicio supera la IR de trabajo del área.</span>
    </div>
    <div class="tabla"><table id="cedula"></table></div>
    <div id="grafico-cedula" style="margin-top:14px"></div>
  </section>

  <section class="bloque" id="b-ratios">
    <h2>Ratios <span class="nota">revisión analítica de Gesia; un hueco es un ratio que no se pudo calcular</span></h2>
    <div class="filtros">
      <select id="f-nat" aria-label="Naturaleza"></select>
      <select id="f-fam" aria-label="Familia"></select>
      <select id="f-rel" aria-label="Relevancia"></select>
      <select id="f-fase" aria-label="Fase"></select>
      <label class="casilla"><input type="checkbox" id="f-sindatos" checked> Ocultar ratios sin datos</label>
    </div>
    <div class="tabla"><table id="ratios"></table></div>
    <div id="grafico-ratios" style="margin-top:14px"></div>
  </section>
</main>
<footer id="pie"></footer>

<script id="datos" type="application/json">{{DATOS}}</script>
<script>
(function () {
  "use strict";
  var D = JSON.parse(document.getElementById("datos").textContent);
  var GENERADO = "{{GENERADO}}";
  // useGrouping "always": en es-ES el navegador no pone el punto de miles a los numeros de cuatro
  // cifras (1638,58), y en una columna de importes eso descoloca la lectura
  var fmt0 = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 0, useGrouping: "always" });
  var fmt2 = new Intl.NumberFormat("es-ES", { minimumFractionDigits: 2, maximumFractionDigits: 2, useGrouping: "always" });
  var fmtR = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 4, useGrouping: "always" });
  var fmtP = new Intl.NumberFormat("es-ES", { style: "percent", maximumFractionDigits: 1 });
  var estado = { area: "", invertir: false, marcadas: {}, ratiosMarcados: {} };
  try { var g = JSON.parse(localStorage.getItem("cm-estado") || "{}"); if (g.area) estado.area = g.area; } catch (e) {}
  // el area tambien puede venir en el enlace: «…html#CO»
  var h0 = decodeURIComponent((location.hash || "").replace(/^#/, ""));
  if (h0 && D.areas.some(function (a) { return a.codigo === h0; })) estado.area = h0;

  function el(t, a, h) { var e = document.createElement(t); if (a) for (var k in a) e.setAttribute(k, a[k]); if (h != null) e.innerHTML = h; return e; }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function imp(v) { return v == null ? "" : fmt2.format(v); }
  function nombreArea(c) { for (var i = 0; i < D.areas.length; i++) if (D.areas[i].codigo === c) return D.areas[i].area; return c; }
  function irArea(c) { var x = D.ir_areas[c]; return (x && x.trabajo) || D.ir.T || null; }
  function paleta(i) { var p = getComputedStyle(document.documentElement).getPropertyValue("--pal").split(","); return (p[i % p.length] || "#888").trim(); }

  document.getElementById("cliente").textContent = D.cliente;
  document.getElementById("subtitulo").textContent = "Auditoría al " + D.cierre + " · ejercicios " + D.ejercicios.slice().reverse().join(", ");
  document.getElementById("generado").textContent = "Generado el " + GENERADO.split("-").reverse().join("/");
  document.getElementById("pie").textContent = "Cuadro de mando generado el " + GENERADO + " con los datos del expediente en esa fecha. Lo que cambie después en Gesia no está aquí.";

  // la segmentacion de area, como la del Excel: un boton por area y «Todas». Solo filtra el
  // analisis del area; el estado, la IR y los riesgos ensenan siempre todo el encargo
  var slicer = document.getElementById("slicer");
  function elegirArea(cod) { estado.area = cod; estado.marcadas = {}; guardar(); pintar(); }
  [{ codigo: "", area: "Todas las áreas" }].concat(D.areas).forEach(function (a) {
    var b = el("button", { type: "button", "data-area": a.codigo, title: a.area }, esc(a.codigo || "Todas"));
    b.addEventListener("click", function () { elegirArea(a.codigo); });
    slicer.appendChild(b);
  });
  function pintarSlicer() {
    slicer.querySelectorAll("button").forEach(function (b) {
      var on = b.getAttribute("data-area") === estado.area;
      b.className = on ? "on" : ""; b.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }
  document.getElementById("invertir").addEventListener("click", function () { estado.invertir = !estado.invertir; pintar(); });
  function guardar() { try { localStorage.setItem("cm-estado", JSON.stringify({ area: estado.area })); } catch (e) {} }

  // ── estado de la auditoria ──
  function pintarEstado() {
    var c = document.getElementById("estado"); c.innerHTML = "";
    D.avance.forEach(function (a) {
      var pr = a.total ? a.realizadas / a.total : 0, pv = a.total ? a.verificadas / a.total : 0;
      var b = el("div", { "class": "b" });
      b.appendChild(el("div", { "class": "nom", title: a.area }, esc(a.codigo + " · " + a.area)));
      var p = el("div", { "class": "pista" });
      p.appendChild(el("div", { "class": "r", style: "width:" + (pr * 100) + "%" }));
      p.appendChild(el("div", { "class": "vv", style: "width:" + (pv * 100) + "%" }));
      b.appendChild(p);
      b.appendChild(el("div", { "class": "pct" }, a.realizadas + " de " + a.total + " realizadas · " + a.verificadas + " verificadas"));
      b.title = a.area + ": " + a.realizadas + " realizadas y " + a.verificadas + " verificadas de " + a.total;
      c.appendChild(b);
    });
    if (!D.avance.length) c.appendChild(el("div", { "class": "vacio" }, "El expediente no trae referencias por área."));
  }

  // ── importancia relativa ──
  function pintarIR() {
    var c = document.getElementById("ir-cifras"); c.innerHTML = "";
    [["Planificación", D.ir.P], ["Trabajo", D.ir.T], ["Informe", D.ir.I]].forEach(function (x) {
      var d = el("div", { "class": "cifra" });
      d.appendChild(el("div", { "class": "k" }, "IR de " + x[0].toLowerCase()));
      d.appendChild(el("div", { "class": "v" }, x[1] == null ? "—" : fmt0.format(x[1])));
      c.appendChild(d);
    });
    var t = document.getElementById("ir-tabla");
    var h = "<thead><tr><th>Área</th><th class='n'>IR de trabajo</th><th class='n'>IR de informe</th><th class='n'>% sobre la IR global</th></tr></thead><tbody>";
    var cods = Object.keys(D.ir_areas).sort();
    cods.forEach(function (cod) {
      var x = D.ir_areas[cod];
      h += "<tr><td>" + esc(cod + " · " + nombreArea(cod)) + "</td><td class='n'>" + imp(x.trabajo) + "</td><td class='n'>" + imp(x.informe) + "</td><td class='n'>" + (D.ir.T && x.trabajo != null ? fmtP.format(x.trabajo / D.ir.T) : "") + "</td></tr>";
    });
    if (!cods.length) h += "<tr><td colspan='4' class='vacio'>El expediente no trae importancia relativa por área.</td></tr>";
    t.innerHTML = h + "</tbody>";
    var chip = document.getElementById("area-ir");
    chip.textContent = estado.area ? "IR de trabajo del área: " + (irArea(estado.area) == null ? "—" : fmt2.format(irArea(estado.area))) : "IR de trabajo: " + (D.ir.T == null ? "—" : fmt2.format(D.ir.T));
  }

  // ── riesgos ──
  function pintarRiesgos() {
    var rs = D.riesgos;
    document.getElementById("riesgos-nota").textContent = D.riesgos.length + " en el encargo · " + D.riesgos.filter(function (r) { return r.significativo; }).length + " significativos";
    var h = "<thead><tr><th>Área</th><th>Riesgo</th><th></th><th>Inherente</th><th>Control</th><th>Incorrección material</th><th>Afirmaciones</th><th>Ref.</th></tr></thead><tbody>";
    rs.forEach(function (r) {
      h += "<tr><td>" + esc(r.area) + "</td><td>" + esc(r.riesgo) + "<div style='font-size:12px;color:var(--muted)'>" + esc([r.tipo, r.clasificacion].filter(Boolean).join(" · ")) + "</div></td><td>"
        + (r.significativo ? "<span class='chip sig'>Significativo</span>" : "") + (r.amra ? "<span class='chip amra'>AMRA</span>" : "")
        + "</td><td class='v-" + esc(r.ri) + "'>" + esc(r.ri) + "</td><td class='v-" + esc(r.rci) + "'>" + esc(r.rci) + "</td><td class='v-" + esc(r.rim) + "'>" + esc(r.rim) + "</td><td>"
        + r.afirmaciones.map(function (a) { return "<span class='chip'>" + esc(a) + "</span>"; }).join("") + "</td><td>" + esc(r.referencia) + "</td></tr>";
    });
    if (!rs.length) h += "<tr><td colspan='8' class='vacio'>El expediente no tiene riesgos identificados en Gesia.</td></tr>";
    document.getElementById("riesgos").innerHTML = h + "</tbody>";
  }

  // ── cedula del area ──
  function signo(v) { return v == null ? null : (estado.invertir ? -v : v); }
  function pintarCedula() {
    var btn = document.getElementById("invertir"); btn.className = estado.invertir ? "on" : "";
    var t = document.getElementById("cedula"), g = document.getElementById("grafico-cedula"), nota = document.getElementById("cedula-nota");
    // los riesgos del area, en una linea: como la tabla de riesgos de la hoja de areas del Excel
    var ar = document.getElementById("area-riesgos");
    if (estado.area) {
      var rsa = D.riesgos.filter(function (r) { return r.area === estado.area; });
      ar.innerHTML = "<span class='etq'>Riesgos del área</span>" + (rsa.length ? rsa.map(function (r) {
        return "<span class='chip" + (r.significativo ? " sig" : "") + "' title='" + esc(r.riesgo + (r.rim ? " · incorrección material " + r.rim : "")) + "'>" + esc(r.riesgo) + (r.rim ? " · " + esc(r.rim) : "") + "</span>";
      }).join("") : "<span class='nota' style='font-size:12.5px;color:var(--muted)'>ninguno identificado en Gesia</span>");
    } else { ar.innerHTML = ""; }
    var E = D.ejercicios;
    if (!estado.area) {
      nota.textContent = "elige un área para ver su cédula; aquí, el resumen de todas";
      var h = "<thead><tr><th>Área</th><th class='n'>Cuentas</th><th class='n'>Saldo " + esc(E[0] || "") + "</th><th class='n'>Variación</th><th class='n'>IR de trabajo</th><th class='n'>Cuentas que la superan</th></tr></thead><tbody>";
      var porArea = {};
      D.cedula.forEach(function (c) { (porArea[c.area] = porArea[c.area] || []).push(c); });
      Object.keys(porArea).sort().forEach(function (a) {
        var cs = porArea[a], s0 = 0, s1 = 0, n = 0, ir = irArea(a);
        cs.forEach(function (c) { var v0 = c.saldos[0], v1 = c.saldos[1]; s0 += v0 || 0; s1 += v1 || 0; if (ir && v0 != null && v1 != null && Math.abs(v0 - v1) > ir) n++; });
        h += "<tr><td><a href='#' data-area='" + esc(a) + "'>" + esc(a + " · " + nombreArea(a)) + "</a></td><td class='n'>" + cs.length + "</td><td class='n'>" + imp(signo(s0)) + "</td><td class='n'>" + imp(E.length > 1 ? signo(s0 - s1) : null) + "</td><td class='n'>" + imp(ir) + "</td><td class='n" + (n ? " supera" : "") + "'>" + n + "</td></tr>";
      });
      t.innerHTML = h + "</tbody>";
      t.querySelectorAll("a[data-area]").forEach(function (a) { a.addEventListener("click", function (ev) { ev.preventDefault(); elegirArea(a.getAttribute("data-area")); window.scrollTo({ top: document.getElementById("b-cedula").offsetTop - 90 }); }); });
      g.innerHTML = "";
      return;
    }
    var cs = D.cedula.filter(function (c) { return c.area === estado.area; });
    var ir = irArea(estado.area);
    nota.textContent = estado.area + " · " + nombreArea(estado.area) + " · cuentas de la cédula principal";
    if (!Object.keys(estado.marcadas).length) {
      cs.slice().sort(function (a, b) { return Math.abs(b.saldos[0] || 0) - Math.abs(a.saldos[0] || 0); }).slice(0, 6).forEach(function (c) { estado.marcadas[c.cuenta] = true; });
    }
    var h = "<thead><tr><th></th><th>Cuenta</th><th>Nombre</th>";
    E.forEach(function (e) { h += "<th class='n'>" + esc(e) + "</th>"; });
    h += "<th class='n'>Variación</th><th class='n'>% variación</th></tr></thead><tbody>";
    var tot = E.map(function () { return 0; });
    cs.forEach(function (c) {
      var v0 = c.saldos[0], v1 = c.saldos[1], dv = (v0 != null && v1 != null) ? v0 - v1 : null;
      var sup = ir && dv != null && Math.abs(dv) > ir;
      h += "<tr><td><input type='checkbox' data-cta='" + esc(c.cuenta) + "'" + (estado.marcadas[c.cuenta] ? " checked" : "") + " aria-label='Ver en el gráfico'></td><td>" + esc(c.cuenta) + "</td><td>" + esc(c.nombre) + "</td>";
      c.saldos.forEach(function (v, i) { tot[i] += v || 0; h += "<td class='n'>" + imp(signo(v)) + "</td>"; });
      h += "<td class='n" + (sup ? " supera" : "") + "'>" + imp(signo(dv)) + (sup ? "<span class='marca' title='Supera la IR de trabajo del área'></span>" : "") + "</td><td class='n'>" + (dv != null && v1 ? fmtP.format(dv / Math.abs(v1)) : "") + "</td></tr>";
    });
    // con un solo ejercicio no hay variacion: el anterior no es cero, no existe
    var dt = E.length > 1 ? tot[0] - tot[1] : null, supt = ir && dt != null && Math.abs(dt) > ir;
    h += "<tr class='total'><td></td><td colspan='2'>Total del área</td>";
    tot.forEach(function (v) { h += "<td class='n'>" + imp(signo(v)) + "</td>"; });
    h += "<td class='n" + (supt ? " supera" : "") + "'>" + imp(signo(dt)) + (supt ? "<span class='marca'></span>" : "") + "</td><td class='n'>" + (tot[1] ? fmtP.format(dt / Math.abs(tot[1])) : "") + "</td></tr>";
    if (!cs.length) h = "<tbody><tr><td class='vacio'>El área no tiene cuentas asignadas a la cédula principal.</td></tr>";
    t.innerHTML = h + "</tbody>";
    t.querySelectorAll("input[data-cta]").forEach(function (i) { i.addEventListener("change", function () { estado.marcadas[i.getAttribute("data-cta")] = i.checked; if (!i.checked) delete estado.marcadas[i.getAttribute("data-cta")]; pintarGraficoCedula(cs); }); });
    pintarGraficoCedula(cs);
  }
  function pintarGraficoCedula(cs) {
    var series = cs.filter(function (c) { return estado.marcadas[c.cuenta]; }).map(function (c) {
      return { nombre: c.cuenta + " · " + c.nombre, valores: c.saldos.slice().reverse().map(signo) };
    });
    lineas(document.getElementById("grafico-cedula"), D.ejercicios.slice().reverse(), series, "Evolución anual de las cuentas marcadas", fmt0);
  }

  // ── ratios ──
  function opciones(id, titulo, valores, def) {
    var s = document.getElementById(id); s.innerHTML = "";
    s.appendChild(el("option", { value: "" }, esc(titulo)));
    valores.forEach(function (v) { s.appendChild(el("option", { value: v }, esc(v))); });
    if (def != null) s.value = def;
    s.addEventListener("change", pintarRatios);
  }
  function unicos(k) { var u = {}; D.ratios.forEach(function (r) { if (r[k]) u[r[k]] = 1; }); return Object.keys(u).sort(); }
  opciones("f-nat", "Toda naturaleza", unicos("naturaleza"), unicos("naturaleza").indexOf("Ratio") >= 0 ? "Ratio" : "");
  opciones("f-fam", "Todas las familias", unicos("familia"));
  opciones("f-rel", "Toda relevancia", unicos("relevancia").map(function (r) { return "Relevancia " + r; }));
  opciones("f-fase", "Todas las fases", unicos("fase").map(function (f) { return "Fase " + f; }));
  document.getElementById("f-sindatos").addEventListener("change", pintarRatios);
  function pintarRatios() {
    var nat = document.getElementById("f-nat").value, fam = document.getElementById("f-fam").value,
        rel = document.getElementById("f-rel").value.replace("Relevancia ", ""), fase = document.getElementById("f-fase").value.replace("Fase ", "");
    // sin datos: los cinco ejercicios vacios (no se pudo calcular) o a cero
    var ocultar = document.getElementById("f-sindatos").checked;
    var rs = D.ratios.filter(function (r) { return (!nat || r.naturaleza === nat) && (!fam || r.familia === fam) && (!rel || r.relevancia === rel) && (!fase || r.fase === fase)
      && (!ocultar || r.valores.some(function (v) { return v != null && v !== 0; })); });
    var E = D.ejercicios;
    var h = "<thead><tr><th></th><th>Código</th><th>Elemento</th>";
    E.forEach(function (e) { h += "<th class='n'>" + esc(e) + "</th>"; });
    h += "<th>Evolución</th></tr></thead><tbody>";
    rs.forEach(function (r) {
      h += "<tr><td><input type='checkbox' data-rat='" + esc(r.codigo) + "'" + (estado.ratiosMarcados[r.codigo] ? " checked" : "") + " aria-label='Ver en el gráfico'></td><td>" + esc(r.codigo) + "</td><td title='" + esc(r.descripcion) + "'>" + esc(r.elemento) + "<div style='font-size:12px;color:var(--muted)'>" + esc(r.familia) + "</div></td>";
      r.valores.forEach(function (v) { h += "<td class='n'>" + (v == null ? "" : fmtR.format(v)) + "</td>"; });
      h += "<td>" + spark(r.valores.slice().reverse()) + "</td></tr>";
    });
    if (!rs.length) h += "<tr><td colspan='" + (E.length + 4) + "' class='vacio'>Ningún ratio con esos filtros.</td></tr>";
    var t = document.getElementById("ratios"); t.innerHTML = h + "</tbody>";
    t.querySelectorAll("input[data-rat]").forEach(function (i) { i.addEventListener("change", function () { var k = i.getAttribute("data-rat"); if (i.checked) estado.ratiosMarcados[k] = true; else delete estado.ratiosMarcados[k]; pintarGraficoRatios(); }); });
    pintarGraficoRatios();
  }
  function pintarGraficoRatios() {
    var series = D.ratios.filter(function (r) { return estado.ratiosMarcados[r.codigo]; }).map(function (r) { return { nombre: r.codigo + " · " + r.elemento, valores: r.valores.slice().reverse() }; });
    var c = document.getElementById("grafico-ratios");
    if (!series.length) { c.innerHTML = "<div class='vacio'>Marca ratios en la tabla para compararlos en un gráfico.</div>"; return; }
    lineas(c, D.ejercicios.slice().reverse(), series, "Ratios marcados", fmtR);
  }

  // ── graficos SVG ──
  function spark(vals) {
    var v = vals.filter(function (x) { return x != null; });
    if (v.length < 2) return "";
    var mn = Math.min.apply(null, v), mx = Math.max.apply(null, v), r = mx - mn || 1, w = 90, hh = 22, n = vals.length;
    var pts = [];
    vals.forEach(function (x, i) { if (x != null) pts.push((i * (w - 4) / (n - 1) + 2).toFixed(1) + "," + (hh - 3 - (x - mn) / r * (hh - 6)).toFixed(1)); });
    var last = pts[pts.length - 1].split(",");
    return "<svg class='spark' viewBox='0 0 " + w + " " + hh + "' role='img' aria-label='evolución'><polyline fill='none' stroke='var(--marca)' stroke-width='1.5' points='" + pts.join(" ") + "'/><circle cx='" + last[0] + "' cy='" + last[1] + "' r='2.2' fill='var(--marca)'/></svg>";
  }
  function lineas(cont, etiquetas, series, titulo, f) {
    cont.innerHTML = "";
    if (!series.length) { cont.appendChild(el("div", { "class": "vacio" }, "Marca cuentas en la tabla para verlas en el gráfico.")); return; }
    var W = 760, H = 260, ml = 86, mr = 16, mt = 14, mb = 28;
    var todos = []; series.forEach(function (s) { s.valores.forEach(function (v) { if (v != null) todos.push(v); }); });
    if (!todos.length) { cont.appendChild(el("div", { "class": "vacio" }, "Sin valores que dibujar.")); return; }
    var mn = Math.min.apply(null, todos.concat([0])), mx = Math.max.apply(null, todos.concat([0]));
    if (mn === mx) { mx += 1; }
    var paso = escala(mn, mx), y0 = Math.floor(mn / paso) * paso, y1 = Math.ceil(mx / paso) * paso;
    var X = function (i) { return ml + (etiquetas.length === 1 ? (W - ml - mr) / 2 : i * (W - ml - mr) / (etiquetas.length - 1)); };
    var Y = function (v) { return mt + (y1 - v) / (y1 - y0) * (H - mt - mb); };
    var s = "<svg viewBox='0 0 " + W + " " + H + "' width='100%' role='img' aria-label='" + esc(titulo) + "'>";
    for (var v = y0; v <= y1 + paso / 2; v += paso) {
      s += "<line class='eje' x1='" + ml + "' x2='" + (W - mr) + "' y1='" + Y(v) + "' y2='" + Y(v) + "'" + (Math.abs(v) < paso / 1e6 ? " stroke-width='1.5'" : " stroke-dasharray='2 3'") + "/>";
      s += "<text x='" + (ml - 8) + "' y='" + (Y(v) + 4) + "' text-anchor='end'>" + esc(f.format(v)) + "</text>";
    }
    etiquetas.forEach(function (e, i) { s += "<text x='" + X(i) + "' y='" + (H - 8) + "' text-anchor='middle'>" + esc(e) + "</text>"; });
    series.forEach(function (se, k) {
      var col = paleta(k), d = "", abierto = false;
      se.valores.forEach(function (v, i) { if (v == null) { abierto = false; return; } d += (abierto ? "L" : "M") + X(i).toFixed(1) + " " + Y(v).toFixed(1) + " "; abierto = true; });
      s += "<path d='" + d + "' fill='none' stroke='" + col + "' stroke-width='2'/>";
      se.valores.forEach(function (v, i) { if (v != null) s += "<circle cx='" + X(i).toFixed(1) + "' cy='" + Y(v).toFixed(1) + "' r='3' fill='" + col + "'><title>" + esc(se.nombre + " · " + etiquetas[i] + ": " + f.format(v)) + "</title></circle>"; });
    });
    s += "</svg>";
    var ley = "<div class='leyenda'>" + series.map(function (se, k) { return "<span><i style='background:" + paleta(k) + "'></i>" + esc(se.nombre) + "</span>"; }).join("") + "</div>";
    cont.innerHTML = ley + s;
  }
  function escala(mn, mx) {
    var r = (mx - mn) / 5, p = Math.pow(10, Math.floor(Math.log10(r))), n = r / p;
    return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * p;
  }

  function pintar() { pintarSlicer(); pintarEstado(); pintarIR(); pintarRiesgos(); pintarCedula(); }
  pintar();
  pintarRatios();
})();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    sys.exit(main())
