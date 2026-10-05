---
name: cuestionario-cuentas-anuales-gesia
description: >
  Rellena el cuestionario de revisión del contenido de la memoria de un expediente de
  Gesia a partir de las cuentas anuales del cliente en PDF: un Excel con el formato de
  exportación de Gesia, listo para importar, y un papel en Word que justifica cada
  respuesta. Úsalo si piden revisar la memoria, contestar el cuestionario de cuentas
  anuales o comprobar qué desgloses faltan, o dicen "revisa la memoria", "rellena el
  AG)20" o "checklist de la memoria". NO es para el diario contable, ni para ratios o
  revisión analítica. SI SOLO DICEN «CUENTAS ANUALES», NO LANCES NADA: este revisa EL
  CONTENIDO DE LA MEMORIA y necesita el PDF; estados-financieros revisa LAS CIFRAS del
  expediente, sin PDF. Pregunta cuál quieren. Requiere el servidor API de Gesia arrancado
  y las cuentas anuales en PDF.
---

# Revisión del contenido de la memoria (Gesia)

Produce un papel de trabajo, no una publicación. Los dos ficheros se escriben **siempre**
en `<expediente>\AsistenteIA\CuestionarioCuentasAnuales\` —la regla del proyecto de una
subcarpeta por skill, para que el auditor sepa dónde buscar sin preguntar— y **nunca se
publican** en ninguna URL: contienen las cuentas anuales de un cliente auditado.

Los dos scripts de generación crean esa carpeta si no existe. No hace falta `mkdir`.

---

## Antes de empezar: ¿te han pedido la memoria, o las cifras?

**«Cuentas anuales» no es este skill, ni es el otro: son las dos cosas.** Aquí se revisa **el
contenido de la memoria** contra el PDF del cliente; las cifras del expediente —balance,
resultados, patrimonio neto y flujos— las revisa `estados-financieros`, que no necesita PDF.

Si la petición no distingue, **pregunta antes de tocar nada** y ofrece las dos. La pista más
fiable: **sin PDF del cliente este skill no puede trabajar**, así que si no hay PDF a la vista,
casi seguro te están pidiendo el otro.

---

## Cuatro reglas que gobiernan todo

**1. Ante la duda, `4`.** Un `4` (Pendiente) de más le cuesta al auditor un minuto de
revisión. Un `1` (Sí) de más es un desglose que ya no vuelve a mirar nadie. **No se
responde `1` sin poder citar dónde está el desglose en la memoria.**

**2. Esto propone, no concluye.** El auditor revisa el Excel antes de importarlo y es
quien firma. El papel de trabajo lo dice explícitamente, y esa frase no se quita.

**3. `Disponible = False` no se toca.** Es una decisión del auditor sobre qué aplica al
encargo. Un skill que la ignora está deshaciendo trabajo hecho.

**4. La importancia relativa no filtra los hallazgos.** Si el desglose falta, va un `2`
aunque el importe sea ridículo. Se revisa si el desglose **está**, no si la cifra mueve la
opinión. Medido: de los cuatro hallazgos que en el expediente de calibración el modelo
marcó y el auditor
no, el auditor confirmó los cuatro — y dos eran de 4.875 € y 239 €. Un umbral de importe habría
borrado la mitad de lo que este skill aporta.

---

## Dónde están los scripts

Al cargarse, el runtime indica el **directorio base de este skill**. Todas las rutas
`scripts/…` son relativas a ese directorio, no al directorio de trabajo. Guárdalo al
empezar:

```bash
SKILL="<directorio base indicado al cargar el skill>"
TRABAJO="$(pwd)/trabajo" && mkdir -p "$TRABAJO"
```

**El dato entra por el MCP, siempre.** Los scripts no hablan con el API de Gesia: lo
hicieron hasta el 23/08/2026 y eso hacía el skill inservible en Cowork, porque ni el
sandbox ni el `device_bash` alcanzan el `localhost` del auditor. El cuestionario entra
en una sola llamada a `exportar_consulta`, que lo deja en disco: son 154 filas y ~94.000
caracteres —`consultar_gesia` cortaría en 60.000—, y tú lees de ese fichero solo la
sección que estás contestando.

**Dónde se exporta depende del entorno**, porque quien exporta y quien calcula no
siempre son la misma máquina (ver `docs/arquitectura.md`):

```bash
# En la máquina del auditor: MCP y scripts comparten disco.
DATOS="$TRABAJO"

