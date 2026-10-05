---
name: fsp-mum-nia530-gesia
description: >
  Redacta en Word el PAPEL DE TRABAJO de la NIA-ES 530 de una prueba MUM de ForSampling:
  objetivo, población y su cuadre, parámetros del diseño, selección, resultados por
  elemento, desviaciones, lo que falta y las firmas, todo leído de los ficheros de
  ForSampling. Si fsp-mum se ha ejecutado en la sesión, toma de su Excel los resultados
  por elemento. Úsalo si piden el papel de la NIA 530, documentar o redactar la prueba de
  muestreo o el memorándum del muestreo, o dicen "haz el papel de la NIA 530 de la MUM".
  NO valida facturas ni mide importes (eso es fsp-mum) y NO es la prueba de cumplimiento.
  NO proyecta el error ni dice si la prueba se supera: la conclusión queda en blanco, que
  es del auditor. Requiere el servidor API arrancado y el .cli o el expediente que lo
  vincula.
---

# Papel de trabajo NIA-ES 530 de una prueba MUM (Word)

Escribe lo que la NIA-ES 530 pide documentar de una prueba de muestreo por unidades monetarias,
con la fuente de cada dato al lado, y deja en blanco —marcado **PENDIENTE** y con quien lo
aporta— todo lo que no consta en ningún fichero. No infiere, no estima, no rellena con
ejercicios anteriores.

