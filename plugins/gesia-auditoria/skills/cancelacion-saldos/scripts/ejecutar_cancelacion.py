"""Verifica el contrato y, si se puede seguir, escribe el papel de trabajo.

    python ejecutar_cancelacion.py --entrada extracto.csv \
        --salida "<expediente>/AsistenteIA/CancelacionSaldos/Cancelacion Saldos <CLIENTE>.xlsx"

Es exactamente lo que hacian los dos pasos de antes, en una sola llamada:

    verificar_contrato.py --entrada X
    generar_papel.py      --entrada X --salida Y

Por que existe: cada llamada obliga al modelo a un turno mas, y un turno
cuesta la superficie entera del MCP -medida el 30/08/2026 en ~12.500 tokens-,
que es mucho mas que las 163 fichas que ocupa la salida del verificador. El
ahorro no esta en escribir menos, esta en volver menos veces.

No reimplementa nada: importa los dos scripts y llama a su main(), asi que si
manana cambia una comprobacion o un color, cambia aqui tambien sin tocar este
fichero. Y los originales siguen valiendo por separado, que es lo que quiere
quien esta depurando uno de los dos.

La semantica del verificador se conserva entera:

  0  todo encaja, y el papel se ha escrito
  1  hay avisos: el papel se ha escrito y los avisos TIENEN QUE CONSTAR en el
     TODO lo que imprime el verificador sigue saliendo, no se resume
  2  no se puede hacer la prueba: no se escribe nada
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generar_papel  # noqa: E402
import verificar_contrato  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--entrada", required=True,
                    help="fichero exportado con exportar_consulta (.csv o .json)")
    p.add_argument("--salida", required=True,
                    help="ruta del .xlsx en la carpeta del expediente")
    args = p.parse_args()

    # Los dos scripts leen sus propios argumentos de sys.argv. Se los damos
    # armados en vez de reescribir su main(): asi no hay dos sitios donde
    # cambiar una opcion.
    sys.argv = ["verificar_contrato.py", "--entrada", args.entrada]
    codigo = verificar_contrato.main()

    if codigo == 2:
        print("\nNo se genera el papel: el contrato no se cumple.")
        return 2

    print("")
    sys.argv = ["generar_papel.py", "--entrada", args.entrada, "--salida", args.salida]
    if generar_papel.main() != 0:
        return 2

    # Si el verificador dio avisos, el codigo de salida los sigue anunciando
    # aunque el papel se haya escrito: se leen y se cuentan al entregar.
    return codigo


if __name__ == "__main__":
    sys.exit(main())
