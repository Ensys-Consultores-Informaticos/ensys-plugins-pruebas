# -*- coding: utf-8 -*-
"""Comprueba que generar_cuadro.py escribe la pagina que tiene que escribir.

    python probar_cuadro.py

Con un expediente sintetico, sin Gesia ni servidor API: dos areas, tres cuentas de la cedula
con cinco ejercicios, dos riesgos y tres ratios. Mira:

  1. que la pagina sale, sin un solo recurso externo (se abre sin internet)
  2. que los datos van dentro y se leen de vuelta tal cual -importes, ejercicios, valoracion-
  3. que un nombre con «</script>» no rompe la pagina
  4. que el resumen marca la cuenta cuya variacion supera la IR de su area, y solo esa
  5. los casos degradados: cedula vacia, un solo ejercicio, IR sin calcular, fichero que falta
  6. que el SKILL.md pide los cinco ficheros que lee el script y borra con ruta literal

Codigos de salida: 0 todo bien, 1 algo ha fallado.
"""
from __future__ import annotations

import io
import json
import re
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

# La carpeta del script, explicita: lanzado con `python -I` no esta en sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import generar_cuadro as g  # noqa: E402

SKILL_MD = Path(__file__).resolve().parent.parent / "SKILL.md"
ANIOS = {"1": "2025", "2": "2024", "3": "2023", "4": "2022", "5": "2021"}

CONTEXTO = {
    "RazonSocialCliente": "EJEMPLO SINTETICO SL", "FechaCierre": "31/12/2025 0:00:00",
    "IR_P": "250000", "IR_T": "200000", "IR_I": "150000",
    "areas": [
        {"CodigoArea": "CO", "Area": "Compras y proveedores", "Total": "10", "Realizadas": "6", "Verificadas": "3"},
        {"CodigoArea": "TE", "Area": "Tesoreria", "Total": "4", "Realizadas": "4", "Verificadas": "4"},
    ],
}
IR_AREAS = [
    {"CodigoArea": "CO", "Area": "Compras y proveedores", "IR_Trabajo": "100000", "IR_Informe": "75000"},
    {"CodigoArea": "TE", "Area": "Tesoreria", "IR_Trabajo": "50000", "IR_Informe": "40000"},
]
RIESGOS = [
    {"IdRiesgo": "1", "CodigoArea": "CO", "Riesgo": "Corte de compras", "Significativo": "True", "AMRA": "False",
     "TipoRiesgo": "1", "Clasificacion": "I", "CodigoValorRIA_RI": "2", "CodigoValorRIA_RCI": "3",
     "CodigoValorRIA_RIM": "2", "Integridad": "True", "Existencia": "False", "Exactitud": "True",
     "Valoracion": "False", "CodigoReferencia": "CO)01"},
    {"IdRiesgo": "2", "CodigoArea": "TE", "Riesgo": "Cobros sin conciliar", "Significativo": "False", "AMRA": "True",
     "TipoRiesgo": "2", "Clasificacion": "R", "CodigoValorRIA_RI": "4", "CodigoValorRIA_RCI": "4",
     "CodigoValorRIA_RIM": "4", "Integridad": "False", "Existencia": "True", "Exactitud": "False",
     "Valoracion": "False", "CodigoReferencia": ""},
]
# 600: varia 150.000 contra una IR de area de 100.000 -> supera. 400: varia 20.000 -> no.
# 572: varia 60.000 contra 50.000 -> supera, y su nombre intenta cerrar el <script>.
SALDOS = {
    ("600", "Compras de mercaderias", "CO"): ["1150000,5", "1000000,5", "900000", "850000", "800000"],
    ("400", "Proveedores", "CO"): ["-220000", "-200000", "-180000", "-170000", ""],
    ("572", "Bancos </script><b>x</b>", "TE"): ["160000", "100000", "90000", "80000", "70000"],
    ("129", "Resultado sin area", ""): ["1", "2", "3", "4", "5"],
}
RATIOS = [
    {"CodigoElementoRA": "AE01", "Elemento": "Rotacion de proveedores", "Naturaleza": "Ratio", "Familia": "Actividad",
     "Relevancia": "Alta", "CodigoFaseRA": "P", "Descripcion": "Compras / proveedores",
     "ValorAño1": "0,1561", "ValorAño2": "0,15", "ValorAño3": "0,14", "ValorAño4": "", "ValorAño5": ""},
    {"CodigoElementoRA": "AE02", "Elemento": "Sin datos", "Naturaleza": "Ratio", "Familia": "Actividad",
     "Relevancia": "Baja", "CodigoFaseRA": "P", "Descripcion": "",
     "ValorAño1": "", "ValorAño2": "", "ValorAño3": "", "ValorAño4": "", "ValorAño5": ""},
    {"CodigoElementoRA": "M01", "Elemento": "Ventas", "Naturaleza": "Magnitud", "Familia": "Resultados",
     "Relevancia": "Media", "CodigoFaseRA": "F", "Descripcion": "",
     "ValorAño1": "1000", "ValorAño2": "900", "ValorAño3": "", "ValorAño4": "", "ValorAño5": ""},
]