# En Cowork: exportar DENTRO de una carpeta conectada -una ruta del sandbox o
# del $TEMP de Windows no sirve-, subirla con device_stage_files, y leer la
# copia que aparece en el sandbox.
#   exportar_consulta(..., ruta = "<raíz conectada>/_tmp_cowork/cuestionario.json")
DATOS="/mnt/user-data/uploads/_tmp_cowork"
```

---

## Secuencia

### Paso 1 — Expediente

```
configurar()            # sin parámetros: ver estado
contexto_expediente()
```

Si falta `gs3_file`, **pide la ruta al usuario**. No la adivines. Si el servidor API no
responde, dile que lo arranque en *Herramientas > Gesia - Cuadro de mando > Arrancar
servidor API*: hay que hacerlo cada vez que se abre Gesia.

### Paso 2 — Localizar el cuestionario

Es el `Referencias` con `CodigoTipoGuia = 'CCC'`, `CodigoReferencia LIKE 'AG)20/%'` y
`Disponible = True`.

```sql
SELECT CodigoReferencia, Referencia, Disponible
FROM Referencias
WHERE CodigoTipoGuia = 'CCC' AND CodigoReferencia LIKE 'AG)20/%'
ORDER BY CodigoReferencia
```

Las cuatro modalidades —PYME, abreviada, normal y consolidada— **existen siempre las
cuatro**; el auditor activa la que aplica. Si hay **ninguna disponible o más de una,
pídele la referencia al usuario**. No elijas tú.

> **Ojo, dos cosas, y las dos muerden** (medido el 01/09/2026 en dos expedientes):
>
> 1. `AG)20` es solo el nodo del índice y **tiene cero filas**. El contenido cuelga de
>    sus hijos. Ni su título ni la numeración de los hijos son fijos: se llama
>    «ESTADOS FINANCIEROS (CUENTAS ANUALES)» en un expediente y «MEMORIA Y CUENTAS
>    ANUALES» en otro, y la memoria PYME es `AG)20/01` en uno y `AG)20/05` en otro.
>    **Nunca fijes el código**: localiza por tipo, título y `Disponible`.
> 2. **Puede haber más de un `CCC` con `Disponible = True`.** En un expediente real
>    salían dos: la revisión de la memoria (154 filas) y una «Revisión de las cuentas
>    anuales» de 23. Si la consulta devuelve varias, **pregunta cuál**, o dilo y
>    quédate con la de más filas; lo que no vale es coger la primera en silencio.

### Paso 3 — Pedir y preparar las cuentas anuales

**Sin el PDF no se responde nada.** Pídeselo al usuario: puede subirlo o indicarte dónde
está en la carpeta del expediente.

**Lee el PDF directamente, sin convertirlo con ningún script.** La herramienta de lectura
abre PDFs, y los abre igual de bien cuando son un escaneo — que es el caso normal, no la
excepción: las cuentas anuales que el auditor archiva son el ejemplar **firmado**, y en
el expediente de calibración eran 31 páginas con **cero** caracteres extraíbles.

Van en tramos de 20 páginas como máximo por lectura, así que unas cuentas anuales normales
son dos lecturas.

Léelas **todas** antes de contestar la primera pregunta.

**Y en cuanto acabes de leerlas, escribe tus notas en disco**, en
`$TRABAJO/memoria_notas.md`: qué notas tiene la memoria, en qué página del PDF empieza cada
una, y los datos que ya sepas que vas a necesitar —importes del balance, criterios de la
nota 4, lo que aparezca y lo que no—. La numeración interna del documento no suele coincidir
con la del PDF, así que anota las dos.

No es burocracia: **contestar 137 preguntas es una sesión larga y el contexto se compacta a
mitad.** Cuando pasa, sin esas notas hay que releer el PDF entero otra vez. Medido en
cliente el 23/08/2026: la segunda lectura de 33 páginas costó unos cinco minutos de sesión,
y era evitable. Con las notas en disco, tras una compactación relees el fichero y sigues;
solo vuelves al PDF para lo que las notas no resuelvan.

> Aquí había un `preparar_memoria.py` que rendería las páginas con PyMuPDF. Se quitó el
> 22/08/2026: obligaba al cliente a instalar Python y `pymupdf` para hacer algo que el
> modelo ya hace solo. Ver `DISENO.md`, «Lo que se ejecuta y dónde».

### Paso 4 — Traer el cuestionario

**El dato entra por el MCP, siempre.** Los scripts de este skill no hablan con el API de
Gesia<!-- solo-cowork:alt=. -->: lo hicieron hasta el 23/08/2026 y eso lo hacía inservible en Cowork, porque ni el
contenedor ni el `device_bash` alcanzan el `localhost` del auditor.<!-- /solo-cowork -->

**Una sola consulta, y a fichero.** El cuestionario no cabe en una respuesta —el PYME son
unos 129.000 bytes y `consultar_gesia` corta en 60.000—, pero eso da igual porque
`exportar_consulta` escribe en disco y a ti solo te devuelve el recuento:

```
exportar_consulta(
  sql = "SELECT Prioritaria, CodigoArea, CodigoGuia, CodigoOrden, Punto,
                DesglosePunto, Descripcion, CodigoClaseReferencia,
                CodigoReferencia, CodigoRealizado, Respuesta, Comentario
         FROM DetalleGuias
         WHERE CodigoGuia = '<el código localizado>'
         ORDER BY Val(CodigoOrden)",
  ruta = "<en local: $TRABAJO/cuestionario.json — en Cowork: <raíz conectada>/_tmp_cowork/cuestionario.json>")