El fichero se escribe en `<expediente>\AsistenteIA\FspMum\`, la misma carpeta que el papel en
Excel de `fsp-mum`, con el nombre `Papel NIA-ES 530 <prueba> <cliente> <fecha>.docx`, y **nunca
se publica** en ninguna URL: describe una prueba de auditoría de un cliente. `<expediente>` es
**la carpeta del fichero configurado**: la del `.gs3`, o la del `.cli` cuando se trabaja solo
con ForSampling, sin expediente de Gesia.

---

## Las reglas, heredadas de fsp-mum

- **Todo sale de los ficheros de ForSampling, por el MCP.** El informe PDF que emite
  ForSampling **no es una fuente**: sirvió para saber qué hay que documentar, y nada se
  transcribe de él. Lo que ForSampling no guarda en sus ficheros —la proyección del error
  (estimación, IMS, IMI, límite superior, texto de conclusión) y la distribución; medido en las
  40 tablas del `.cli` y en las del fichero de la prueba— **no se rellena ni se recalcula**: el
  apartado 8 dice que se calcula al emitir el informe, y el informe se adjunta como anexo.
- **No proyecta ni concluye.** La conclusión de auditoría queda en blanco: es del auditor.
- **Ningún nombre de tercero sale del equipo del auditor.** Se trabaja con el perfil `fsp-mum`
  y los terceros van por su token (`PROV`, `CLI`, `TER`). Si la muestra llega sin tokenizar, el
  constructor **para** y manda volver a configurar. El Word lleva tokens; la equivalencia con
  el nombre la recupera el auditor con `rehidratar` cuando el MCP acepte `.docx`.
- **Las unidades MUM son la suma de `Repeticiones`**; los elementos distintos son otra cosa, y
  las dos cifras se dan por separado.
- **Los errores por exceso y por defecto se listan separados y no se netean.**
- **Solo lee.** No escribe nada en ForSampling ni en Gesia.
- **Nada lee el reloj:** la fecha de generación se pasa a los scripts.

---

## Dónde están los scripts

Al cargarse, el runtime indica el **directorio base del skill**. Las rutas `scripts/…` son
relativas a él:

```bash
SKILL="<directorio base indicado al cargar el skill>"
TRABAJO="$(pwd)/trabajo" && mkdir -p "$TRABAJO"
```

**Dónde es `<DATOS>` no depende del producto, depende de una propiedad**: si los scripts y el
MCP comparten disco. En local, `DATOS="$TRABAJO"`. En un contenedor, `$DATOS` es un directorio
escribible del contenedor al que se copia lo exportado; es la misma regla, palabra por palabra,
que en `fsp-mum`, y si `fsp-mum` se ha ejecutado en la sesión **`$DATOS` es el suyo**: ahí
están ya `muestra.json`, `parametros.json` y `evaluacion.json`.

---

## Secuencia

### Paso 1 — Contexto y prueba

`configurar(gs3_file=…, perfil="fsp-mum")`. Con un `.gs3` que vincula el cliente de muestreo
vale igual que con el `.cli` directamente. Si responde que el API no contesta, llama a
`arrancar_api` y sigue.

Si el fichero es un `.gs3`, guarda también el contexto: `contexto_expediente()` → escríbelo tal
cual en `<DATOS>/contexto.json`. Trae la razón social, el cierre y la importancia relativa
(`IR_P`, `IR_T`, `IR_I`). Con un `.cli` solo, **no hay contexto**: el papel sale en modo
`solo_fs` y lo de Gesia se solicita en el apartado 9.

`obtener_entidad('pruebas')` → guárdalo en `<DATOS>/pruebas.json`. Elige la prueba MUM
(`Tipo = MUM`); si hay varias, **pregunta cuál**. Anota su `MuestraId`.

### Paso 2 — Las cuatro exportaciones de la prueba

```
obtener_entidad('parametros', id = <MuestraId>)   → <DATOS>/parametros.json   (tal cual)
obtener_entidad('resumen',    id = <MuestraId>)   → <DATOS>/resumen.json      (tal cual)
exportar_consulta(entidad = "muestra",    id = <MuestraId>, ruta = "<DATOS>/muestra.json")
exportar_consulta(entidad = "evaluacion", id = <MuestraId>, ruta = "<DATOS>/evaluacion.json")
```

`parametros` trae el bloque **`descodificado`**: confianza y factor del riesgo general, criterio
y método de selección, si el error tolerable se definió por valor o por tasa, y **los dos
factores de confianza** con su fuente. `resumen` trae la población en cifras sin una sola fila:
elementos, valor, máximo, seleccionados, selecciones, intervalo, cobertura, el desglose por
grupo y **el cuadre del `.smp` de importación con el fichero de la prueba**. Si alguna de las
dos no trae eso, el MCP es anterior a la 1.23.0: el papel saldrá con más PENDIENTES y hay que
decirlo.

Si `fsp-mum` se ejecutó en la sesión, `muestra.json` y `evaluacion.json` **ya existen**: no los
exportes dos veces.

### Paso 3 — Construir el JSON del papel (puede abortar)

```bash
python "$SKILL/scripts/construir_nia530.py" --id <MuestraId> \
  --pruebas "$DATOS/pruebas.json" --parametros "$DATOS/parametros.json" \
  --resumen "$DATOS/resumen.json" --muestra "$DATOS/muestra.json" \
  --evaluacion "$DATOS/evaluacion.json" \
  [--contexto "$DATOS/contexto.json"] [--excel "<papel de fsp-mum>.xlsx"] \
  --salida "$DATOS/nia530.json"
```

`--excel` es el papel de `fsp-mum` de **esta** sesión —la copia tokenizada, nunca la
rehidratada—: de él salen el importe según documento y el error de cada elemento. Sin él, los
apartados 6 y 7 salen PENDIENTES; **propón ejecutar `fsp-mum` antes**, y si el auditor no
quiere, sigue sin él.

Salida `2` → **no hay papel**: la prueba no es MUM, falta una exportación, o **la muestra no
está tokenizada** (el nombre del tercero iría al Word: se para). Salida `1` → se sigue, y los
avisos van al auditor literales. Salida `0` → todo encaja.

Después de construirlo, **abre `nia530.json` y completa lo que es del auditor si él te lo ha
dicho en la conversación**, y solo eso: `afirmacion`, `riesgo_area`, `p.motivacion`,
`conciliacion_detalle`, `causa_errores`, `anomalias`, `por_cuenta` (si te ha dado el saldo
contable por cuenta) y `diario`. Lo que no te haya dicho se queda en `null`.

### Paso 4 — Generar el Word

```bash
python "$SKILL/scripts/generar_nia530.py" \
  --datos "$DATOS/nia530.json" --generado "<dd/mm/aaaa de hoy>" \
  --salida "<expediente>/AsistenteIA/FspMum/Papel NIA-ES 530 <prueba> <cliente> <fecha>.docx"