def cedula(ejercicios: int = 5) -> list[dict]:
    filas = []
    for (cta, nombre, area), saldos in SALDOS.items():
        for i, s in enumerate(saldos[:ejercicios], start=1):
            filas.append({"Cuenta": cta, "Nombre": nombre, "CodigoAreaCP": area, "Año": ANIOS[str(i)],
                          "CodigoAuditoria": str(i), "SaldoAuditoria": s})
    return filas


def escribir_fixture(carpeta: Path, **cambios) -> None:
    datos = {"contexto": CONTEXTO, "ir_areas": IR_AREAS, "riesgos": RIESGOS, "cedula": cedula(), "ratios": RATIOS}
    datos.update(cambios)
    for nombre, contenido in datos.items():
        if contenido is not None:
            (carpeta / f"{nombre}.json").write_text(json.dumps(contenido, ensure_ascii=False), encoding="utf-8")


def generar(carpeta: Path) -> tuple[int, str, Path]:
    salida = carpeta / "Cuadro de mando PRUEBA 2025.html"
    buf = io.StringIO()
    with redirect_stdout(buf):
        codigo = g.main(["--datos", str(carpeta), "--generado", "2026-10-22", "--salida", str(salida)])
    return codigo, buf.getvalue(), salida


def datos_de(html: str) -> dict:
    m = re.search(r'<script id="datos" type="application/json">(.*?)</script>', html, re.S)
    if not m:
        raise AssertionError("no encuentro los datos en la pagina")
    return json.loads(m.group(1).replace("<\\/", "</"))


FALLOS: list[str] = []


def comprobar(cond: bool, que: str) -> None:
    print(("  ok   " if cond else "  MAL  ") + que)
    if not cond:
        FALLOS.append(que)