```

<!-- solo-cowork -->**En Cowork, súbelo después con `device_stage_files`** y trabaja con la copia
del sandbox. Si exportas a una ruta que no esté bajo una carpeta conectada, no
se puede subir y el fichero no le sirve al script: hay que reexportarlo.<!-- /solo-cowork -->

Las doce columnas y en ese orden: son las del export de Gesia y `generar_xlsx.py` las copia
literales.

Dos detalles que cuestan una vuelta si se olvidan:

- **`ORDER BY Val(CodigoOrden)`, no `ORDER BY CodigoOrden`.** El campo es texto, así que sin
  `Val()` ordena 1, 10, 100, 101… y las secciones salen entrelazadas.
- **`Punto` es numérico** y va sin comillas si alguna vez lo filtras.

**Comprueba el recuento que te devuelve** y quédatelo: es con lo que se compara luego si el
contrato avisa de que faltan preguntas. El PYME son 154 filas.

**No abras `cuestionario.json`.** Lo leen los scripts, y es justo el fichero que no tiene
que pasar por tu contexto: son 129 KB de texto del máster que no aportan nada hasta que hay
que contestar una sección concreta, y para eso está `mostrar_seccion.py`.

### Paso 5 — Verificar el contrato (puede abortar)

```bash
python "$SKILL/scripts/verificar_contrato.py" \
    --cuestionario "$DATOS/cuestionario.json" --guia "<el código que hayas localizado>"
