"""Comprueba en ejecucion lo que el skill da por supuesto. Puede abortar.

Codigos de salida:
  0  todo encaja
  1  hay avisos, se puede seguir
  2  ABORTA. No se genera nada.

Lo que se asume se comprueba: la semantica de los campos de Gesia no coincide
con lo documentado en mas de un expediente. Un .xlsx impecable construido sobre
datos mal entendidos es peor que no tener .xlsx, porque se importa al expediente
y nadie lo vuelve a mirar.

    python verificar_contrato.py --cuestionario trabajo/cuestionario.json \n        --guia "<el codigo del cuestionario, que NO es fijo entre encargos>"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from lib_cuestionario import (
    RESPUESTAS,
    es_cabecera,
    huecos_de_orden,
    leer_cuestionario,
    salida_utf8,
)

MAX_LISTA = 10


class Informe:
    def __init__(self) -> None:
        self.lineas: list[tuple[str, str, str]] = []
        self.aborta = False
        self.avisos = 0

    def ok(self, codigo: str, texto: str) -> None:
        self.lineas.append(("OK", codigo, texto))

    def aviso(self, codigo: str, texto: str) -> None:
        self.lineas.append(("AVISO", codigo, texto))
        self.avisos += 1

    def error(self, codigo: str, texto: str) -> None:
        self.lineas.append(("ABORTA", codigo, texto))
        self.aborta = True

    def imprimir(self) -> int:
        for nivel, codigo, texto in self.lineas:
            print(f"{nivel:<7} {codigo}  {texto}")
        if self.aborta:
            print("\nCONTRATO NO VERIFICADO. No se genera nada.")
            return 2
        print(f"\nContrato verificado. {self.avisos} aviso(s).")
        return 1 if self.avisos else 0


def entero(bruto) -> int | None:
    texto = str(bruto if bruto is not None else "").strip()
    try:
        return int(texto)
    except ValueError:
        return None


def main() -> int:
    salida_utf8()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cuestionario", required=True,
                   help="el JSON que dejo exportar_consulta")
    p.add_argument("--guia", required=True)
    args = p.parse_args()

    inf = Informe()

    # C01 — el JSON es del cuestionario pedido.
    # Que la referencia exista, sea CCC y este Disponible lo comprueba el modelo
    # en el paso 2 del SKILL.md con consultar_gesia: es el unico que puede hablar
    # con el expediente. Aqui solo se valida lo que ha llegado.
    try:
        datos = leer_cuestionario(args.cuestionario)
    except (OSError, ValueError) as exc:
        print("C01 ERROR: no se puede leer el cuestionario: " + str(exc))
        return 2
    if datos.get("guia") != args.guia:
        inf.error("C01", "el JSON dice que es de " + repr(datos.get("guia"))
                  + " y se ha pedido " + repr(args.guia))
        return inf.imprimir()
    inf.ok("C01", args.guia + ": JSON con " + str(datos.get("n_filas", "?")) + " filas")

    # C02 — tiene contenido.
    filas = datos["filas"]
    if not filas:
        inf.error("C02", "Cero filas en DetalleGuias. Si es un nodo del indice "
                         "(como 'AG)20'), el contenido cuelga de sus hijos")
        return inf.imprimir()
    inf.ok("C02", f"{len(filas)} filas en DetalleGuias")


    # C03 — todas del mismo cuestionario.
    ajenas = {f["CodigoGuia"] for f in filas} - {args.guia}
    if ajenas:
        inf.error("C03", f"Hay filas de otros cuestionarios: {sorted(ajenas)[:5]}")
    else:
        inf.ok("C03", "Todas las filas son del cuestionario pedido")

    # C04 — CodigoOrden entero, unico y contiguo desde 1.
    ordenes = [entero(f["CodigoOrden"]) for f in filas]
    if any(o is None for o in ordenes):
        inf.error("C04", "Hay CodigoOrden no numericos")
    elif len(set(ordenes)) != len(ordenes):
        inf.error("C04", "Hay CodigoOrden repetidos: no sirve como clave de respuesta")
    elif sorted(ordenes) != list(range(1, len(ordenes) + 1)):
        # Un hueco puede ser del propio master -una pregunta retirada- o puede
        # ser que el cuestionario haya llegado incompleto, y eso NO se nota
        # leyendolo: uno al que le faltan doce preguntas se rellena igual de bien
        # y el papel sale con la misma pinta. Queda en aviso porque las dos
        # causas son posibles, pero con los huecos delante para poder mirarlos.
        faltan = huecos_de_orden(filas)
        inf.aviso("C04", f"CodigoOrden no es contiguo 1..{len(ordenes)}: faltan "
                  + str(len(faltan)) + " (" + str(faltan[:12])
                  + (" ..." if len(faltan) > 12 else "") + "). El export de "
                  "Gesia si era contiguo, asi que puede ser que el cuestionario "
                  "haya llegado incompleto: compara el recuento con el que dio "
                  "exportar_consulta antes de seguir.")
    else:
        inf.ok("C04", f"CodigoOrden contiguo 1..{len(ordenes)} y unico")

    # C05 — Punto entero en todas.
    if any(entero(f["Punto"]) is None for f in filas):
        inf.error("C05", "Hay filas sin Punto numerico: no se pueden agrupar en secciones")
    else:
        inf.ok("C05", f"Punto numerico en las {len(filas)} filas")

    # C06 — una cabecera por seccion.
    cabeceras = [f for f in filas if es_cabecera(f)]
    preguntas = [f for f in filas if not es_cabecera(f)]
    puntos = {str(f["Punto"]) for f in filas}
    por_punto: dict[str, int] = {}
    for f in cabeceras:
        por_punto[str(f["Punto"])] = por_punto.get(str(f["Punto"]), 0) + 1
    sin_cabecera = sorted(puntos - set(por_punto), key=lambda x: int(x))
    repetidas = sorted(k for k, v in por_punto.items() if v > 1)
    if sin_cabecera:
        inf.aviso("C06", f"Secciones sin titulo: {sin_cabecera[:MAX_LISTA]}")
    if repetidas:
        inf.aviso("C06", f"Secciones con mas de una cabecera: {repetidas[:MAX_LISTA]}")
    if not sin_cabecera and not repetidas:
        inf.ok("C06", f"{len(cabeceras)} cabeceras para {len(puntos)} secciones, una cada una")

    # C07 — las cabeceras no llevan respuesta.
    contestadas_cabecera = [f["CodigoOrden"] for f in cabeceras
                            if str(f.get("Respuesta", "")).strip()]
    if contestadas_cabecera:
        inf.aviso("C07", f"{len(contestadas_cabecera)} cabeceras traen Respuesta. "
                         "El skill las deja vacias igualmente")
    else:
        inf.ok("C07", "Ninguna cabecera trae respuesta, como en el export")

    # C08 — dominio de Respuesta.
    fuera = sorted({str(f["Respuesta"]).strip() for f in filas
                    if str(f.get("Respuesta", "")).strip()
                    and entero(f["Respuesta"]) not in RESPUESTAS})
    if fuera:
        inf.error("C08", f"Respuesta con valores fuera de 1-4: {fuera[:MAX_LISTA]}. "
                         "El codigo de respuestas no es el que se creia")
    else:
        inf.ok("C08", "Respuesta solo toma vacio o 1-4")

    # C09 — las preguntas tienen DesglosePunto numerico.
    malas = [f["CodigoOrden"] for f in preguntas if entero(f["DesglosePunto"]) is None]
    if malas:
        inf.error("C09", f"{len(malas)} preguntas con DesglosePunto no numerico: "
                         f"{malas[:MAX_LISTA]}")
    else:
        inf.ok("C09", f"{len(preguntas)} preguntas, todas con DesglosePunto numerico")

    # C10 — Prioritaria booleana.
    valores = {str(f.get("Prioritaria", "")).strip() for f in filas}
    if valores - {"True", "False", ""}:
        inf.aviso("C10", f"Prioritaria toma valores raros: {sorted(valores)[:MAX_LISTA]}")
    else:
        inf.ok("C10", "Prioritaria es booleana")

    # C11 estaba aqui: lanzaba dos consultas al API para ver si
    # CodigoRealizado se compara como numero o como cadena. Se quito el
    # 23/08/2026, al dejar de hablar con el API. El contrato de tipos esta medido
    # en docs/trampas-jet.md y, si hay que comprobarlo, son dos consultar_gesia
    # que hace el modelo, no este script.

    # C12 — estado de partida.
    ya = [f for f in preguntas if str(f.get("Respuesta", "")).strip()]
    if ya:
        inf.aviso("C12", f"{len(ya)} de {len(preguntas)} preguntas YA estan contestadas. "
                         "Hay que preguntarle al usuario antes de sobrescribir")
    else:
        inf.ok("C12", f"Cuestionario en blanco: {len(preguntas)} preguntas por responder")

    return inf.imprimir()


if __name__ == "__main__":
    sys.exit(main())