def main() -> int:
    g._salida_utf8()
    with tempfile.TemporaryDirectory(prefix="cuadro-prueba-") as tmp:
        base = Path(tmp)

        print("1-4 · el caso completo")
        c = base / "completo"; c.mkdir()
        escribir_fixture(c)
        codigo, texto, salida = generar(c)
        comprobar(codigo == 0 and salida.exists(), "sale la pagina (salida 0)")
        html = salida.read_text(encoding="utf-8")
        externos = re.findall(r"""(?:src|href)\s*=\s*["']?(?:https?:)?//""", html, re.I)
        comprobar(not externos and "@import" not in html, "sin recursos externos")
        comprobar(html.count("</script>") == len(re.findall(r"<script[ >]", html)) and "</script><b>" not in html,
                  "el nombre con </script> va escapado")
        D = datos_de(html)
        comprobar(D["cliente"] == "EJEMPLO SINTETICO SL" and D["cierre"] == "31/12/2025", "cliente y cierre")
        comprobar(D["ejercicios"] == ["2025", "2024", "2023", "2022", "2021"], "los cinco ejercicios, del mas reciente")
        c600 = next(x for x in D["cedula"] if x["cuenta"] == "600")
        comprobar(c600["saldos"][0] == 1150000.5 and c600["saldos"][1] == 1000000.5, "importes con coma decimal")
        c400 = next(x for x in D["cedula"] if x["cuenta"] == "400")
        comprobar(c400["saldos"][4] is None, "un saldo vacio es None, no cero")
        comprobar(all(x["cuenta"] != "129" for x in D["cedula"]), "la cuenta sin area no sale")
        r1 = next(r for r in D["riesgos"] if r["riesgo"] == "Corte de compras")
        comprobar(r1["rim"] == "Alto" and r1["significativo"] and r1["afirmaciones"] == ["Integridad", "Exactitud"],
                  "valoracion al reves (2 = Alto) y afirmaciones")
        comprobar(D["ir_areas"]["CO"]["trabajo"] == 100000.0 and D["ir"]["T"] == 200000.0, "IR global y por area")
        comprobar(next(r for r in D["ratios"] if r["codigo"] == "AE01")["valores"][0] == 0.1561, "valor de ratio")
        comprobar("1 cuenta(s) de la cedula principal sin area" in texto, "avisa de la cuenta sin area")
        superan = re.search(r"supera la IR de su area: (\d+)", texto)
        comprobar(superan is not None and superan.group(1) == "2" and "CO · 600" in texto and "TE · 572" in texto
                  and "CO · 400" not in texto, "marca 600 y 572 (superan la IR del area) y no 400")

        print("5 · casos degradados")
        d = base / "sin_cedula"; d.mkdir()
        escribir_fixture(d, cedula=[])
        codigo, texto, salida = generar(d)
        comprobar(codigo == 0 and "no trae ejercicios" in texto, "cedula vacia: sale, y avisa")
        d = base / "un_ejercicio"; d.mkdir()
        escribir_fixture(d, cedula=cedula(1))
        codigo, texto, salida = generar(d)
        comprobar(codigo == 0 and "supera la IR de su area: 0" in texto, "un solo ejercicio: sale, sin variaciones")
        d = base / "sin_ir"; d.mkdir()
        escribir_fixture(d, contexto=dict(CONTEXTO, IR_T="", IR_P="", IR_I=""))
        codigo, texto, salida = generar(d)
        comprobar(codigo == 0 and "IR de trabajo viene a cero o vacia" in texto, "IR sin calcular: sale, y avisa")
        d = base / "falta"; d.mkdir()
        escribir_fixture(d, riesgos=None)
        codigo, texto, salida = generar(d)
        comprobar(codigo == 2 and "falta riesgos.json" in texto and not salida.exists(),
                  "falta un fichero: salida 2 y no escribe nada")
        with redirect_stdout(io.StringIO()):
            codigo = g.main(["--datos", str(d), "--generado", "22/10/2026", "--salida", str(d / "x.html")])
        comprobar(codigo == 2, "fecha de generacion mal escrita: salida 2")

        print("6 · el SKILL.md")
        skill = SKILL_MD.read_text(encoding="utf-8")
        comprobar(all(f"{n}.json" in skill for n in g.FICHEROS), "pide los cinco ficheros que lee el script")
        comprobar('configurar(perfil = "cuadro-mando")' in skill
                  and 'limpiar_exportaciones(procedimiento = "cuadro-mando")' in skill, "perfil y limpieza")
        comprobar('rm -rf "$TRABAJO"' not in skill and "rm -rf \"<" in skill, "borra el directorio con ruta literal")
        comprobar("sellar_uso_ia" not in skill, "sin bloque de uso de IA (decidido el 22/10/2026)")

    print()
    if FALLOS:
        print(f"FALLAN {len(FALLOS)}:")
        for f in FALLOS:
            print("   - " + f)
        return 1
    print("Todo bien.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