```

Salida `2` → **para**. No se genera nada. Salida `1` son avisos: léelos, sobre todo el
**C12**, que dice si el cuestionario ya tenía respuestas. Si las tenía, **pregunta al
usuario** si se rellenan solo los huecos o se rehace entero, antes de seguir.

### Paso 6 — Responder, sección a sección

Recorre las secciones de una en una. Para cada una:

```bash
python "$SKILL/scripts/mostrar_seccion.py" --cuestionario "$DATOS/cuestionario.json" --punto 3
```

Con las preguntas de esa sección y la memoria delante, decide para cada pregunta:

| Código | Cuándo |
|---|---|
| `1` Sí | el desglose **está** en la memoria y puedes decir dónde |
| `2` No | el desglose **debería estar y no está** |
| `3` No aplica | lo que la pregunta nombra **no existe** en esta empresa |
| `4` Pendiente | **la memoria no permite decidirlo.** Es la respuesta por defecto |

**`1` y `3` significan lo mismo para el trabajo: esta pregunta no arroja hallazgo.** Cuál
de los dos se pone es convención del auditor que contesta, no criterio de auditoría, y por
eso `probar_calibracion.py` los colapsa: el número que mide el skill es el del eje
hallazgo/no hallazgo. **No gastes esfuerzo en afinar esa frontera.**

Se intentó dar una regla y no funciona. En la segunda calibración fueron 23 de 42 discrepancias —18 en
un sentido y 5 en el otro—, y no se deduce de la memoria: de las 55 respuestas `3` con
motivo negativo el auditor dio por buenas 39, así que voltearlas en bloque arreglaba 16 y
rompía 39.

La única pauta que ayuda: **si la memoria dice algo sobre la pregunta —aunque sea que la
circunstancia no se da—, pon `1`**; reserva `3` para cuando lo que la pregunta nombra no
existe en esta empresa y la memoria calla. Y si el expediente ya trae secciones
contestadas, copia la convención que siga de hecho.

**Y responde `4` siempre que contestar exija saber algo que no está en las cuentas
anuales.** Ejemplo real: «si hay proveedores con vencimiento superior a un año, la partida
se desglosa» no se puede responder leyendo el balance —donde no aparecen— porque la
pregunta es si *existen*, y eso lo sabe el auditor, no la memoria. Contestar `3` ahí borra
un hallazgo: es como se perdieron 4 de los 12 que había en el expediente de calibración.

**Antes de firmar un `2`, pasa estos cuatro filtros.** Salen de la tercera calibración
(19/09/2026), en la que el auditor revisó **13 respuestas `2` y las trece se cayeron**: doce
estaban mal y la decimotercera es cierta pero inmaterial. No es que el modelo marcara de más
por valiente: es que dio por incumplimiento cuatro cosas que no lo eran.

**(a) ¿Tu motivo empieza por «no se menciona», «no existe nota sobre» o «no informa de»?**
Entonces pregúntate si eso que falta **existiría en esta empresa**. Ocho de los trece eran
desgloses cuya circunstancia de fondo no se da: no hay capitalización de gastos financieros,
no hay costes de desmantelamiento, no hay deterioro de las inversiones en el grupo, la deuda
no tiene garantía real, no hay compromisos fuera de balance. La memoria no lo cuenta porque
no hay nada que contar. **Si no puedes saber desde las cuentas anuales si la circunstancia se
da, es `4`, no `2`.** Es la regla 1 de arriba, aplicada donde más se incumple.

**(b) ¿La pregunta es de presentación o de desglose?** Si versa sobre **cómo se presenta una
partida** en el balance o en la cuenta de pérdidas y ganancias —si el capital está inscrito,
si Aprovisionamientos separa los trabajos de otras empresas— no es una obligación de
información de la memoria y no se responde leyéndola: va `3`. Dos de los trece.

**(c) ¿Has mirado la memoria entera, o solo la nota que sugiere el cuestionario?** Dos de los
trece estaban informados **en otra nota**: el salto de Mobiliario lo explicaba la 8.1 cuando
el motivo decía que faltaba en la 6. Busca el dato por toda la memoria antes de decir que no
está.

**(d) ¿Estás dando por hecho algo del encargo que la memoria no dice?** Quién administra la
sociedad, quién es apoderado, quién debe firmar. El modelo dedujo de una nota que una persona
era administradora, montó dos hallazgos sobre su firma ausente, y resultó ser el director
general. **Los hechos del encargo no se deducen de la memoria: si hacen falta, es `4`.**

Y cuando el `2` pase los cuatro filtros, **ponle el importe en el motivo**. La regla 4 de
arriba sigue en pie —la importancia relativa no filtra hallazgos, y está medida: el auditor
confirmó hallazgos de 4.875 € y de 239 €—, pero con la cifra delante descartar uno inmaterial
le cuesta un vistazo en vez de una búsqueda.

**Dicho todo eso, no te vuelvas tímido.** En las dos primeras calibraciones los `2` fueron
buenos —nueve de nueve válidos en la primera, cero peligrosos en la segunda— y cuatro eran
desgloses que el auditor no había detectado. El coste de este skill sigue estando en los
hallazgos que **no** ve. Los filtros de arriba no dicen «marca menos»: dicen **«lo que no
puedas decidir leyendo las cuentas, déjalo en `4` y que se vea en el Word»**, que es para lo
que está el papel de trabajo. Este skill contesta de una pasada y deja escritas las dudas; no
se convierte en un interrogatorio al auditor.

Ve acumulando en `$TRABAJO/respuestas.json`:

```json
{"respuestas": [
  {"orden": 2, "respuesta": 1,
   "motivo": "La memoria incluye balance, PyG y memoria PYME",
   "evidencia": "Índice, p. 1"}
]}
```

`orden` es el `CodigoOrden` de la fila. **Toda pregunta lleva una entrada** — si no se
puede contestar, va un `4` con el motivo. Las **cabeceras de sección no se responden**:
`mostrar_seccion.py` ya no te las enseña.

`evidencia` es obligatoria para un `1`. Sin ella, la respuesta es `4`.

### Paso 7 — Generar el Excel

```bash
python "$SKILL/scripts/generar_xlsx.py" \
    --cuestionario "$DATOS/cuestionario.json" \
    --respuestas "$TRABAJO/respuestas.json" \
    --salida "<destino>/AG20-01_<CLIENTE>_<EJERCICIO>.xlsx"
