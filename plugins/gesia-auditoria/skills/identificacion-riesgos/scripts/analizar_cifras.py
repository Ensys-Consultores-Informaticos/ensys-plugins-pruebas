"""Calcula los hechos cuantitativos del balance y la cuenta de resultados.

    python analizar_cifras.py --balance b.json --pyg p.json [--ratios r.json] \
        --ejercicios 2025,2024,2023,2022,2021 --salida analisis.json

Recibe lo que devuelve `consultar_gesia` sobre `EstructuraBalance` y
`EstructuraPyG` —las dos traen `SaldoAuditoria1..5`, o sea los cinco ejercicios—
y saca los umbrales disparados, con su epigrafe y su importe.

Lo que este script NO hace: decidir que riesgo corresponde a cada hallazgo. Eso
es criterio de auditoria y lo aplica el modelo eligiendo del catalogo, porque no
existe ningun mapa epigrafe -> area del catalogo y inventarlo aqui seria
disfrazar de calculo una decision profesional.

La jerarquia del balance es Clase > Seccion > Epigrafe > Desglose. Un nivel se
reconoce por que codigos vienen vacios, y los niveles superiores ya traen el
total de lo que agrupan, asi que no hay que sumar hojas.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from lib_riesgos import (
    CONCENTRACION,
    EJERCICIOS,
    EJERCICIOS_PERDIDAS,
    UMBRAL_VACIO,
    VARIACION,
    es_esal,
    numero,
    proporcion_ceros,
    con_resumen,
    ruta_resumen,
    salida_utf8,
    comparar,
    convertir_signo,
    viene_convertido,
    serie,
    variacion,
)

MAX_LISTA = 20

# El epigrafe de resultado se reconoce por su concepto. Entra SIEMPRE en el
# analisis, tenga el importe que tenga: es el que resume el ejercicio, y un
# resultado casi nulo es en si mismo informativo.
CLAVES_RESULTADO = ("resultado del ejercicio", "excedente del ejercicio",
                    "resultado del periodo")


def es_resultado(texto_concepto: str) -> bool:
    c = (texto_concepto or "").lower()
    return any(k in c for k in CLAVES_RESULTADO)


def leer(ruta) -> list:
    datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    if isinstance(datos, dict):
        for clave in ("filas", "rows", "resultado", "data"):
            if isinstance(datos.get(clave), list):
                return datos[clave]
        raise RuntimeError(str(ruta) + ": objeto sin lista de filas dentro")
    return datos


# Nivel 0: fila de encabezado, sin cifra propia. Ver nivel().
ENCABEZADO = 0


def nivel(f: dict) -> int:
    """0 encabezado, 1 seccion, 2 epigrafe, 3 desglose.

    En la PyG, `CodigoEpigrafe = "0"` NO es un epigrafe: es la cabecera de una
    de las dos grandes secciones del modelo del PGC -«A) OPERACIONES
    CONTINUADAS» y «B) OPERACIONES INTERRUMPIDAS»- y arrastra el resultado
    total, no una cifra suya. Medido en un expediente real: las dos filas de
    encabezado valian -492.656,53, exactamente el resultado del ejercicio, y
    una de ellas se colo en el informe como si «OPERACIONES INTERRUMPIDAS»
    hubiera movido medio millon de euros en una empresa que no tiene ninguna.

    El balance no tiene este caso: alli las secciones llevan el epigrafe vacio.
    """
    epi = str(f.get("CodigoEpigrafe", "") or "").strip()
    des = str(f.get("CodigoDesglose", "") or "").strip()
    if epi == "0":
        return ENCABEZADO
    if not epi and not des:
        return 1
    if epi and not des:
        return 2
    # El subdesglose es un nivel MAS, y distinguirlo importa: sin esto «Reservas»,
    # «Legal y estatutarias» y «Otras reservas» eran las tres nivel 3 y ademas
    # compartian etiqueta, o sea tres filas distintas con el mismo codigo en el
    # papel. Medido en un expediente real.
    if str(f.get("CodigoSubDesglose", "") or "").strip():
        return 4
    return 3


def concepto(f: dict) -> str:
    """El nombre del epigrafe. En la PyG, SIEMPRE `ConceptoIngresos`.

    Cada fila de la PyG trae dos denominaciones, y de ahi salio la tentacion de
    elegir una segun el signo del saldo -la fila del resultado es «RESULTADO DEL
    EJERCICIO (A.4+19)» en ConceptoIngresos y «BENEFICIOS ANTES DE IMPUESTOS» en
    ConceptoGastos-. Pero la consulta con la que Gesia hace la revision analitica
    usa `ConceptoIngresos AS Concepto` y punto, sin condicional. Manda eso.

    Elegir por el signo tenia dos consecuencias malas, las dos vistas en
    ejecucion: en una empresa con beneficio el resultado aparecia titulado
    «BENEFICIOS ANTES DE IMPUESTOS», y como ese texto no contiene la palabra
    resultado, la funcion que localiza la fila del resultado dejaba de
    encontrarla y la serie de los cinco ejercicios desaparecia del informe.

    ConceptoGastos solo se usa si el otro viene vacio, que no se ha visto pasar.
    """
    directo = str(f.get("Concepto", "") or "").strip()
    if directo:
        return directo                      # el balance solo tiene uno
    ingresos = str(f.get("ConceptoIngresos", "") or "").strip()
    return ingresos or str(f.get("ConceptoGastos", "") or "").strip()


def etiqueta(f: dict) -> str:
    # CodigoSubDesglose entra en la etiqueta: sin el, «Reservas» y «Otras
    # reservas» salian las dos como «P.A.1.3». Dos filas con el mismo codigo en un
    # papel de trabajo no se pueden puntear.
    partes = [str(f.get(k, "") or "").strip()
              for k in ("CodigoClase", "CodigoSeccion", "CodigoEpigrafe",
                        "CodigoDesglose", "CodigoSubDesglose")]
    return ".".join(p for p in partes if p)


# Prioridad entre filas que repiten el mismo importe. T total, ST subtotal,
# I epigrafe. Lo demas, lo ultimo.
RANGO_CLASE = {"T": 3, "ST": 2, "I": 1}


def _rango(v: dict) -> tuple:
    """Cuanto de agregada es una fila. Mas alto gana en el deduplicado."""
    partes = str(v.get("epigrafe", "")).split(".")
    clase = partes[0] if partes else ""
    seccion = 0
    if len(partes) > 1 and partes[1].isdigit():
        seccion = int(partes[1])
    return (RANGO_CLASE.get(clase, 0), seccion)


def clase_de(f: dict) -> str:
    return str(f.get("CodigoClase", "") or "").strip()


def serie_presentada(f: dict) -> list:
    """La serie con el signo que Gesia le da al presentarla.

    Si la fila ya viene de `cifras_pyg`, el signo esta puesto y NO se vuelve a
    tocar: convertir dos veces deja los beneficios del reves otra vez.
    """
    if viene_convertido(f):
        return serie(f)
    clase = clase_de(f)
    return [convertir_signo(v, clase) for v in serie(f)]


CIFRA_DE_NEGOCIOS = "importe neto de la cifra de negocios"


def es_cifra_de_negocios(f: dict) -> bool:
    return concepto(f).strip().lower().startswith(CIFRA_DE_NEGOCIOS)


def analizar(filas: list, ejercicios: list, que: str, ir_t: float = 0.0) -> dict:
    """Variaciones, concentracion y perdidas sobre un juego de epigrafes.

    Con `ir_t` mayor que cero solo se analizan los epigrafes cuyo saldo del
    ejercicio auditado supera, en valor absoluto, la importancia relativa de
    trabajo: un epigrafe por debajo de la materialidad no puede originar una
    incorreccion material. Es la regla del proyecto de anclar los umbrales a
    `IR_T` y no a cifras inventadas.

    El resultado del ejercicio se salta ese filtro y entra siempre.
    """
    variaciones, concentraciones = [], []
    sin_masa: dict = {}                 # clase -> epigrafes sin masa de referencia
    desgloses_materiales = 0
    desgloses_inmateriales = 0
    desgloses_sin_ir_t = 0
    bajo_materialidad = []

    # Total de cada clase por ejercicio, para poder medir concentraciones.
    #
    # SI HAY FILA DE TOTAL, SE USA ESA. El balance la tiene: es la de
    # CodigoSeccion = 'TG' -«TOTAL ACTIVO», «TOTAL PATRIMONIO NETO Y PASIVO»- y
    # el comentario que habia aqui afirmaba lo contrario, asi que el total se
    # componia sumando las secciones Y la fila de total, con lo que salia el
    # doble del balance. Medido: los fondos propios pesaban «31,1 %» de un
    # balance del que son el 62,1 %. Un peso a la mitad no salta a la vista.
    #
    # Solo si no hay fila de total se suman las secciones, que es el caso de la
    # PyG: alli los agregados son las clases ST y T, no una seccion.
    totales: dict = {}
    con_fila_de_total: set = set()
    # Y COMO SE LLAMA ESA MASA, que es la mitad del asunto: si el script da el
    # importe pero no el nombre, quien redacte tiene que deducirlo del epigrafe
    # que esta mirando, y se equivoca. Paso en un informe real: los fondos
    # propios pesan el 62,1 % DEL BALANCE y se escribio «del patrimonio neto»,
    # del que son el 99,98 %. Cuatro riesgos de seis salieron con la masa mal.
    nombre_masa: dict = {}

    # EN LA PYG LA MASA DE REFERENCIA ES LA CIFRA DE NEGOCIOS. Sus epigrafes son
    # de clase 'I' y esa clase no tiene fila de total, asi que sin esto el peso
    # no se medía en absoluto -y el informe no lo decia, con lo que la ausencia
    # de la seccion se leia como «se miro y no habia nada»-. Medir cada partida
    # sobre las ventas es la lectura vertical habitual de la cuenta de
    # resultados: los aprovisionamientos son «el 86 % de las ventas», que es una
    # frase que un auditor entiende sin traducir. Decidido en cliente el
    # 25/08/2026, sobre la alternativa de usar el total de ingresos.
    for f in filas:
        if es_cifra_de_negocios(f):
            cn = serie_presentada(f)
            if abs(cn[0]) >= 1:
                totales["I"] = list(cn)
                nombre_masa["I"] = "la cifra de negocios"
            break

    for f in filas:                     # y las filas de total, si las hay
        if nivel(f) == 1 and str(f.get("CodigoSeccion", "") or "").strip().upper() == "TG":
            totales[clase_de(f)] = list(serie_presentada(f))
            nombre_masa[clase_de(f)] = concepto(f)
            con_fila_de_total.add(clase_de(f))
    for f in filas:
        if nivel(f) != 1:
            continue
        clase = clase_de(f)
        if clase in con_fila_de_total:
            continue
        acumulado = totales.setdefault(clase, [0.0] * EJERCICIOS)
        for i, v in enumerate(serie_presentada(f)):
            acumulado[i] += v

    for f in filas:
        n = nivel(f)
        if n == ENCABEZADO:             # cabecera de seccion: no es una cifra
            continue
        # Antes de contar nada: una fila sin concepto no se analiza, asi que
        # tampoco cuenta como desglose analizado. El recuento de `cobertura` tiene
        # que cuadrar con lo que se ha mirado de verdad.
        c = concepto(f)
        if not c:
            continue
        # Los desgloses de nivel 3 se miran SOLO si son materiales. Antes se
        # descartaban todos, y eso se comio la partida que mas importaba en dos de
        # tres ejecuciones sobre un expediente real: «Otras aportaciones de
        # socios», un desglose de fondos propios. Analizarlos todos seria ruido
        # -son la mayoria de las filas-, asi que entra el que supera la IR_T y los
        # demas se cuentan en `cobertura`. Sin IR_T no hay con que decidir y se
        # mantiene el comportamiento de antes: fuera.
        if n >= 3:
            if ir_t <= 0:
                desgloses_sin_ir_t += 1
                continue
            if abs(serie_presentada(f)[0]) < ir_t:
                desgloses_inmateriales += 1
                continue
            desgloses_materiales += 1
        clase = clase_de(f)
        crudo = serie(f)
        # Todo lo que sigue va sobre los saldos CONVERTIDOS, con la regla de
        # Gesia: es la unica forma de que el papel de trabajo de los mismos
        # numeros que el programa y el auditor pueda cuadrarlos.
        s = serie_presentada(f)

        if ir_t > 0 and abs(s[0]) < ir_t and not es_resultado(c):
            bajo_materialidad.append({"epigrafe": etiqueta(f), "concepto": c,
                                      "actual": round(s[0], 2)})
            continue

        cambio = crudo[0] * crudo[1] < 0
        sen = comparar(s[0], s[1], cambio)
        var = sen["variacion_absoluta"]
        base = {
            "epigrafe": etiqueta(f), "concepto": c, "nivel": n,
            # Lo que se pinta: el saldo convertido. Y al lado el saldo crudo del
            # expediente, para poder contrastar el papel contra la tabla.
            "actual": round(s[0], 2), "anterior": round(s[1], 2),
            "actual_gesia": round(crudo[0], 2),
            "anterior_gesia": round(crudo[1], 2),
            "es_subtotal": clase in ("T", "ST"),
            "sentido": sen["sentido"],
            "variacion_absoluta": sen["variacion_absoluta"],
            "ejercicio": ejercicios[0] if ejercicios else "",
            "ejercicio_anterior": ejercicios[1] if len(ejercicios) > 1 else "",
        }
        if var is not None and abs(var) >= VARIACION and abs(s[0] - s[1]) >= 1:
            variaciones.append(dict(base, variacion=var))
        elif var is None and abs(s[0]) >= 1:
            # Sin base utilizable no se da porcentaje. Dos casos distintos y los
            # dos se dicen con palabras: la partida no existia, o existia con un
            # importe despreciable frente al de ahora.
            variaciones.append(dict(
                base, variacion=None,
                nota=("partida nueva: no existía en el ejercicio anterior"
                      if abs(s[1]) < 0.005 else
                      "base del ejercicio anterior despreciable: el porcentaje "
                      "no sería significativo")))

        total = totales.get(clase, [0.0] * EJERCICIOS)[0]
        # La cifra de negocios es el denominador: medir su peso sobre si misma da
        # el 100 % y no informa de nada.
        if n >= 2 and es_cifra_de_negocios(f):
            continue
        if n == 2 and abs(total) < 1:
            # Epigrafe evaluable al que no se le puede medir el peso porque su
            # clase no tiene masa de referencia. Se cuenta para poder decirlo.
            sin_masa.setdefault(clase, 0)
            sin_masa[clase] += 1
        if n >= 2 and abs(total) >= 1:
            peso = abs(s[0]) / abs(total)
            if peso >= CONCENTRACION:
                concentraciones.append({
                    "epigrafe": etiqueta(f), "concepto": c,
                    "importe": round(s[0], 2), "total_clase": round(total, 2),
                    "peso": round(peso, 4), "clase": clase, "nivel": n,
                    # El nombre exacto de la masa sobre la que se mide el peso.
                    # USALO TAL CUAL al redactar. No lo sustituyas por el
                    # epigrafe que contiene la partida: el peso no es sobre eso.
                    "masa": nombre_masa.get(clase, ""),
                    "masa_es_suma": clase not in con_fila_de_total,
                })

    total_medidos = len(concentraciones)

    # Los totales anidados repiten el mismo importe: en un expediente real el
    # resultado del ejercicio salia en CUATRO filas con cuatro nombres. Se queda
    # una sola, y aqui esta el detalle que fallaba: no la primera que llega -que
    # dependia del orden de la tabla y era la menos informativa- sino la mas
    # agregada. Entre importes iguales gana el total sobre el subtotal y el
    # subtotal sobre el epigrafe, y a igualdad de clase la fila que va mas abajo
    # en el modelo, que es la mas final.
    unicas: dict = {}
    for v in variaciones:
        clave = (v["actual"], v["anterior"])
        previa = unicas.get(clave)
        if previa is None:
            unicas[clave] = v
            continue
        gana, pierde = ((v, previa) if _rango(v) > _rango(previa)
                        else (previa, v))
        gana.setdefault("tambien_en", []).extend(
            [pierde["concepto"]] + pierde.pop("tambien_en", []))
        unicas[clave] = gana
    variaciones = list(unicas.values())

    # Lo mismo con las concentraciones, y por el mismo motivo: al abrir el nivel 3
    # un desglose unico repite el importe exacto de su epigrafe padre. Medido: en
    # un expediente real «Efectivo y otros activos liquidos» y su unico desglose
    # «Tesoreria» salian los dos con el 50,8 %, que es la misma partida contada
    # dos veces. Gana la mas agregada y la otra se anota como `tambien_en`.
    unicas_c: dict = {}
    for c in concentraciones:
        clave = (c["importe"], c["clase"])
        previa = unicas_c.get(clave)
        if previa is None:
            unicas_c[clave] = c
            continue
        # Menor nivel = mas agregada. A igualdad, la que ya estaba.
        gana, pierde = ((previa, c) if previa.get("nivel", 9) <= c.get("nivel", 9)
                        else (c, previa))
        gana.setdefault("tambien_en", []).extend(
            [pierde["concepto"]] + pierde.pop("tambien_en", []))
        unicas_c[clave] = gana
    concentraciones = list(unicas_c.values())

    # DE QUE OTRA CONCENTRACION FORMA PARTE CADA UNA. Al abrir los niveles 3 y 4
    # salen padre e hijo, y si sus importes no son idénticos la deduplicación de
    # arriba no los une -ni debe: son cifras distintas-. Pero el peso del padre YA
    # INCLUYE al hijo, asi que presentarlos como dos concentraciones
    # independientes invita a sumarlos, y sumarlos esta mal. Medido en un
    # expediente real: «Reservas» al 35,6 % y su desglose «Otras reservas» al
    # 30,6 %, que leidos como cosas distintas dan un 66 % que no existe.
    #
    # Los codigos son jerarquicos -P.A.1.3.2 esta dentro de P.A.1.3- asi que la
    # relacion se deduce del propio codigo. Del ancestro mas proximo al mas
    # lejano.
    for c in concentraciones:
        dentro = [o for o in concentraciones
                  if o is not c and c["epigrafe"].startswith(o["epigrafe"] + ".")]
        if dentro:
            dentro.sort(key=lambda x: -len(x["epigrafe"]))
            c["dentro_de"] = [x["concepto"] for x in dentro]

    # Los epigrafes van antes que los subtotales. Un subtotal no explica nada por
    # si mismo: si la explotacion se mueve es porque se movio alguno de sus
    # componentes, y ese componente esta en la lista. Ordenados solo por tamano,
    # los subtotales copaban la cabecera de la tabla -cuatro de las ocho primeras
    # lineas- y repetian lo que la tabla del resultado ya dice.
    variaciones.sort(key=lambda x: (x.get("es_subtotal", False),
                                    -abs(x["variacion"] if x["variacion"] is not None
                                         else (x["variacion_absoluta"] or 9))))
    concentraciones.sort(key=lambda x: x["peso"], reverse=True)
    return {
        "que": que,
        # QUE SE HA MIRADO Y QUE NO. Si un umbral no se ha podido aplicar, tiene
        # que constar: una seccion que no aparece se lee como «se miro y no habia
        # nada», que es justo lo contrario de lo que ha pasado. En la PyG el peso
        # no se midio nunca -no hay masa de referencia- y el informe callaba.
        "cobertura": {
            "epigrafes_medidos": total_medidos,
            "epigrafes_sin_masa": sum(sin_masa.values()),
            "clases_sin_masa": sorted(sin_masa),
            "motivo": ("" if not sin_masa else
                       "de " + str(total_medidos + sum(sin_masa.values()))
                       + " epígrafes evaluables, a "
                       + str(sum(sin_masa.values())) + " no se les ha medido el "
                       "peso porque su clase (" + ", ".join(sorted(sin_masa))
                       + ") no tiene masa de referencia en esta fuente: no hay "
                       "fila de total que sirva de denominador. En la PyG las "
                       "filas de nivel 1 son subtotales de resultado, no masas "
                       "de ingresos o gastos."),
            "masas": {k: v[0] for k, v in totales.items()},
            # Los desgloses de nivel 3: cuantos han entrado y cuantos no. Antes no
            # entraba ninguno y no se decia.
            "desgloses_analizados": desgloses_materiales,
            "desgloses_bajo_materialidad": desgloses_inmateriales,
            "desgloses_sin_criterio": desgloses_sin_ir_t,
            "nota_desgloses": (
                "" if not desgloses_sin_ir_t else
                "hay " + str(desgloses_sin_ir_t) + " desglose(s) de nivel 3 que "
                "no se han mirado porque sin IR_T no hay con qué decidir si son "
                "materiales. Pasa --ir-t para que entren los que lo sean."),
        },
        "variaciones": variaciones,
        "concentraciones": concentraciones,
        "ir_t_aplicada": ir_t if ir_t > 0 else None,
        "epigrafes_bajo_materialidad": len(bajo_materialidad),
        "bajo_materialidad": bajo_materialidad[:MAX_LISTA],
        "totales_clase": {k: [round(x, 2) for x in v] for k, v in totales.items()},
    }


def resultado_por_ejercicio(pyg: list, ejercicios: list) -> dict:
    """Resultado de los cinco ejercicios y en cuantos hubo perdidas.

    La fila NO puede ser la primera que coincida por texto. En un expediente real
    hay tres que coinciden y la primera es «Resultado del ejercicio procedente de
    operaciones interrumpidas neto de impuestos», que vale cero: la serie salia a
    cero en los cinco ejercicios en una empresa con medio millon de beneficio. Y
    lo peor es que dependia del orden en que la tabla devolviera las filas, o sea
    del azar, porque la consulta no lleva ORDER BY.

    Se eligen todas las candidatas y gana la mas agregada: clase T antes que ST y
    que I, y a igualdad la seccion mas alta, que es la que va mas abajo en el
    modelo del PGC. En ese expediente: T seccion 5, «RESULTADO DEL EJERCICIO
    (A.4+19)».
    """
    candidatas = [f for f in pyg
                  if es_resultado(concepto(f).lower()) and 0 < nivel(f) <= 2]
    if candidatas:
        candidatas.sort(key=lambda f: _rango({"epigrafe": etiqueta(f)}), reverse=True)
        descartadas = [{"concepto": concepto(f), "epigrafe": etiqueta(f),
                        "actual": round(serie(f)[0], 2)} for f in candidatas[1:]]
        for f in candidatas[:1]:
            conv = serie_presentada(f)
            s = serie(f)
            # EN LA PYG DE GESIA EL SIGNO VA AL REVES DE LO INTUITIVO: los
            # ingresos y los beneficios son ACREEDORES, o sea negativos. Un
            # resultado de -492.656 es un BENEFICIO de 492.656 euros. La propia
            # fila lo dice: su ConceptoGastos es «BENEFICIOS ANTES DE IMPUESTOS».
            # Hasta el 25/08/2026 esto estaba invertido y el informe daba por
            # perdidas los beneficios. Detectado en cliente.
            # Con el saldo ya convertido, una perdida es lo que parece: negativa.
            perdidas = [i for i, v in enumerate(conv) if v < -0.005]
            return {
                "encontrado": True, "concepto": concepto(f),
                # Se invierte para presentarlo como lo lee un auditor: beneficio
                # en positivo, perdida en negativo. El dato de Gesia va al
                # contrario y mostrarlo tal cual obliga a traducir cada cifra.
                "serie": [round(v, 2) for v in conv],
                "serie_gesia": [round(v, 2) for v in s],
                "signo_invertido": True,
                "nota_signo": ("En la PyG de Gesia los beneficios son acreedores "
                               "(negativos). Aqui la serie va en signo natural: "
                               "beneficio positivo, perdida negativa."),
                "ejercicios": ejercicios,
                "ejercicios_con_perdidas": len(perdidas),
                "supera_umbral": len(perdidas) >= EJERCICIOS_PERDIDAS,
                "umbral": EJERCICIOS_PERDIDAS,
                # Para poder contrastar el papel con el expediente: que otras
                # filas decian llamarse resultado y con que importe.
                "otras_filas_de_resultado": descartadas,
            }
    return {"encontrado": False,
            "nota": "no se ha localizado la fila de resultado del ejercicio"}


def main() -> int:
    salida_utf8()
    resumen = con_resumen()
    p = argparse.ArgumentParser()
    p.add_argument("--balance", required=True)
    p.add_argument("--pyg", required=True)
    p.add_argument("--ratios")
    # Importancia relativa de trabajo, de contexto_expediente. Sin ella el
    # analisis mira TODOS los epigrafes y hay que decirlo: un riesgo sobre una
    # partida inmaterial no es un riesgo de incorreccion material.
    p.add_argument("--ir-t", type=float, default=0.0,
                   help="importancia relativa de trabajo; 0 = sin filtrar")
    # De donde sale la cifra. Importa en el papel de trabajo: una materialidad
    # calculada en Gesia y una dada a mano no acreditan lo mismo.
    # El auditor manda sobre la deteccion automatica de la clase de entidad, y
    # hace falta que pueda mandar: es_esal() busca vocabulario de entidad sin
    # animo de lucro en los epigrafes, y si el plan contable es el PGC estandar
    # NO LO ENCUENTRA aunque la entidad lo sea, porque el balance dice «Fondos
    # propios» igual que el de una mercantil. Medido en cliente: tres ejecuciones
    # sobre el mismo expediente, tres veces mal clasificado, y las tres hubo que
    # corregir el JSON a mano con un script suelto. Un paso manual que hace falta
    # el 100 % de las veces y que no esta documentado es un paso que falta.
    p.add_argument("--sin-animo-de-lucro", action="store_true",
                   help="la entidad NO tiene animo de lucro: fundacion, "
                        "asociacion, entidad publica. El informe dira «cuenta de "
                        "resultados» en vez de «cuenta de perdidas y ganancias».")
    p.add_argument("--mercantil", action="store_true",
                   help="lo contrario: fuerza sociedad mercantil aunque el "
                        "vocabulario del balance sugiera otra cosa.")
    p.add_argument("--ir-t-origen", choices=("gesia", "manual"), default=None,
                   help="gesia = calculada en el módulo de IR; manual = la dio "
                        "el usuario en el momento")
    p.add_argument("--ejercicios", default="",
                   help="del mas reciente al mas antiguo, p.ej. 2025,2024,2023,2022,2021")
    p.add_argument("--salida", required=True)
    args = p.parse_args()

    balance, pyg = leer(args.balance), leer(args.pyg)
    ejercicios = [e.strip() for e in args.ejercicios.split(",") if e.strip()]

    # ¿Hay cifras? Si casi todo viene a cero, el expediente no esta cargado y
    # cualquier analisis seria inventado.
    ceros = proporcion_ceros(balance + pyg)
    sin_datos = ceros >= UMBRAL_VACIO

    conceptos = [concepto(f) for f in balance + pyg]
    # Las dos banderas se excluyen. Con un if/elif ganaba la primera en silencio,
    # y la clase de entidad decide como se llama la cuenta de resultados en el
    # papel: no puede depender del orden en que se escribieron los argumentos.
    if args.sin_animo_de_lucro and args.mercantil:
        print("--sin-animo-de-lucro y --mercantil se excluyen: elige una.")
        return 2

    entidad = es_esal(conceptos)
    if args.sin_animo_de_lucro:
        entidad = {"esal": True,
                   "terminos": entidad["terminos"] + ["indicado por el auditor"]}
    elif args.mercantil:
        entidad = {"esal": False, "terminos": ["descartado por el auditor"]}

    salida = {
        "ejercicios": ejercicios,
        "entidad": {
            "sin_animo_de_lucro": entidad["esal"],
            "terminos_detectados": entidad["terminos"],
            # De donde sale la clasificacion, para que el papel pueda decirlo
            "origen": ("indicado por el auditor"
                       if (args.sin_animo_de_lucro or args.mercantil)
                       else "deducido del vocabulario del balance"),
            # El informe tiene que hablar el idioma de la entidad.
            "denominacion_resultados": ("cuenta de resultados" if entidad["esal"]
                                        else "cuenta de pérdidas y ganancias"),
        },
        "materialidad": {
            "ir_t": args.ir_t if args.ir_t > 0 else None,
            "origen": (args.ir_t_origen if args.ir_t > 0 else None),
            "aplicada": args.ir_t > 0,
        },
        "cobertura": {
            "proporcion_importes_a_cero": round(ceros, 4),
            "umbral": UMBRAL_VACIO,
            "sin_datos_suficientes": sin_datos,
        },
        "balance": analizar(balance, ejercicios, "balance", args.ir_t),
        "resultados": analizar(pyg, ejercicios, "resultados", args.ir_t),
        "resultado_ejercicio": resultado_por_ejercicio(pyg, ejercicios),
        "umbrales": {
            "variacion": VARIACION,
            "concentracion": CONCENTRACION,
            "ejercicios_con_perdidas": EJERCICIOS_PERDIDAS,
        },
    }
    if args.ratios:
        salida["ratios"] = leer(args.ratios)

    Path(args.salida).parent.mkdir(parents=True, exist_ok=True)
    Path(args.salida).write_text(
        json.dumps(salida, ensure_ascii=False, indent=1, allow_nan=False),
        encoding="utf-8")

    print("Escrito: " + args.salida)
    if sin_datos:
        print("\nATENCION: el " + str(round(ceros * 100)) + " % de los importes "
              "viene a cero (umbral " + str(round(UMBRAL_VACIO * 100)) + " %).")
        print("No hay datos suficientes para identificar riesgos. Para aqui y "
              "dilo: revisa que el expediente tiene las cifras cargadas.")
        return 1

    e = salida["entidad"]
    print("  entidad      " + ("sin ánimo de lucro" if e["sin_animo_de_lucro"]
                               else "sociedad mercantil")
          + (" (" + ", ".join(e["terminos_detectados"][:3]) + ")"
             if e["terminos_detectados"] else ""))
    print("  se dice      " + e["denominacion_resultados"])
    for que in ("balance", "resultados"):
        a = salida[que]
        print("  " + que.ljust(12) + str(len(a["variaciones"])) + " variaciones ≥ "
              + str(int(VARIACION * 100)) + " % · " + str(len(a["concentraciones"]))
              + " concentraciones ≥ " + str(int(CONCENTRACION * 100)) + " %")
    r = salida["resultado_ejercicio"]
    if r.get("encontrado"):
        print("  resultado    " + " / ".join(format(v, ",.0f") for v in r["serie"])
              + "  → pérdidas en " + str(r["ejercicios_con_perdidas"])
              + " de " + str(EJERCICIOS)
              + (" (supera el umbral)" if r["supera_umbral"] else ""))
    else:
        print("  resultado    " + r.get("nota", ""))

    # Decir siempre con que materialidad se ha trabajado, y cuanto se ha dejado
    # fuera: un recorte silencioso se lee como "no habia nada".
    if args.ir_t > 0:
        fuera = sum(salida[k]["epigrafes_bajo_materialidad"]
                    for k in ("balance", "resultados"))
        origen = {"gesia": "Gesia", "manual": "Manual"}.get(args.ir_t_origen, "?")
        print("  IR_T         " + format(args.ir_t, ",.2f").replace(",", " ")
              + "  (Origen: " + origen + ")  ·  " + str(fuera)
              + " epígrafes por debajo, no analizados")
        if args.ir_t_origen is None:
            print("               AVISO: no se ha indicado el origen "
                  "(--ir-t-origen gesia|manual); el informe no podrá decirlo")
    else:
        print("  IR_T         SIN APLICAR: se analizan todos los epígrafes, "
              "materiales o no")

    print("\nLos umbrales disparados, para elegir riesgos:")
    for que in ("balance", "resultados"):
        for v in salida[que]["variaciones"][:MAX_LISTA]:
            if v["variacion"] is None:
                pct = "s/base"
            else:
                pct = format(abs(v["variacion_absoluta"] or 0) * 100, ".1f") + " %"
            print("  " + que[:3] + " " + v["epigrafe"].ljust(9)
                  + v["sentido"].rjust(10) + pct.rjust(9) + "  "
                  + format(v["actual"], ",.0f").rjust(14) + "  "
                  + v["concepto"][:40]
                  + ("  (+" + str(len(v.get("tambien_en", []))) + " igual)"
                     if v.get("tambien_en") else ""))
    for c in salida["balance"]["concentraciones"][:MAX_LISTA]:
        print("  con " + c["epigrafe"].ljust(10)
              + format(c["peso"] * 100, ".1f").rjust(8) + " %  "
              + format(c["importe"], ",.0f").rjust(14) + "  " + c["concepto"][:44])
    resumen.guardar(ruta_resumen(args.salida))
    print("  resumen      " + ruta_resumen(args.salida))
    return 0


if __name__ == "__main__":
    sys.exit(main())