```

Antes de escribir comprueba que la suma de unidades es el tamaño seleccionado, que hay tantos
elementos como únicos, que el cuadre `.smp`/`.pcu` no está marcado en rojo y **que ningún
tercero es otra cosa que un token**. Si algo no cuadra, no escribe (salida `2`); `--forzar`
lo escribe igualmente y lo deja anotado. No pisa un fichero que ya exista.

### Paso 5 — Entregar

Di al auditor, en pocas líneas:

- dónde está el fichero, con la ruta completa
- el **modo**: con expediente de Gesia, o solo ForSampling
- **qué falta**, en una lista corta y con quién lo aporta: la ejecución de `fsp-mum`, el
  saldo contable por cuenta, la motivación y la conclusión; y que **el informe emitido por
  ForSampling se adjunta como anexo**, porque la proyección solo existe ahí
- si la prueba **no está finalizada** en ForSampling
- si hay **elementos sin documento**: el apartado 11 de la NIA manda tratarlos como
  incorrección salvo procedimiento alternativo, y eso lo decide el auditor
- que el Word **lleva tokens** en vez de nombres

Y nada sobre si la prueba se supera. Eso no es de este papel.

---

## Lo que este skill no hace

- **No valida documentos** ni mide importes: es `fsp-mum`.
- **No proyecta, no compara con el error tolerable como conclusión, no concluye.** Y no
  transcribe nada de un PDF: el informe de ForSampling es un anexo, no una fuente.
- **No rellena lo que es del auditor**: afirmación, motivación, conciliación detallada, causa
  de los errores, anomalías y conclusión quedan en blanco salvo que él los haya dado.
- **No escribe en ForSampling ni en Gesia.**
- **No abre el `.pcu` ni el `.smp` por su cuenta**: los agregados los da `resumen`, por el API.
- **No hace la prueba de cumplimiento** ni la circularización.

---

## Degradación

| Situación | Qué hace |
|---|---|
| El API no responde | `arrancar_api` y repite; solo si eso falla, se lo dice al auditor |
| Solo hay `.cli`, sin expediente de Gesia | modo `solo_fs`: lo de Gesia va PENDIENTE y el apartado 9 es la lista de lo que se solicita |
| La muestra llega sin tokenizar | **para**: vuelve a `configurar(gs3_file=…, perfil="fsp-mum")` y exporta otra vez |
| El MCP es anterior a la 1.23.0 | sigue: confianza, factor, método, criterio y cuadre salen PENDIENTES, y se dice |
| No se ha ejecutado `fsp-mum` | sigue: importe según documento y error PENDIENTES; propón ejecutarlo |
| La prueba no está finalizada | sigue y lo marca en ámbar en la portada y en los puntos abiertos |
| El `.smp` y el fichero de la prueba no cuadran | el constructor avisa y el generador no escribe sin `--forzar`: hay que entenderlo antes |
| Hay varias pruebas MUM | pregunta cuál |
| La prueba no es MUM | **para**: este papel es de la NIA-ES 530 para MUM |

---

## Comprobar que el skill funciona

```bash
python "$SKILL/scripts/probar_nia530.py"
```

Exportaciones sintéticas con la forma exacta del MCP 1.23.0 —medida sobre una prueba real—,
constructor y generador de punta a punta, y las reglas que no pueden romperse: solo tokens en
el Word, unidades como suma de repeticiones, errores sin netear, proyección ni calculada ni
transcrita —el apartado 8 remite al informe emitido—, y una muestra sin tokenizar que para el
skill.