```

Aborta si falta alguna pregunta por responder o si hay respuestas fuera de 1-4.

<!-- solo-cowork:alt=**El destino es la carpeta del expediente**, directamente: `<expediente>/AsistenteIA/CuestionarioCuentasAnuales/`. Vale igual para el papel de trabajo del paso siguiente. -->**El destino depende del entorno.** En la máquina del auditor, directamente
`<expediente>/AsistenteIA/CuestionarioCuentasAnuales/`. En Cowork el script escribe
en el sandbox, así que va a `$TRABAJO` y luego se baja: `SendUserFile` devuelve un
`file_uuid` y `device_commit_files` lo escribe en esa carpeta del expediente. Vale
igual para el papel de trabajo del paso siguiente.<!-- /solo-cowork -->

Copia once columnas literales del expediente y calcula una, `Respuesta`. En particular
**`CodigoRealizado` no se deduce**: hay expedientes con preguntas contestadas y esa
columna vacía, así que rellenarla sería inventar dato.

### Paso 8 — Generar el papel de trabajo

```bash
python "$SKILL/scripts/generar_papel.py" \
    --cuestionario "$DATOS/cuestionario.json" \
    --respuestas "$TRABAJO/respuestas.json" \
    --generado "<AAAA-MM-DD>" \
    --cliente "<razón social>" --cierre "<fecha de cierre>" \
    --salida "<expediente>/AsistenteIA/CuestionarioCuentasAnuales/revision_memoria_<CLIENTE>_<EJERCICIO>.docx"
```

`--generado` es obligatorio y lo pones tú: **nada en este skill lee el reloj**. Un papel de
trabajo tiene que poder regenerarse idéntico dentro de dos años.

**`--cliente` y `--cierre` salen de `contexto_expediente`** y hay que pasarlos. Si los
omites, la cabecera del papel sale en blanco: antes se leían del API y, cuando el API no
respondía, quedaba vacía sin decir nada. Ahora al menos el hueco se ve en el comando.

### Paso 9 — Entregar

Di la ruta completa de los dos ficheros —siempre
`<expediente>\AsistenteIA\CuestionarioCuentasAnuales\`— y **cuántas preguntas
quedaron en `2` y en `4`**, que es el trabajo que le queda al auditor. Recuérdale que:

- el Excel se importa **desde Gesia**, y conviene revisarlo antes. El formato está
  comprobado contra el importador real (22/08/2026), así que si algo falla al importar es
  el contenido, no la estructura;
- las respuestas son una propuesta, y la revisión y la firma son suyas.

**Los temporales.** Los volcados de `exportar_consulta` los borra
`limpiar_exportaciones()`, y esa es la vía: funciona igual en local y en Cowork
—lo borra el MCP, que corre en la máquina del usuario— y borra lo que él escribió
sin que haya que decirle cuál. Si alguno no se deja, lo dice con su ruta.

El directorio de trabajo va aparte:

```bash
rm -rf "$TRABAJO"
```

**Y cuenta con que en Cowork no te dejen**: el puente no tiene permiso de borrado
en el equipo del usuario (comprobado el 25/08/2026). Por eso los volcados van a la
carpeta temporal del sistema y **nunca a `AsistenteIA`**, donde solo debe quedar
el entregable. Si el borrado falla, di las rutas exactas de lo que queda.


---

## Lo que este skill no hace

Decirlo importa: callar una limitación es peor que tenerla, y la conversación no va al
archivo del encargo. El papel de trabajo ya lo recoge, pero tenlo presente al explicarlo:

- **No escribe en el expediente.** El MCP solo lee; el auditor importa el `.xlsx` a mano.
- **No juzga si la memoria es correcta**, solo si el desglose **está**.
- **No contrasta las respuestas contra los saldos** del expediente. Una pregunta
  respondida «no aplica» sobre un epígrafe con saldo no se detecta hoy.
- **No cuadra el balance ni la PyG** contra el PDF.
- **No cubre los demás cuestionarios `CCC`** (continuidad, independencia, control interno).
