# -*- coding: utf-8 -*-
"""Valida el dígito de control de un identificador fiscal español.

Distingue CIF de persona jurídica, DNI y NIE, y valida el control de los tres.
La investigación de entidades solo aplica a personas jurídicas (CIF): el skill
usa el campo `tipo` para pararse si le llega un identificador de persona física.

Con un CIF válido devuelve además la `forma` de la entidad y el `registro` donde buscarla,
por su letra inicial, y `borme_aplica` solo para las mercantiles.

Salida: un JSON por stdout. Código de salida 0 si el control es válido,
2 si no lo es o el formato no se reconoce (el skill PARA: investigar un CIF
mal tecleado produce un informe sobre otra entidad).
"""

import argparse
import json
import re
import sys

# Letras iniciales admitidas en un CIF de persona jurídica (RD 1065/2007).
LETRAS_CIF = "ABCDEFGHJNPQRSUVW"

# El control es LETRA para organismos públicos y entidades sin forma mercantil,
# y DÍGITO para las formas societarias clásicas. Para el resto valen los dos.
CONTROL_SOLO_LETRA = "PQRSNW"
CONTROL_SOLO_DIGITO = "ABEH"

# Tabla oficial: el dígito de control 0..9 se corresponde con esta letra.
LETRAS_CONTROL_CIF = "JABCDEFGHI"

# Tabla oficial del DNI/NIE: letra = número % 23.
LETRAS_DNI = "TRWAGMYFPDXBNJZSQVHLCKE"

# La letra inicial dice la FORMA de la entidad (Orden EHA/451/2008), y con ella el registro
# donde buscarla. El BORME solo vale para las mercantiles: el 05/10/2026 se investigo una
# fundacion (G) y el investigador tuvo que descubrir solo que su registro era el de
# Fundaciones del Pais Vasco, mientras el informe seguia citando el BORME en la cabecera.
FORMAS = {
    "A": ("sociedad anónima", "Registro Mercantil (BORME)", True),
    "B": ("sociedad de responsabilidad limitada", "Registro Mercantil (BORME)", True),
    "C": ("sociedad colectiva", "Registro Mercantil (BORME)", True),
    "D": ("sociedad comanditaria", "Registro Mercantil (BORME)", True),
    "E": ("comunidad de bienes, herencia yacente u otra entidad sin personalidad jurídica",
          "sin registro mercantil", False),
    "F": ("sociedad cooperativa", "Registro de Cooperativas, estatal o autonómico", False),
    "G": ("asociación o fundación", "Registro de Fundaciones o de Asociaciones, estatal o autonómico", False),
    "H": ("comunidad de propietarios", "sin registro público de la entidad", False),
    "J": ("sociedad civil", "sin registro mercantil, salvo que se haya inscrito", False),
    "N": ("entidad extranjera", "registro de su país de origen", False),
    "P": ("corporación local", "boletines oficiales y portal de transparencia", False),
    "Q": ("organismo público", "boletines oficiales y portal de transparencia", False),
    "R": ("congregación o institución religiosa", "Registro de Entidades Religiosas", False),
    "S": ("órgano de la Administración del Estado o de una comunidad autónoma",
          "boletines oficiales", False),
    "U": ("unión temporal de empresas", "registro especial de UTE; sus socios, en el Registro Mercantil", False),
    "V": ("otro tipo de entidad", "a determinar según la entidad", False),
    "W": ("establecimiento permanente de entidad no residente", "Registro Mercantil (BORME), como sucursal", True),
}


def normalizar(texto):
    """Quita espacios, guiones y puntos y pasa a mayúsculas."""
    return re.sub(r"[\s\-.]", "", texto or "").upper()


def _control_cif(siete_digitos):
    """Calcula el dígito de control de un CIF a partir de sus 7 dígitos."""
    suma = 0
    for i, caracter in enumerate(siete_digitos):
        digito = int(caracter)
        if i % 2 == 0:  # posiciones impares 1,3,5,7 (índice 0,2,4,6): se duplican
            doble = digito * 2
            suma += doble - 9 if doble > 9 else doble
        else:  # posiciones pares 2,4,6: se suman tal cual
            suma += digito
    return (10 - suma % 10) % 10


def validar(identificador):
    """Devuelve (tipo, valido, motivo) para un identificador ya normalizado."""
    if re.fullmatch(r"[0-9]{8}[A-Z]", identificador):
        numero, letra = int(identificador[:8]), identificador[8]
        ok = LETRAS_DNI[numero % 23] == letra
        return "dni", ok, None if ok else "la letra de control no corresponde"

    if re.fullmatch(r"[XYZ][0-9]{7}[A-Z]", identificador):
        # El prefijo del NIE se sustituye por su dígito antes del módulo 23.
        numero = int(str("XYZ".index(identificador[0])) + identificador[1:8])
        ok = LETRAS_DNI[numero % 23] == identificador[8]
        return "nie", ok, None if ok else "la letra de control no corresponde"

    if re.fullmatch(r"[A-Z][0-9]{7}[0-9A-J]", identificador):
        inicial, digitos, control = identificador[0], identificador[1:8], identificador[8]
        if inicial not in LETRAS_CIF:
            return "cif", False, "la letra inicial %s no es de un CIF válido" % inicial
        esperado = _control_cif(digitos)
        letra_esperada = LETRAS_CONTROL_CIF[esperado]
        if inicial in CONTROL_SOLO_LETRA:
            ok = control == letra_esperada
        elif inicial in CONTROL_SOLO_DIGITO:
            ok = control == str(esperado)
        else:
            ok = control in (str(esperado), letra_esperada)
        return "cif", ok, None if ok else "el carácter de control no corresponde"

    return "desconocido", False, "el formato no es CIF, DNI ni NIE"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cif", required=True, help="identificador a validar")
    argumentos = parser.parse_args()

    identificador = normalizar(argumentos.cif)
    tipo, valido, motivo = validar(identificador)
    forma, registro, mercantil = (FORMAS.get(identificador[:1], (None, None, False))
                                  if tipo == "cif" and valido else (None, None, False))
    print(json.dumps({
        "identificador": identificador,
        "tipo": tipo,
        "valido": valido,
        "motivo": motivo,
        "es_persona_juridica": tipo == "cif" and valido,
        "forma": forma,
        "registro": registro,
        "borme_aplica": mercantil,
    }, ensure_ascii=False, allow_nan=False))
    return 0 if valido else 2


if __name__ == "__main__":
    sys.exit(main())
