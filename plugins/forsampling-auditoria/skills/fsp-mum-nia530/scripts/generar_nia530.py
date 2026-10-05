# -*- coding: utf-8 -*-
"""Escribe el papel de trabajo NIA-ES 530 de una prueba MUM en Word.

    python generar_nia530.py --datos nia530.json --generado 2026-09-30 \
        --salida "<expediente>/AsistenteIA/FspMum/Papel NIA-ES 530 <prueba> <cliente> <fecha>.docx"

Lee `nia530.json` -el esquema esta en el SKILL.md- y escribe el .docx. TODO DATO NULL SALE COMO
«PENDIENTE» EN AMBAR, con quien lo aporta entre parentesis: FS (ForSampling), GS (Gesia), DOC
(documentos) o AU (auditor). No infiere, no estima, no rellena con ejercicios anteriores.

Es el porte a Python del generador que David escribio en JavaScript (docx de npm) para el skill
local del 30/09/2026. Mismas diez secciones y el mismo anexo, mismos textos, misma leyenda de
origen. Se porto porque los skills del plugin generan Word con python-docx -identificacion-
riesgos, cuestionario-cuentas-anuales, investigacion-entidad- y un skill con Node dentro
obligaria a que el equipo del auditor lo tuviera.

Reglas heredadas de fsp-mum, y que este fichero hace cumplir por construccion:

  * no proyecta ni concluye: la proyeccion NO se guarda en ningun fichero de ForSampling
    -se calcula al emitir el informe- y este papel no la recalcula ni la transcribe de un PDF,
    que no es fuente. El apartado 8 dice donde esta y deja el hueco
  * los errores por exceso y por defecto se listan separados y NO se netean
  * las unidades MUM son la suma de Repeticiones; los elementos distintos, otra cosa
  * el tercero va por su token (PROV/CLI/TER): ningun nombre ni NIF sale en el Word
  * `--generado` es obligatorio: nada en este proyecto lee el reloj
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

FUENTE = "Calibri"
AZUL = RGBColor(0x1F, 0x38, 0x64)
GRIS_TXT = RGBColor(0x7F, 0x7F, 0x7F)
SOMBRA_CAB = "D9E2F3"
AMBAR = "FFF2CC"
VERDE = "E2EFDA"
CLARO = "F2F2F2"


# ── utilidades de formato ─────────────────────────────────────────────────────

def nulo(v) -> bool:
    return v is None or v == ""


def eur(v) -> str:
    """1.234.567,89 con signo menos tipografico; «—» si no consta."""
    if nulo(v):
        return "—"
    v = float(v)
    s = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("−" if v < 0 else "") + s


def pct(v) -> str:
    if nulo(v):
        return "—"
    return f"{float(v):.2f}".replace(".", ",") + " %"


class Pend:
    """Un texto que va en ambar: es un dato que falta, con quien lo aporta."""
    def __init__(self, texto: str):
        self.texto = texto

    def __str__(self):
        return self.texto


def PEND(origen: str) -> Pend:
    return Pend("PENDIENTE (" + origen + ")")


def V(x, origen: str, f=str):
    """El valor formateado, o PENDIENTE con su origen."""
    return PEND(origen) if nulo(x) else f(x)


def _sombrear(celda, hex_color: str) -> None:
    tcPr = celda._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tcPr.append(shd)


def _bordes(celda) -> None:
    tcPr = celda._tc.get_or_add_tcPr()
    borders = OxmlElement("w:tcBorders")
    for lado in ("top", "left", "bottom", "right"):
        b = OxmlElement("w:" + lado)
        b.set(qn("w:val"), "single"); b.set(qn("w:sz"), "4")
        b.set(qn("w:color"), "A6A6A6")
        borders.append(b)
    tcPr.append(borders)


def _run(p, texto: str, tam=10, negrita=False, cursiva=False, color=None):
    r = p.add_run(texto)
    r.font.name = FUENTE
    r.font.size = Pt(tam)
    r.bold, r.italic = negrita, cursiva
    if color is not None:
        r.font.color.rgb = color
    return r


def parrafo(doc, partes, tam=10, despues=5, cursiva=False):
    """`partes` es un texto, o una lista de textos y de tuplas (texto, negrita)."""
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(despues)
    for parte in (partes if isinstance(partes, list) else [partes]):
        if isinstance(parte, tuple):
            _run(p, parte[0], tam, negrita=parte[1], cursiva=cursiva)
        else:
            _run(p, str(parte), tam, cursiva=cursiva)
    return p


def h1(doc, texto: str):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(14)
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.keep_with_next = True
    _run(p, texto, 13, negrita=True, color=AZUL)
    return p


def h2(doc, texto: str):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(9)
    p.paragraph_format.space_after = Pt(5)
    p.paragraph_format.keep_with_next = True
    _run(p, texto, 11, negrita=True, color=AZUL)
    return p


def vineta(doc, texto: str):
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.space_after = Pt(3)
    _run(p, texto, 10)
    return p


def _celda(celda, valor, negrita=False, derecha=False, sombra=None, tam=9):
    """Escribe un valor en una celda. Un Pend va en ambar y en negrita, siempre."""
    celda.text = ""
    texto = str(valor) if valor is not None else "—"
    if isinstance(valor, Pend):
        sombra, negrita = AMBAR, True
    lineas = texto.split("\n")
    p = celda.paragraphs[0]
    for i, linea in enumerate(lineas):
        if i:
            p = celda.add_paragraph()
        p.paragraph_format.space_after = Pt(1)
        if derecha:
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        _run(p, linea, tam, negrita=negrita)
    if sombra:
        _sombrear(celda, sombra)
    _bordes(celda)


def tabla(doc, anchos_cm: list, cabeceras, filas: list, derecha: tuple = ()):
    """Tabla con bordes finos; la cabecera sombreada; las columnas de `derecha` alineadas."""
    ncol = len(anchos_cm)
    t = doc.add_table(rows=0, cols=ncol)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    if cabeceras:
        celdas = t.add_row().cells
        for i, c in enumerate(cabeceras):
            _celda(celdas[i], c, negrita=True, sombra=SOMBRA_CAB)
    for fila in filas:
        celdas = t.add_row().cells
        for i, v in enumerate(fila):
            sombra = None
            if isinstance(v, dict):          # {"t": texto, "sombra": VERDE}
                sombra, v = v.get("sombra"), v.get("t")
            _celda(celdas[i], v, derecha=(i in derecha), sombra=sombra)
    for fila in t.rows:
        for i, celda in enumerate(fila.cells):
            celda.width = Cm(anchos_cm[i])
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return t


def caja(doc, partes, sombra=None, alto_min_cm: float = 0):
    """Un recuadro de una celda, para avisos y para el hueco de la conclusion."""
    t = doc.add_table(rows=1, cols=1)
    t.autofit = False
    celda = t.rows[0].cells[0]
    celda.width = Cm(17.0)
    celda.text = ""
    p = celda.paragraphs[0]
    for parte in (partes if isinstance(partes, list) else [partes]):
        if isinstance(parte, tuple):
            _run(p, parte[0], 9.5, negrita=parte[1] == "b", cursiva=parte[1] == "i")
        else:
            _run(p, str(parte), 9.5)
    if sombra:
        _sombrear(celda, sombra)
    _bordes(celda)
    if alto_min_cm:
        trPr = t.rows[0]._tr.get_or_add_trPr()
        h = OxmlElement("w:trHeight")
        h.set(qn("w:val"), str(int(alto_min_cm * 567)))
        h.set(qn("w:hRule"), "atLeast")
        trPr.append(h)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return t


def lab(texto: str) -> dict:
    return {"t": texto, "sombra": CLARO}


# ── el papel ──────────────────────────────────────────────────────────────────

def generar(S: dict, generado: str) -> Document:
    P = S.get("p") or {}
    E = S.get("elementos") or []
    R = S.get("resultados")
    fin = S.get("estado") or {}
    ir = P.get("ir")
    tam = P.get("tam") or {}
    VP = S.get("valor_poblacion")

    con_doc = [e for e in E if not e.get("sin_documento")]
    sin_doc = [e for e in E if e.get("sin_documento")]
    unidades = sum(int(e.get("unidades") or 1) for e in E)
    distintos = sum(float(e.get("libros") or 0) for e in E)
    ponderado = sum(float(e.get("libros") or 0) * int(e.get("unidades") or 1) for e in E)
    exceso = [e for e in con_doc if not nulo(e.get("error")) and float(e["error"]) > 0.005]
    defecto = [e for e in con_doc if not nulo(e.get("error")) and float(e["error"]) < -0.005]
    comparados = [e for e in con_doc if not nulo(e.get("error_auditor")) and not nulo(e.get("error"))]
    coinciden = [e for e in comparados if abs(float(e["error"]) - float(e["error_auditor"])) < 0.005]

    doc = Document()
    for s in doc.sections:
        s.page_width, s.page_height = Cm(21.0), Cm(29.7)
        s.left_margin = s.right_margin = s.top_margin = s.bottom_margin = Cm(2.0)
    estilo = doc.styles["Normal"]
    estilo.font.name = FUENTE
    estilo.font.size = Pt(10)

    # cabecera y pie: la referencia arriba, y abajo que es un borrador con IA
    anio = str(S.get("ejercicio_ini") or "")[-4:]
    cab = doc.sections[0].header.paragraphs[0]
    _run(cab, (f"{S['entidad']} · " if S.get("entidad") else "")
         + f"Ejercicio {anio} · {S.get('referencia', '')} · Muestreo de auditoría (NIA-ES 530)", 8, color=GRIS_TXT)
    pie = doc.sections[0].footer.paragraphs[0]
    pie.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _run(pie, f"Borrador preparado por Asistente IA el {generado}. La conclusión es del auditor.", 8, color=GRIS_TXT)

    # ── portada ──
    p = doc.add_paragraph(); _run(p, "PAPEL DE TRABAJO · MUESTREO DE AUDITORÍA (NIA-ES 530)", 16, negrita=True, color=AZUL)
    p = doc.add_paragraph(); p.paragraph_format.space_after = Pt(8)
    _run(p, f"Prueba {S.get('tipo') or 'MUM'} «{S.get('prueba', '')}» · Referencia {S.get('referencia', '')}", 13, color=AZUL)

    estado_txt = (Pend(f"NO FINALIZADA: PruebaFinalizada = False; Realizado = {'Sí' if fin.get('realizado') else 'No'}; "
                       f"Verificado = {'Sí' if fin.get('verificado') else 'No'}") if fin.get("finalizada") is False
                  else "Finalizada" if fin.get("finalizada") is True else PEND("FS"))
    tabla(doc, [4.4, 12.6], None, [
        [lab("Entidad auditada"), V(S.get("entidad"), "GS")],
        [lab("Ejercicio"), f"{S.get('ejercicio_ini', '')} – {S.get('ejercicio_fin', '')}"
                           + (f" (cierre {S['cierre']})" if S.get("cierre") else "")],
        [lab("Área / referencia"), f"{S.get('area') or ''} · {S.get('referencia', '')}"],
        [lab("Prueba en ForSampling"), f"MuestraId {S.get('muestra_id', '')} · tipo {S.get('tipo') or 'MUM'} · "
                                       f"cliente de muestreo «{S.get('cli', '')}»"],
        [lab("Informe de ForSampling"), "Anexo a adjuntar por el auditor: la proyección solo existe en el informe que emite "
                                        "ForSampling, no en sus ficheros"],
        [lab("Estado de la prueba"), estado_txt],
        [lab("Modo de trabajo"), Pend("SOLO ForSampling: sin expediente de Gesia; lo que no está en ForSampling se solicita (apartado 9)")
                                 if S.get("modo") == "solo_fs" else "ForSampling y expediente de Gesia"],
        [lab("Preparado por / fecha"), "______________________    ____ / ____ / ________"],
        [lab("Revisado por / fecha"), "______________________    ____ / ____ / ________"],
    ])
    parrafo(doc, [("Naturaleza de este borrador. ", True),
                  "Las cifras de diseño, población y selección proceden de los ficheros de ForSampling y de Gesia, con la "
                  "fuente indicada en cada línea. Los importes «según documento» los ha propuesto el asistente de IA y "
                  "deben ser revisados por el auditor. La proyección del error no se recalcula ni se transcribe: ForSampling "
                  "la calcula al emitir su informe, que se adjunta como anexo. La conclusión de auditoría y las decisiones "
                  "de juicio están en blanco: son del auditor."], tam=9.5)
    h2(doc, "Leyenda de origen y regla cuando solo hay fichero de ForSampling")
    tabla(doc, [2.0, 15.0], ["Marca", "Significado"], [
        ["FS", "ForSampling: .cli (catálogo de pruebas, parámetros y catálogos), .smp (población importada) y .pcu "
               "(muestra y evaluación), leídos por el API. El informe que emite ForSampling es un anexo, no una fuente."],
        ["GS", "Gesia: expediente .gs3 (importancia relativa, riesgos, sumas y saldos, referencias) y diario contable .smn."],
        ["DOC", "Documentos escaneados de la carpeta del área (facturas)."],
        ["AU", "Auditor: juicio, decisión o documento que no consta en ningún fichero."],
    ])
    caja(doc, [("Regla de aplicación. ", "b"),
               "Si el encargo dispone únicamente del fichero de ForSampling y no del expediente de Gesia (.gs3), todo dato "
               "marcado GS o AU no se infiere, no se estima y no se completa con valores de ejercicios anteriores: se deja "
               "en blanco, se marca PENDIENTE y se solicita al auditor con la lista del apartado 9. Lo que ForSampling no "
               "guarda en sus ficheros (la distribución, los resultados de la proyección) no se rellena desde ningún "
               "documento: se deja el hueco y se adjunta el informe emitido."], AMBAR)

    # ── 1 ──
    h1(doc, "1. Objetivo y alcance (NIA-ES 530, apartados 4 y 6)")
    if nulo(S.get("objetivo")):
        parrafo(doc, [("Objetivo de la prueba: ", True), "PENDIENTE (FS): la prueba no tiene objetivo ni observaciones en Muestreos"])
    else:
        parrafo(doc, f"Objetivo de la prueba, según consta en ForSampling (FS · Muestreos): {S['objetivo']}")
    parrafo(doc, "Procedimiento: comparar el importe contabilizado de cada elemento seleccionado con el que sostiene el "
                 "documento de soporte (término de comparación: el que fija la propia muestra) y registrar la diferencia "
                 "como error. La prueba mide el importe; no evalúa la clasificación contable de la operación.")
    tabla(doc, [5.4, 7.6, 4.0], ["Dato", "Valor", "Origen"], [
        ["Afirmación que se pretende cubrir", V(S.get("afirmacion"), "AU"), "AU"],
        ["Riesgo valorado del área (NIA-ES 315)", V(S.get("riesgo_area"), "GS / AU"), "GS / AU"],
        ["Fecha de cierre del ejercicio", V(S.get("cierre"), "GS"), "GS"],
    ])

    # ── 2 ──
    h1(doc, "2. Población (apartados 5 y 6; NIA-ES 500 sobre fiabilidad de la información)")
    cu, di = S.get("cuadre") or {}, S.get("diario") or {}
    tabla(doc, [5.8, 7.6, 3.6], ["Dato", "Valor", "Origen"], [
        ["Descripción de la población", V(S.get("descripcion_poblacion"), "FS"), "FS · .cli, DatosPSMum"],
        ["Elemento / unidad de muestreo", f"{S.get('unidad') or 'Elemento'} (apunte del diario); selección MUM sobre "
                                          "unidades monetarias", "FS · .cli"],
        ["Número de elementos", V(S.get("n_elementos"), "FS"), "FS · .cli y .pcu"],
        ["Valor de la población (campo principal)", PEND("FS") if nulo(VP)
         else f"{eur(VP)} €" + (f" ({S['poblacion_nota']})" if S.get("poblacion_nota") else ""), "FS · .smp / .pcu"],
        ["Fichero de importación", V(S.get("fichero_smp"), "FS"), "FS · .cli"],
        ["Fichero de la prueba", V(S.get("fichero_pcu"), "FS"), "FS · .cli"],
        ["Cuadre .smp ↔ .pcu", {"t": cu.get("texto"), "sombra": VERDE} if cu.get("ok") is True
         else Pend("PENDIENTE (FS): " + (cu.get("texto") or "no comprobado")), "FS"],
        ["Elementos de la muestra en el diario", {"t": di.get("texto"), "sombra": VERDE} if di.get("ok") is True
         else Pend("PENDIENTE (GS): " + (di.get("texto") or "no comprobado")), "GS · diario .smn"],
    ])
    h2(doc, "Conciliación con la contabilidad")
    por_cuenta = S.get("por_cuenta") or []
    if por_cuenta:
        tp = sum(float(c["poblacion"]) for c in por_cuenta)
        tc = sum(float(c["contable"]) for c in por_cuenta)
        filas = [[str(c["cuenta"]), eur(c["poblacion"]), eur(c["contable"]), eur(float(c["contable"]) - float(c["poblacion"]))]
                 for c in por_cuenta]
        filas.append([{"t": "Total", "sombra": CLARO}, eur(tp), eur(tc), eur(tc - tp)])
        tabla(doc, [2.6, 4.8, 4.8, 4.8], ["Cuenta", "Población de la prueba", "Saldo cliente (sumas y saldos)",
                                          "Diferencia (contabilidad − población)"], filas, derecha=(1, 2, 3))
        parrafo(doc, f"Fuente: población, FS (.pcu); saldo cliente, GS (sumas y saldos). La diferencia neta es el "
                     f"{pct((tc - tp) / tc * 100 if tc else None)} del saldo contable."
                     + (" " + S["conciliacion_nota"] if S.get("conciliacion_nota") else ""), tam=9.5)
    else:
        tabla(doc, [5.8, 11.2], None, [[lab("Saldo contable por cuenta"),
                                        Pend("PENDIENTE (GS): solicitar el saldo contable por cuenta de la población (sumas y saldos)")]])
    tabla(doc, [5.8, 11.2], None, [[lab("Conciliación detallada de la diferencia"),
                                    Pend("PENDIENTE (AU): detallar las partidas excluidas y concluir sobre la completitud de la población")
                                    if nulo(S.get("conciliacion_detalle")) else S["conciliacion_detalle"]]])

    # ── 3 ──
    h1(doc, "3. Diseño de la muestra y parámetros (apartados 6 y 7)")
    conf = P.get("confianza")
    et = P.get("et")
    tabla(doc, [4.6, 4.4, 4.2, 3.8], ["Parámetro", "Valor", "Origen / campo", "Observación"], [
        ["Tipo de muestreo", "Estadístico, por unidades monetarias (MUM)", "FS · Muestreos.Tipo", ""],
        ["Nivel de confianza / riesgo de muestreo", PEND("FS") if nulo(conf) else f"{conf} % / {100 - float(conf):g} %",
         "FS · RiesgoGeneralId → TM_Confianza", f"Tipo de trabajo «{P['tipo_trabajo']}»" if P.get("tipo_trabajo") else ""],
        ["Distribución", Pend("No se guarda en los ficheros de ForSampling"), "FS · no consta", "Figura solo en el informe emitido"],
        ["Errores esperados en la población", PEND("FS") if nulo(P.get("err_esp_n")) else f"{P['err_esp_n']} / {pct(P.get('err_esp_pct'))}",
         "FS · DatosPSMum", "" if nulo(P.get("tie")) else f"Tie = {pct(P['tie'])}"],
        ["Error tolerable (incorrección tolerable)", PEND("FS") if nulo(et)
         else f"{eur(et)} €" + (f" ({pct(float(et) / float(VP) * 100)} de la población)" if not nulo(VP) and float(VP) else ""),
         "FS · ErrorTolerableValor", "" if nulo(P.get("tp")) else f"Tp = {pct(P['tp'])} (ET − Tie)"],
        ["Importancia relativa de referencia", f"IR_P = {eur(ir['p'])} €; IR_T = {eur(ir['t'])} €; IR_I = {eur(ir['i'])} €" if ir
         else Pend("PENDIENTE (GS): solicitar"), "GS · CalculosIRElecciones", P.get("ir_nota") or ""],
        ["Relación ET / IR de trabajo", f"{eur(et)} = {float(et) / float(ir['t']) * 100:.0f} % de {eur(ir['t'])}"
         if (not nulo(et) and ir and not nulo(ir.get("t")) and float(ir["t"])) else Pend("PENDIENTE"),
         "Cálculo aritmético", "ForSampling no guarda la regla de fijación"],
        ["Tamaño de muestra", PEND("FS") if nulo(tam.get("seleccionado"))
         else f"Deseado {tam.get('propuesto', '—')} · seleccionado {tam['seleccionado']} · elementos únicos {tam.get('unicos', '—')}",
         "FS · DatosPSMum y fichero de la prueba",
         f"{tam.get('seleccionado', '—')} unidades = suma de repeticiones de {tam.get('unicos', '—')} elementos"],
        ["Método de selección", V(P.get("metodo"), "FS"), "FS · MetodoSelId descodificado", P.get("metodo_nota") or ""],
        ["Factor de confianza aplicado", Pend("No documentado") if nulo(P.get("factor")) else str(P["factor"]),
         "FS · TM_Confianza / TM_Lambda", P.get("factor_nota") or ""],
    ])
    tabla(doc, [5.8, 11.2], None, [[lab("Motivación del error tolerable y del nivel de confianza"),
                                    Pend("PENDIENTE (AU): justificar la fijación del error tolerable y la aceptación del riesgo de muestreo")
                                    if nulo(P.get("motivacion")) else P["motivacion"]]])

    # ── 4 ──
    h1(doc, "4. Selección de los elementos (apartado 8)")
    repetidos = [e for e in E if int(e.get("unidades") or 1) > 1]
    parrafo(doc, f"Selección con probabilidad proporcional al importe (MUM)"
                 + (f", método {str(P['metodo']).lower()}" if P.get("metodo") else "")
                 + (f", ejecutada el {S['seleccion_fecha']}" if S.get("seleccion_fecha") else "")
                 + ". Los elementos de mayor importe pueden seleccionarse más de una vez"
                 + (": " + " y ".join(f"el elemento {e['id']} figura {e['unidades']} veces" for e in repetidos) if repetidos else "")
                 + ". Los terceros aparecen como código; la equivalencia con el nombre está en la hoja «Tokens» del papel en Excel.")
    tabla(doc, [1.7, 2.6, 2.0, 3.4, 1.9, 5.4], ["Elemento", "Fecha", "Cuenta", "Importe libros (€)", "Unidades", "Tercero"],
          [[str(e["id"]), str(e.get("fecha") or "—"), str(e.get("cuenta") or "—"), eur(e.get("libros")),
            str(e.get("unidades") or 1), e.get("token") or "—"] for e in E], derecha=(3, 4))
    parrafo(doc, f"Fuente: FS · .pcu (muestra). Totales de la selección: {len(E)} elementos, {unidades} unidades; importe "
                 f"contable de los elementos distintos {eur(distintos)} €"
                 + (f" ({pct(distintos / float(VP) * 100)} de la población); ponderado por repeticiones {eur(ponderado)} € "
                    f"({pct(ponderado / float(VP) * 100)})" if not nulo(VP) and float(VP) else "")
                 + ". Son datos descriptivos, no una conclusión sobre la población.", tam=9.5)
    sin_el = S.get("sin_elementos") or []
    if sin_el:
        t_sin = sum(float(c["importe"]) for c in sin_el)
        parrafo(doc, [("Cobertura por cuentas. ", True),
                      "Las cuentas " + " y ".join(f"{c['cuenta']} ({eur(c['importe'])} €)" for c in sin_el)
                      + " no tienen ningún elemento seleccionado"
                      + (f"; juntas son el {pct(t_sin / float(VP) * 100)} de la población" if not nulo(VP) and float(VP) else "")
                      + ". Valoración de su efecto sobre la conclusión: auditor."], tam=9.5)

    # ── 5 ──
    h1(doc, "5. Procedimientos aplicados (apartados 9 a 11)")
    vineta(doc, "Localización del documento de soporte de cada elemento en la carpeta de documentación del área"
                + (f" ({S['n_documentos']} documentos disponibles)" if S.get("n_documentos") else "")
                + (f"; {S['modo_facturas']}" if S.get("modo_facturas") else "") + ".")
    vineta(doc, "Lectura de número, fecha, base, IVA y total, y comparación del importe contabilizado con el término de "
                "comparación que fija la propia muestra.")
    for t in S.get("procedimientos_extra") or []:
        vineta(doc, t)
    vineta(doc, f"Resultado de la localización: {len(con_doc)} de {len(E)} elementos con documento."
                + (f" Sin documento: elemento{'s' if len(sin_doc) > 1 else ''} {', '.join(str(e['id']) for e in sin_doc)} (apartado 7)."
                   if sin_doc else ""))
    for t in S.get("avisos") or []:
        vineta(doc, t)
    parrafo(doc, "Los valores «según documento» los ha propuesto el asistente de IA. La evaluación registrada en ForSampling "
                 "(SaldoAuditoria y ErrorAuditoria) es la del auditor.", tam=9.5, cursiva=True)

    # ── 6 ──
    h1(doc, "6. Resultados por elemento (apartado 12)")
    tabla(doc, [1.7, 2.6, 3.0, 2.2, 2.7, 4.8],
          ["Elemento", "Libros (€)", "Según documento (€)", "Error (€)", "Error según auditor en FS (€)", "Nota"],
          [[str(e["id"]), eur(e.get("libros")),
            {"t": "sin documento", "sombra": AMBAR} if e.get("sin_documento") else eur(e.get("doc")),
            "—" if e.get("sin_documento") else eur(e.get("error")), eur(e.get("error_auditor")), e.get("nota") or ""]
           for e in E], derecha=(1, 2, 3, 4))
    parrafo(doc, f"Elementos con error por exceso: {', '.join(str(e['id']) for e in exceso) or 'ninguno'}. "
                 f"Elementos con error por defecto: {', '.join(str(e['id']) for e in defecto) or 'ninguno'}. "
                 "No se suman ni se compensan errores de signo contrario."
                 + (f" En {len(comparados)} elementos medidos con evaluación del auditor en ForSampling, el resultado del "
                    f"asistente coincide en {len(coinciden)}." if comparados else ""), tam=9.5)

    # ── 7 ──
    h1(doc, "7. Desviaciones, incorrecciones y anomalías (apartados 11, 12 y 13)")
    filas7 = [[lab(f"Incorrecciones en los {len(con_doc)} elementos medidos"),
               ("Elementos con diferencia: " + "; ".join(f"{e['id']} ({eur(e['error'])} €)" for e in exceso + defecto)
                + f". Naturaleza y causa: {S.get('causa_errores') or 'PENDIENTE (AU)'}.") if (exceso or defecto)
               else "Ninguna identificada."],
              [lab("Anomalías (apartado 13)"),
               S.get("anomalias") or (Pend("PENDIENTE (AU): valorar si alguna incorrección es anómala") if (exceso or defecto)
                                      else "Ninguna identificada.")]]
    for e in sin_doc:
        filas7.append([lab(f"Elemento {e['id']} · {eur(e.get('libros'))} € · cuenta {e.get('cuenta', '')}"),
                       e.get("sin_doc_texto") or "No se ha podido aplicar el procedimiento diseñado."])
        filas7.append([lab(f"Tratamiento del elemento {e['id']}"),
                       Pend("PENDIENTE (AU): el apartado 11 exige tratar el elemento como incorrección salvo que se apliquen "
                            "procedimientos alternativos adecuados. Documentar el procedimiento alternativo o registrar la "
                            "incorrección en ForSampling.")])
    for t in S.get("observaciones_ajenas") or []:
        filas7.append([lab("Observación ajena al muestreo"), t])
    tabla(doc, [5.5, 11.5], None, filas7)

    # ── 8 ──
    h1(doc, "8. Proyección y evaluación de resultados (apartados 14 y 15)")
    parrafo(doc, "ForSampling calcula la proyección del error al emitir su informe y no la guarda en ningún fichero: la "
                 "estimación del error, el punto estimado, los límites superior e inferior (IMS e IMI) y el texto de "
                 "conclusión existen solo en el informe emitido. Este papel no los recalcula ni los transcribe.")
    tabla(doc, [5.8, 11.2], None, [
        [lab("Proyección del error"), Pend("En el informe emitido por ForSampling, que se adjunta como anexo. No se recalcula aquí.")],
        [lab("Comparación con el error tolerable"), Pend("La hace ForSampling en su informe. Este papel no concluye si la prueba se supera.")],
    ])
    caja(doc, [("Dependencia del resultado. ", "b"),
               "ForSampling calcula con la evaluación registrada en el momento de emitir el informe. Si el auditor cambia la "
               "evaluación de algún elemento (apartado 7), hay que volver a emitir el informe antes de concluir."], AMBAR)
    h2(doc, "Conclusión del auditor (apartado 15)")
    parrafo(doc, "Evaluación de si los resultados de la muestra proporcionan una base razonable para alcanzar conclusiones "
                 "sobre la población, y de la necesidad de procedimientos adicionales:")
    caja(doc, [("PENDIENTE (AU): a redactar por el auditor. El asistente no concluye si la prueba se supera.", "i")], None, 2.8)

    # ── 9 ──
    h1(doc, "9. Información a solicitar cuando solo se dispone del fichero de ForSampling")
    parrafo(doc, "Lista de control. Con solo el .cli y los ficheros de la prueba, todo lo que no figure en FS se pide al auditor "
                 "con esta relación. La última columna recoge el estado en este encargo.")
    SOL = Pend("PENDIENTE: solicitar")

    def est(t):
        return Pend(t) if isinstance(t, str) and t.startswith("PENDIENTE") else t

    tabla(doc, [4.4, 3.2, 3.6, 5.8], ["Dato a solicitar", "Uso (NIA-ES)", "Dónde está en Gesia", "Estado en este encargo"], [
        ["Importancia relativa y criterio para fijar el error tolerable", "320 / 530 ap. 6", "Expediente · importancia relativa",
         est(f"IR_T {eur(ir['t'])} €; ET {eur(et)} €. Criterio y motivación: {'PENDIENTE' if nulo(P.get('motivacion')) else 'documentados'}") if ir else SOL],
        ["Fecha de cierre y periodo auditado", "530 ap. 6", "Datos del encargo", S.get("cierre") or SOL],
        ["Riesgo valorado del área y afirmación", "315 / 530 ap. 6", "Riesgos del expediente",
         "Disponible" if (S.get("riesgo_area") and S.get("afirmacion")) else (Pend("PENDIENTE: completar") if (S.get("riesgo_area") or S.get("afirmacion")) else SOL)],
        ["Saldo contable por cuenta de la población", "500 / 530 ap. 6", "Sumas y saldos",
         est(f"Disponible; desglose de la diferencia {'PENDIENTE' if nulo(S.get('conciliacion_detalle')) else 'documentado'}") if por_cuenta else SOL],
        ["Diario contable del ejercicio (.smn)", "500", "Diario importado", ("Disponible; " + str(di.get("texto"))) if di.get("ok") is True else SOL],
        ["Documentos de soporte de la muestra", "500 / 530 ap. 9", "Carpeta de documentación del área",
         f"{S['n_documentos']} documentos; {len(con_doc)} de {len(E)} elementos con soporte" if S.get("n_documentos") else SOL],
        ["Informe emitido por ForSampling (proyección y distribución), como anexo", "530 ap. 14 y 15", "No está en Gesia: lo emite ForSampling",
         Pend("PENDIENTE: adjuntar el informe emitido")],
        ["Programa de trabajo, responsable y revisor", "230", "Referencias y personal", Pend("PENDIENTE: firmas")],
        ["Decisión sobre elementos sin soporte", "530 ap. 10 y 11", "No consta",
         Pend(f"PENDIENTE: elemento{'s' if len(sin_doc) > 1 else ''} {', '.join(str(e['id']) for e in sin_doc)}") if sin_doc else "No aplica"],
        ["Conclusión sobre la muestra", "530 ap. 15", "No consta", Pend("PENDIENTE")],
    ])

    # ── 10 ──
    h1(doc, "10. Puntos abiertos y firmas")
    if fin.get("finalizada") is False:
        vineta(doc, "Prueba no finalizada en ForSampling: cerrarla cuando el auditor resuelva los puntos abiertos y redacte la conclusión.")
    if sin_doc:
        vineta(doc, f"Elemento{'s' if len(sin_doc) > 1 else ''} sin documento de soporte ({', '.join(str(e['id']) for e in sin_doc)}): "
                    "procedimiento alternativo o incorrección.")
    if nulo(P.get("motivacion")):
        vineta(doc, "Motivación del error tolerable, del nivel de confianza y de la afirmación cubierta.")
    if nulo(S.get("conciliacion_detalle")):
        vineta(doc, "Conciliación detallada de la diferencia entre la población y la contabilidad.")
    vineta(doc, "Adjuntar el informe emitido por ForSampling: la proyección del error y la distribución solo constan ahí.")
    if nulo(P.get("factor")) or nulo(P.get("metodo")):
        vineta(doc, "Factor de confianza o método sin descodificar en los ficheros de ForSampling.")
    tabla(doc, [8.5, 8.5], ["Preparado", "Revisado"],
          [["Nombre: ______________________\nFecha: ____ / ____ / ________\nFirma:",
            "Nombre: ______________________\nFecha: ____ / ____ / ________\nFirma:"]])

    # ── anexo ──
    h1(doc, "Anexo · Fuentes y trazabilidad")
    fuentes = [list(f) for f in (S.get("fuentes") or [])]
    fuentes.append(["NIA-ES 530", "Resolución del ICAC de 11/04/2024, aplicable a trabajos iniciados desde el 01/01/2025. "
                                  "Apartados 4 (objetivo), 5 (definiciones) y 6 a 15 (requerimientos)."])
    tabla(doc, [5.3, 11.7], ["Fuente", "Contenido utilizado"], fuentes)
    return doc


def comprobar(S: dict) -> list:
    """Lo que tiene que cuadrar antes de escribir. Devuelve la lista de fallos (vacia = bien)."""
    fallos = []
    E = S.get("elementos") or []
    tam = (S.get("p") or {}).get("tam") or {}
    unidades = sum(int(e.get("unidades") or 1) for e in E)
    if not nulo(tam.get("seleccionado")) and int(tam["seleccionado"]) != unidades:
        fallos.append(f"la suma de unidades de los elementos ({unidades}) no es el tamaño seleccionado ({tam['seleccionado']})")
    if not nulo(tam.get("unicos")) and int(tam["unicos"]) != len(E):
        fallos.append(f"hay {len(E)} elementos y el tamaño de únicos dice {tam['unicos']}")
    cu = S.get("cuadre") or {}
    if cu.get("ok") is False:
        fallos.append("el cuadre .smp ↔ .pcu está marcado como NO cuadrado: " + str(cu.get("texto")))
    # ningun nombre: el tercero de cada elemento tiene que ser un token o nada
    # `\b` despues del prefijo: sin el, «Proveedor Real, S.A.» pasaba por token porque empieza
    # por PROV. Un token es el prefijo, un espacio y el codigo, y nada mas.
    import re
    tok = re.compile(r"^(PROV|CLI|TER)\b\s*\S+$", re.I)
    for e in E:
        t = e.get("token")
        if t and not tok.match(str(t)):
            fallos.append(f"el elemento {e.get('id')} lleva un tercero que no es un token: no puede salir en el Word")
    return fallos


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--datos", required=True, help="nia530.json")
    ap.add_argument("--generado", required=True, help="fecha de generación, dd/mm/aaaa o aaaa-mm-dd")
    ap.add_argument("--salida", required=True)
    ap.add_argument("--forzar", action="store_true", help="escribe aunque las comprobaciones fallen (se anotan)")
    a = ap.parse_args()

    S = json.load(io.open(a.datos, encoding="utf-8-sig"))
    fallos = comprobar(S)
    if fallos and not a.forzar:
        print("❌ no se escribe el papel:")
        for f in fallos:
            print("   - " + f)
        return 2
    if os.path.exists(a.salida):
        print("❌ ya existe y no se pisa: " + a.salida)
        return 2
    doc = generar(S, a.generado)
    os.makedirs(os.path.dirname(os.path.abspath(a.salida)), exist_ok=True)
    doc.save(a.salida)
    E = S.get("elementos") or []
    pend = json.dumps(S, ensure_ascii=False).count("null")
    print(f"✔ papel escrito: {a.salida}")
    print(f"  modo: {S.get('modo', '—')} · elementos: {len(E)} · unidades: {sum(int(e.get('unidades') or 1) for e in E)}"
          " · la proyección no se recalcula: apartado 8 remite al informe emitido")
    print(f"  datos que faltan (null en el JSON): {pend}")
    if fallos:
        print("\nPARA CONTAR AL ENTREGAR (tal cual, sin resumir):")
        for f in fallos:
            print("  - " + f)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
