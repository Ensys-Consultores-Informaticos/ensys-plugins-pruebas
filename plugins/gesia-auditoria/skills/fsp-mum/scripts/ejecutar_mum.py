"""Verifica el contrato y, si se puede seguir, escribe el papel de trabajo.

    python ejecutar_mum.py --muestra muestra.json --parametros parametros.json \
        --facturas facturas.json [--evaluacion evaluacion.json] \
        --salida "<expediente>/AsistenteIA/FspMum/MUM <PRUEBA> <CLIENTE> <EJERCICIO>.xlsx" \
        --generado 2026-09-03

Es lo que hacen los dos scripts de debajo, en una sola llamada:

    verificar_contrato.py --muestra X --parametros P --facturas F [--evaluacion E]
    generar_papel.py      --muestra X --parametros P --facturas F [--evaluacion E] --salida Y --generado D
                          [--manifiesto M] [--carpeta-documentos C]

Por que existe: cada llamada obliga al modelo a un turno mas, y un turno cuesta la
superficie entera del MCP. El ahorro no esta en escribir menos, esta en volver menos
veces. No reimplementa nada: importa los dos scripts y llama a su main().

Codigos de salida, los del verificador:

  0  todo encaja, y el papel se ha escrito
  1  hay avisos: el papel se ha escrito y los avisos TIENEN QUE CONSTAR al entregar
  2  no se puede hacer la prueba: no se escribe nada
"""
from __future__ import annotations

import argparse
import contextlib
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generar_papel  # noqa: E402
import verificar_contrato  # noqa: E402


def _capturar(fn) -> tuple[int, str]:
    """Ejecuta un main() capturando lo que imprime, y lo reimprime tal cual."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        codigo = fn()
    texto = buf.getvalue()
    print(texto, end="")
    return codigo, texto


def _para_el_usuario(verif: str, papel: str) -> None:
    """Lo que hay que contar al entregar, ya recogido, para que no se pierda al parafrasear.

    En el primer uso real los avisos del contrato se imprimieron y no llegaron
    citados al usuario: el paso de entrega del SKILL.md los pide, pero quedaban
    treinta lineas mas arriba. Aqui se recogen los avisos, los elementos con
    hallazgo o diferencia, los documentos sueltos y la comparacion con el
    auditor, en un bloque final que se copia sin reescribir.
    """
    lineas = []
    for l in verif.splitlines():
        t = l.strip()
        if t.startswith("A0") or t.startswith("[A]") or (t.startswith("C0") and "ERROR" in t):
            lineas.append("  " + t)
    claves = ("·", "frente al auditor", "incorrecciones", "NO son la proyección",
              "esta población contabiliza", "sin diferencia", "elementos ")
    for l in papel.splitlines():
        t = l.strip()
        if t.startswith(claves):
            lineas.append("  " + t)
    print()
    print("=== PARA CONTAR AL ENTREGAR (tal cual, sin resumir) ===")
    if lineas:
        for l in lineas:
            print(l)
    else:
        print("  sin avisos ni hallazgos")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--muestra", required=True)
    p.add_argument("--parametros", required=True)
    p.add_argument("--facturas", required=True)
    p.add_argument("--evaluacion")
    p.add_argument("--salida", required=True)
    p.add_argument("--generado", required=True)
    p.add_argument("--manifiesto")
    p.add_argument("--carpeta-documentos", dest="carpeta_documentos")
    args = p.parse_args()

    comunes = ["--muestra", args.muestra, "--parametros", args.parametros, "--facturas", args.facturas]
    if args.evaluacion:
        comunes += ["--evaluacion", args.evaluacion]

    sys.argv = ["verificar_contrato.py"] + comunes
    codigo, salida_verif = _capturar(verificar_contrato.main)
    if codigo == 2:
        print("\nNo se genera el papel: el contrato no se cumple.")
        return 2

    print("")
    # los dos del hipervinculo van SOLO al papel: verificar_contrato no los conoce
    del_papel = ["--salida", args.salida, "--generado", args.generado]
    if args.manifiesto:
        del_papel += ["--manifiesto", args.manifiesto]
    if args.carpeta_documentos:
        del_papel += ["--carpeta-documentos", args.carpeta_documentos]
    sys.argv = ["generar_papel.py"] + comunes + del_papel
    codigo_papel, salida_papel = _capturar(generar_papel.main)
    if codigo_papel != 0:
        return 2
    _para_el_usuario(salida_verif, salida_papel)
    return codigo


if __name__ == "__main__":
    sys.exit(main())
