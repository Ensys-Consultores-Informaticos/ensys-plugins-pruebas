---
name: identificacion-riesgos-gesia
description: >
  Identifica los riesgos de auditoría de un expediente de Gesia conforme a la
  NIA-ES 315, eligiéndolos del catálogo de riesgos del máster, a partir del
  balance y la cuenta de resultados de los cinco últimos ejercicios. Produce un
  informe en Word con las cifras que justifican cada riesgo y los procedimientos
  previstos.
  Usa este skill cuando el usuario pida identificar o valorar los riesgos de un
  encargo, la NIA 315, los riesgos de incorrección material, o diga cosas como
  "identifica los riesgos", "qué riesgos tiene este cliente", "riesgos de
  auditoría del expediente", "prepara la identificación de riesgos" o "valora los
  riesgos del encargo".
  NO es el cuadro de mando del diario, ni el cuestionario de la memoria, ni la
  prueba de continuidad de saldos.
  Requiere Gesia abierto con el servidor API arrancado y un expediente con las
  cifras de balance y resultados cargadas.
---

# Identificación de riesgos de auditoría (NIA-ES 315)

Propone riesgos **elegidos de un catálogo**, no redactados. Cada uno con el
epígrafe y el importe que lo justifican.

El informe se escribe en `<expediente>\AsistenteIA\IdentificacionRiesgos\` y
**nunca se publica** en ninguna URL: contiene las cifras de un cliente auditado.

---

## Parámetros

| Parámetro | Por defecto | Qué es |
|---|---|---|
| `NumRiesgos` | 10 | cuántos riesgos proponer. **Orientativo**: el rango razonable es 5-10 |

---

## Cinco reglas que gobiernan todo

**1. Los riesgos se eligen del catálogo, nunca se inventan.** El catálogo es la
tabla `RiesgosNIAS` del **máster de Gesia**, que es un `.gs3` distinto del
expediente y **se lee en cada ejecución**: no viaja en el plugin. Y
esto no es una recomendación: `validar_seleccion.py` comprueba que cada id existe
y que el nombre es **literalmente** el del catálogo, y aborta si no. Un nombre
«casi igual» en un papel de trabajo es un nombre distinto.

**2. Dos riesgos van siempre**, digan lo que digan las cifras: **Integridad de las
ventas (fraude)** y **Elusión de controles por la dirección (por sesgo o fraude)**.
Son los que la NIA-ES 240 presume en todo encargo.

**Búscalos por el nombre, nunca por el número.** `IdRiesgo` es la numeración
interna del fichero que estés leyendo, no la identidad del riesgo, y cambia de un
máster a otro. Medido el 04/09/2026:

| Riesgo | Máster 25 (106) | Máster 21 (100) |
|---|---|---|
| Integridad de las ventas (fraude) | 18 | 97 |
| Elusión de controles por la dirección | 27 | 28 |

Y en un expediente la tabla viene renumerada desde 1 con los pocos riesgos que el
auditor ya eligió. Los scripts los resuelven solos por el nombre y **te dicen con
qué número salen en el catálogo que has cargado**: usa ese número y no el de
ningún ejemplo. Esto no es un detalle de estilo. Con el número fijo, una ejecución
real contra el máster 21 metió en el informe «Pérdida de la concesión
administrativa» y «Obsolescencia del producto en catálogo» rotulados como de
inclusión obligatoria por la NIA-ES 240, dejó fuera los dos que sí lo son, y la
validación pasó limpia.

**3. El número es orientativo y no se rellena.** Si las cifras solo justifican
seis riesgos, se proponen seis y el informe lo dice. Meter cuatro más sin epígrafe
ni importe que citar convierte un papel de trabajo en un relleno.

**4. Cada riesgo que no sea de los dos obligatorios cita su evidencia**: epígrafe,
concepto e importe o variación. Si no hay cifra que lo dispare, hay que explicar
por qué se incluye.

**5. Si el expediente no tiene cifras, se para.** Cuando el 90 % o más de los
importes vienen a cero, `analizar_cifras.py` lo dice y no hay análisis posible:
avisa al usuario de que revise que el expediente está cargado. No se identifican
riesgos sobre un expediente vacío.

---

## Dónde están los scripts y el catálogo

```bash
SKILL="<directorio base indicado al cargar el skill>"
TRABAJO="$(pwd)/trabajo" && mkdir -p "$TRABAJO"
```

**`$TMPR` es donde `exportar_consulta` deja los volcados, y depende del
entorno**, porque quien exporta y quien calcula no siempre son la misma
máquina (ver `docs/arquitectura.md`):

```bash
# En la máquina del auditor (Claude Code): MCP y scripts comparten disco.
TMPR="$TEMP/gesia-riesgos"

# En Cowork: el MCP escribe en el equipo y los scripts corren en el sandbox.
# El volcado tiene que caer DENTRO de una carpeta conectada para poder
# subirse con device_stage_files -una ruta de $TEMP no se puede subir-, y en
# una subcarpeta de trabajo de su raíz, nunca en el expediente.
#   exportar_consulta(..., ruta = "<raíz conectada>/_tmp_cowork/catalogo.json")
# device_stage_files, y luego se lee la copia del sandbox:
TMPR="/mnt/user-data/uploads/_tmp_cowork"
```

**Comprueba que los ficheros se leen antes de lanzar los scripts.** Una
exportación que el script no ve obliga a repetirla, y el error no se
parece a lo que es.

El catálogo **no viene con el skill**: se trae del máster al empezar (paso 3) y
queda en `$TRABAJO/riesgos.json` (~240 KB) con su `$TRABAJO/indice.md` (~8 KB).
**Lee el índice, no el JSON**: el índice trae área, id, nombre y las marcas de
significativo y afirmaciones, que es lo que hace falta para elegir. El detalle de
un riesgo lo saca `generar_informe.py` del JSON por su id.

---

## Secuencia

### Paso 1 — Expediente, y preguntar el sector

```
configurar()
contexto_expediente()
```

**Mira la importancia relativa de trabajo (`IR_T`)** que devuelve
`contexto_expediente`. Es lo que decide qué epígrafes se analizan: por debajo de
la materialidad no puede haber una incorrección material, y un riesgo sobre una
partida inmaterial no es un riesgo.

**Si `IR_T` viene a cero, para y pregunta.** Significa que el auditor no la ha
calculado en el módulo de importancia relativa de Gesia. Dos salidas, y las dos
son suyas:

- **calcularla en Gesia** y volver a lanzar el skill, que es lo correcto; o
- **darte una cifra de referencia** en el momento, para seguir ahora.

Si te da una cifra a mano, el informe tiene que decir que la materialidad usada no
sale del expediente. Y si decide seguir sin ninguna, se analiza todo y **también se
dice**: el análisis mezclará partidas materiales con las que no lo son.

**El sector sale del expediente: mira `Actividad` en `DatosAuditoria`.** Es el
campo que el auditor rellena de verdad —en un expediente real dice «Mayorista de
pescado»—; `Sector` y `CNAE` existen pero suelen estar en blanco.

```sql
SELECT Actividad, CNAE, Epigrafe FROM DatosAuditoria
```

**Son esos tres campos y ni uno más.** La ventana de Gesia enseña un cuadro
«Sector», pero **`Sector` no es una columna de `DatosAuditoria`**: si lo pides,
Access lo toma por un parámetro y devuelve «No se han especificado valores para
algunos de los parámetros requeridos», que no se parece en nada al problema real.
Comprobado en cliente el 26/08/2026, después de que la consulta con `Sector`
fallara en tres ejecuciones seguidas.

Usa el primero que traiga algo, en ese orden. **Los tres vacíos es un caso normal
—pasa en expedientes reales—, y entonces se lo preguntas al usuario**; si no lo
sabe, sigue sin filtrar por sector y dilo en el informe.

### Paso 2 — Avisar de lo que va a pasar

Dile al usuario, antes de empezar, que vas a analizar el balance y la cuenta de
resultados de los cinco últimos ejercicios y que **puede tardar**. Es un análisis
sobre cinco ejercicios completos y conviene que sepa que no se ha colgado.

### Paso 3 — Traer el catálogo de riesgos del máster

**El catálogo está en el máster, no en el expediente.** Son dos ficheros `.gs3`
distintos: en el expediente sólo están los riesgos que el auditor ya eligió para
ese encargo —en uno real, 8— y en el máster está el catálogo completo, 106 con su
descripción y sus procedimientos.

**No hay que abrir el máster en Gesia.** El API recibe el fichero como parámetro,
así que sirve cualquier `.gs3` que se le indique mientras el programa tiene
cargado otro. Basta con la ruta:

```
configurar(master_file = "<ruta del máster CON RIESGOS>")
exportar_consulta(entidad = "catalogo_riesgos", ruta = "$TMPR/catalogo.json")
```

Si no tienes la ruta, **pídesela**. Suele estar en una carpeta tipo
`Master Gesia <año>` y el fichero lleva `CON RIESGOS` en el nombre. Sin máster no
hay catálogo y el skill **para**: los riesgos no se inventan.

Luego se normaliza al directorio de trabajo:

```bash
python "$SKILL/scripts/extraer_catalogo.py" \
    --catalogo "$TMPR/catalogo.json" --salida "$TRABAJO" \
    --master "<ruta del máster CON RIESGOS>"
```

`--master` no lee el fichero: solo deja escrito en el catálogo **de dónde sale**,
porque por este camino el script no lo sabe. Sin él, el papel de trabajo no dice
con qué máster se hizo y el aviso de máster desfasado no puede funcionar.

Eso deja `$TRABAJO/riesgos.json` y `$TRABAJO/indice.md`. **Lee las tres últimas
líneas que imprime**: el recuento, el máster del que sale y con qué número
aparecen en él los dos riesgos obligatorios. Si el recuento es muy inferior a
cien, el máster indicado no es el que lleva los riesgos.

Por qué se lee y no viaja empaquetado, que era como estaba hasta el 26/08/2026:

- **Es el know-how de la firma.** Son 170.000 caracteres de descripciones y
  procedimientos redactados. Dentro del paquete viajaba en claro en cada copia
  distribuida; en el máster lo protegen la contraseña del `.gs3` y la licencia de
  Gesia.
- **Y es el catálogo de ESE auditor.** Empaquetado, todos recibirían la copia del
  máster con el que se construyó el plugin, y propondría riesgos que el cliente no
  tiene en su programa, con referencias que no existen en su expediente. Leído del
  máster, propone lo que él tiene, y se actualiza cuando Gesia actualice el máster
  sin republicar nada.

### Paso 4 — Traer las cifras por el MCP

**Tres entidades, tres ficheros, ninguna consulta escrita a mano.**

```
exportar_consulta(entidad = "cifras_balance", ruta = "$TMPR/balance.json")
exportar_consulta(entidad = "cifras_pyg",     ruta = "$TMPR/pyg.json")
exportar_consulta(entidad = "cifras_ratios",  ruta = "$TMPR/ratios.json")
```

Van a fichero y no a tu contexto porque son cientos de filas de contabilidad que
tú no tienes que leer: las lee un script. Medido en cliente, traerlas y volver a
escribirlas fue el mayor coste de toda la ejecución.

Y van **por entidad** por una razón que no es la comodidad: **el signo**. En
Gesia los saldos están en convención debe-haber y cada tabla tiene su regla para
presentarlos —no la misma—:

| | Cómo lo presenta Gesia |
|---|---|
| Balance, activo | tal cual |
| Balance, pasivo | **invertido**: viene acreedor y se lee en positivo |
| PyG, epígrafe | en magnitud: «Gastos de personal» ya dice que es un gasto |
| PyG, subtotal y total | **invertido**: beneficio positivo, pérdida negativa |

Las entidades traen eso ya aplicado y las variaciones ya calculadas, con las
consultas del propio programa. Escribir la consulta a mano es donde se cuela el
error, **y el error no se ve**: los importes salen plausibles y del revés. Pasó:
un informe dio por pérdidas cinco ejercicios de beneficios.

Dos cosas que conviene saber de lo que llega:

- **Las columnas se llaman `Saldo1..5` y `SaldoAud1..5`**, no
  `SaldoAuditoria1..5`. Ese nombre distinto es la señal de que el signo ya está
  puesto: los scripts lo reconocen y **no lo vuelven a aplicar**. Si algún día
  consultas la tabla a pelo, las columnas se llamarán `SaldoAuditoria*` y
  entonces sí se convierten.
- **El signo del balance no es un valor absoluto.** Un patrimonio neto negativo
  queda negativo, y un activo negativo también —en un expediente real el fondo
  de comercio salía a −625,26—. Eso no es un defecto: es la señal que se busca.

Los ejercicios y su orden salen de `Auditorias`: **el `CodigoAuditoria` es un
orden interno, no un año.** La columna del año se llama `Año`, con eñe y con
tilde, así que va entre corchetes. Es esta consulta y no otra —`Ejercicio` no
existe y el error que devuelve Gesia, «No se han especificado valores para algunos
de los parámetros requeridos», no dice cuál es la columna que falta—:

```sql
SELECT CodigoAuditoria, [Año], FechaAuditoria FROM Auditorias ORDER BY CodigoAuditoria
```

De la revisión analítica, cuatro cosas:

- Viene **filtrada por `Relevancia <= 2`**, que es el criterio de Gesia para lo
  que merece mirarse. En un expediente real deja 21 elementos de los activos.
- **`ValorAño1` es el ejercicio que se audita**: el 5 es el más antiguo.
- **Un valor vacío significa que no se ha podido calcular, no cero.**
- **Un mismo ratio puede venir repetido por fase** —`P` planificación, `T`
  trabajo, `I` informe—. `analizar_ra.py` se queda con el de **planificación**,
  que es la fase en la que se identifican los riesgos, y dice cuántos ha
  descartado. La fase vacía es el caso normal y entonces no hay nada que
  deduplicar.

**No abras ninguno de los tres ficheros.** Los leen los scripts.

### Paso 5 — Analizar (puede parar)

```bash
python "$SKILL/scripts/analizar_cifras.py" \
    --balance "$TMPR/balance.json" --pyg "$TMPR/pyg.json" \
    --ir-t <IR_T> --ir-t-origen gesia \
    --ratios "$TMPR/ratios.json" \
    --ejercicios "2025,2024,2023,2022,2021" \
    --salida "$TRABAJO/analisis.json"
```

**`--ir-t-origen` es `gesia` o `manual`, y hay que pasarlo.** Sin él el informe no
puede decir de dónde sale la materialidad, y una IR_T calculada en el módulo de
Gesia y otra dictada de viva voz no acreditan lo mismo. Si la sacaste de
`contexto_expediente`, es `gesia`; si te la dio el usuario en el momento porque el
módulo estaba a cero, es `manual`.

**Y si la entidad no tiene ánimo de lucro, dilo aquí:** añade
`--sin-animo-de-lucro`. La detección automática busca vocabulario de fundación o
asociación en los epígrafes del balance, y **cuando el plan contable es el PGC
estándar no lo encuentra aunque la entidad lo sea**: el balance dice «Fondos
propios» igual que el de una mercantil. Pasó tres veces con el mismo expediente. El
flag existe para no tener que corregir el JSON después, y `--mercantil` fuerza lo
contrario. Si no sabes qué es la entidad, pregúntalo: cambia cómo se llama la
cuenta de resultados en todo el informe.

Salida `1` → el expediente no tiene cifras suficientes: **para y dilo**.

**Lee el `analisis_resumen.md` que deja al lado, no el JSON.** El resumen trae las
variaciones y concentraciones disparadas, que es lo que hace falta para elegir; el
JSON completo es la fuente de auditoría y solo se consulta para un epígrafe
concreto, con un `grep` puntual. Son 1,8 KB frente a 10,6 KB.

**`--ir-t` filtra por materialidad**: solo se analizan los epígrafes cuyo saldo
del ejercicio auditado supera esa cifra en valor absoluto. El **resultado del
ejercicio entra siempre**, tenga el importe que tenga, porque es el que resume el
ejercicio y un resultado casi nulo ya es informativo por sí mismo.

El script dice cuántos epígrafes han quedado por debajo — medido en un expediente
real con 250.000 de materialidad: 38 fuera, y con ellos desapareció una partida
que sin filtro salía como un llamativo +301 % sobre 239.791 €. Si no pasas
`--ir-t`, avisa en mayúsculas de que no se ha aplicado.

Lo que calcula, y lo que hay que leer de su salida:

- **Variaciones** interanuales del 20 % o más, con su sentido en palabras. Cuando
  la base del ejercicio anterior es despreciable **no da porcentaje**: dice
  «aparece» o «base despreciable», porque un «−739.777 %» es correcto y no
  informa de nada.
- **Concentraciones** del 30 % o más sobre el total de su masa.

  **Los desgloses de nivel 3 y 4 entran si superan la IR_T.** Antes se descartaban
  todos —eran demasiados y hacían ruido—, y con ellos se iba alguna partida que
  importaba: un desglose de fondos propios de varios millones no aparecía en
  ninguna parte. Ahora entra el que es material y los demás se cuentan en
  `cobertura` (`desgloses_bajo_materialidad`), así que el recorte se puede ver.

  Ojo con lo que esto **no** hace: que un desglose se analice no significa que
  salte. En un expediente real «Otras aportaciones de socios» son 3,8 M€ —casi
  ocho veces la IR_T— y no dispara nada, porque varía un 1,69 % y pesa el 7,6 %
  del balance. Se analiza y no cruza umbral. **Si una partida así tiene que
  señalarse por su tamaño absoluto y no por moverse, eso es un criterio que hoy no
  existe**: dilo en el informe si lo ves y coméntalo con el auditor.

  **Una concentración con `dentro_de` NO es independiente de su padre, y no se
  suma.** Al abrirse los desgloses materiales salen las dos: el epígrafe y la
  partida que lo domina. El peso del padre **ya incluye** al hijo, así que
  presentarlos por separado invita a sumarlos y la suma no existe. En un
  expediente real salieron «Reservas» al 35,6 % y su desglose «Otras reservas» al
  30,6 %: leídos como cosas distintas dan un 66 % del balance que no es de nadie.

  Al redactar, di **una** concentración y usa el desglose para explicarla —«las
  reservas concentran el 35,6 % del balance, y dentro de ellas las otras reservas
  son la práctica totalidad»—, no dos. El campo trae la cadena completa de
  ancestros, del más próximo al más lejano.

  Y si trae `tambien_en`, es la **misma cifra** con otro nombre: un desglose único
  que repite el importe exacto de su epígrafe. Ahí no hay nada que explicar, solo
  un nombre alternativo.

  **Al redactar, la masa se llama como dice el campo `masa`, y punto.** No la
  deduzcas del epígrafe que contiene la partida: el peso no se mide sobre eso.
  Un ejemplo real de lo que sale si se deduce: los fondos propios pesan el
  62,1 % de `TOTAL PATRIMONIO NETO Y PASIVO`, se escribió «del patrimonio neto»
  y del patrimonio neto son el 99,98 %. Cuatro riesgos de seis salieron con la
  masa mal puesta, con el porcentaje correcto al lado.

  **Y mira `cobertura` antes de dar por hecho que se ha medido todo.** Si trae
  `epigrafes_sin_masa` distinto de cero, a esos epígrafes **no se les ha medido
  el peso** y hay que decirlo en el informe con su motivo. Es lo que pasa hoy en
  la cuenta de resultados: sus epígrafes son de clase `I` y esa clase no tiene
  fila de total, así que no hay denominador. Callarlo hace que la ausencia de
  una sección se lea como «se miró y no había nada», que es lo contrario de lo
  que ha ocurrido.
- **Pérdidas** en 3 o más de los cinco ejercicios.
- **Si la entidad es sin ánimo de lucro**, por el vocabulario de sus cuentas
  —«ingresos de la actividad propia», «fondo social», «dotación fundacional»— y
  no por el CNAE. Si lo es, el informe habla de **cuenta de resultados** y no de
  pérdidas y ganancias, y el script ya te da la denominación que toca usar.

### Paso 5 bis — Analizar la revisión analítica

```bash
python "$SKILL/scripts/analizar_ra.py" \
    --ra "$TMPR/ratios.json" --ejercicios "2025,2024,2023,2022,2021" \
    --ir-t 200000 \
    --salida "$TRABAJO/analisis_ra.json"
```

**La `--ir-t` es la del expediente**, la misma del paso 1. Sirve para un solo
propósito: un ratio que es un **importe en euros** (`TipoValor = 1`) y cuya
magnitud queda por debajo de la importancia relativa no genera señal. Salió de un
informe real, donde «Exigible a Largo 130,02 — a la baja 5 años» figuraba como
hallazgo: son 130 € de pasivo no corriente y ocupaban el sitio de algo que sí
importa. Los ratios propiamente dichos (`TipoValor = 2`) no se filtran nunca:
comparar un endeudamiento de 0,6091 con una cifra en euros no significa nada.
**Lo descartado se declara** con nombre e importe, y va al informe.

Mide comportamientos sobre cada ratio y **no interpreta lo que significan**: no
sabe si un endeudamiento de 0,8 es bueno o malo. Lo que detecta:

| Señal | Qué es |
|---|---|
| tendencia | el ratio se mueve en la misma dirección 3 o más años |
| salto | el movimiento del último ejercicio es varias veces el habitual de ese ratio |
| negativo persistente | negativo en todos los ejercicios con valor |
| cambio de signo | el ejercicio auditado cambia de signo respecto al anterior |

El salto se mide **contra el propio historial del ratio**, no con un porcentaje
fijo: un 0,2 en un margen es enorme y en un periodo medio de cobro no es nada.

**Esta suele ser la fuente que más riesgos justifica**, y a menudo los más graves.
Medido en un expediente real: el fondo de maniobra cayendo tres años y pasando a
negativo, la solvencia a corto por debajo de la unidad y el cash flow negativo los
cinco ejercicios — un cuadro de empresa en funcionamiento que las variaciones de
epígrafes no enseñaban.

### Paso 6 — Elegir los riesgos

**Lee el `analisis_ra_resumen.md`, nunca el JSON completo.** El de la revisión
analítica son 98 KB y 127 elementos: leerlo entero se trunca a mitad y la mayor
parte son ratios sin señal que no vas a usar. El resumen son **2,5 KB** con los
ratios que sí tienen señal, ya ordenados por relevancia. Al JSON se va solo para el
detalle de un `CodigoElementoRA` que vayas a citar, con un `grep` de ese código.

Lee `$TRABAJO/indice.md` y elige, cruzando **las dos fuentes** —lo que
dispararon los umbrales de las cifras y lo que señaló la revisión analítica— con
las áreas del catálogo. **Esta es la parte de criterio y es tuya**: no hay ningún
mapa epígrafe→área en el expediente, y el script no lo inventa a propósito.

Escribe `$TRABAJO/seleccion.json`:

Los `id` de este ejemplo son los del máster 25. **Coge los tuyos del índice y de
lo que imprime `extraer_catalogo.py`**, que no tienen por qué coincidir:

```json
{"riesgos": [
  {"id": 18, "nombre": "Integridad de las ventas (fraude)",
   "justificacion": "Riesgo de inclusión obligatoria conforme a la NIA-ES 240."},
  {"id": 33, "nombre": "Relevancia de cuentas a cobrar (Clientes y Deudores)",
   "justificacion": "Los deudores comerciales aumentan un 329,9 %.",
   "evidencia": {"epigrafe": "A.B.3",
                 "concepto": "Deudores comerciales y otras cuentas a cobrar",
                 "importe": 2166319.0, "variacion": 3.299}}
]}
```

La evidencia puede venir de cualquiera de las dos fuentes. Un ratio vale igual
que un epígrafe:

```json
{"id": 15, "justificacion": "El fondo de maniobra pasa a negativo.",
 "evidencia": {"ratio": "AFC01", "elemento": "Fondo de Maniobra",
               "valor": -3163962.34,
               "señal": "a la baja 3 años, cambia de signo"}}
```

**Para decidir si un riesgo encaja hace falta su descripción, no su nombre.** El
índice solo trae el nombre; en vez de abrir `riesgos.json` —240 KB— pide de una vez
las fichas de los candidatos:

```bash
python "$SKILL/scripts/mostrar_riesgos.py" --catalogo "$TRABAJO/riesgos.json"     --ids 18,27,33,80
```

(Esos ids son de un máster concreto: pon los del índice que acabas de generar.)

Saca área, afirmaciones, calificación, referencia y descripción completa de cada
uno, y avisa si algún id no existe — mejor verlo aquí que cuando el validador
aborte. Con `--area H` los saca todos los de un área y con `--procedimientos`
añade los procedimientos previstos.

El `nombre` tiene que ser el del catálogo, carácter por carácter. Si no lo pones,
se usa el del catálogo; si lo pones distinto, el validador aborta.

### Paso 7 — Validar la selección (puede abortar)

```bash
python "$SKILL/scripts/validar_seleccion.py" \
    --seleccion "$TRABAJO/seleccion.json" \
    --analisis "$TRABAJO/analisis.json" \
    --catalogo "$TRABAJO/riesgos.json" \
    --ejercicio 2025
```

**`--catalogo` es obligatorio y sin él el script aborta**: el catálogo ya no viaja
dentro del plugin, sale del máster. Es el mismo `riesgos.json` del paso 2.

`--ejercicio` es el año auditado, el que sacaste de `Auditorias`. Solo sirve para
avisar de que el catálogo es de un máster de otro año, que es de las cosas que no
se ven leyendo el informe terminado.

Al final imprime, siempre, **de qué máster sale el catálogo y con qué número
aparecen en él los dos obligatorios**. Es la línea que hay que mirar si algo no
cuadra.

Salida `2` → **para**, no se genera informe. Salida `1` son avisos y hay que
contarlos: el más importante es un riesgo elegido sin evidencia cuantitativa.

### Paso 7 bis — Escribir el análisis

Las tablas dicen **qué** pasa; esto dice **qué significa**. Sin ello el informe
salta de las cifras a los riesgos y quien lo revise no ve el razonamiento que
llevó de unas a otros.

Escribe `$TRABAJO/narrativa.json` con cuatro textos, separando párrafos con una
línea en blanco:

```json
{"balance": "…", "resultados": "…", "revision_analitica": "…", "resumen": "…"}
```

| Clave | Qué va |
|---|---|
| `balance` | análisis financiero y contable del balance: qué se mueve, en qué dirección y qué relación tienen unas partidas con otras |
| `resultados` | lo mismo sobre la cuenta de resultados. Usa la denominación que te dio `analizar_cifras.py`: si la entidad es sin ánimo de lucro, **cuenta de resultados**, no PyG |
| `revision_analitica` | qué dicen los ratios, y si confirman o contradicen lo anterior |
| `resumen` | el cierre: la situación del encargo y por qué los riesgos elegidos son esos. Se escribe **después** de elegirlos, para poder hablar de ellos |

Cíñete a las cifras que salieron del análisis. Este texto va en un papel de trabajo
firmado: nada de adjetivos que no sostenga un número.

### Paso 8 — El informe

```bash
python "$SKILL/scripts/generar_informe.py" \
    --analisis "$TRABAJO/analisis.json" --analisis-ra "$TRABAJO/analisis_ra.json" \
    --seleccion "$TRABAJO/seleccion.json" --narrativa "$TRABAJO/narrativa.json" \
    --cliente "<razón social>" --cierre "<31/12/25>" --sector "<sector>" \
    --generado "<AAAA-MM-DD>" --ref "<referencia>" \
    --catalogo "$TRABAJO/riesgos.json" \
    --salida "<destino>/Riesgos <CLIENTE> <EJERCICIO>.docx"
```

<!-- solo-cowork:alt=**El destino es la carpeta del expediente**, directamente: `<expediente>/AsistenteIA/IdentificacionRiesgos/`. -->**El destino depende del entorno.** En la máquina del auditor, directamente
`<expediente>/AsistenteIA/IdentificacionRiesgos/`. En Cowork el script escribe
en el sandbox, así que va a `$TRABAJO` y luego hay que bajarlo: `SendUserFile`
devuelve un `file_uuid` y `device_commit_files` lo escribe en
`<expediente>/AsistenteIA/IdentificacionRiesgos/`. Sin ese paso el informe no
llega al expediente, aunque el script diga que lo ha escrito.<!-- /solo-cowork -->

`--generado` lo pones tú: nada aquí lee el reloj. **`--catalogo` es obligatorio**,
igual que en el paso anterior.

**`--ref` es obligatoria y no tiene valor por defecto a propósito**: escribir una
referencia inventada mete en el expediente un código que no existe en el índice de
Gesia.

**Búscala primero en el expediente, y pregunta solo si no sale una y solo una.**
El papel suele existir ya, y preguntar por algo que está a una consulta es hacerle
perder el tiempo al auditor:

```sql
SELECT CodigoReferencia, Referencia FROM Referencias
WHERE Referencia LIKE '%valoraci%n de riesgos%'
```

El `%` de en medio se come la tilde, así que no depende de cómo esté escrita. En
los dos expedientes medidos el 04/09/2026 devuelve una sola fila,
`Identificación y valoración de riesgos`.

- **Una fila** → úsala, y dile al usuario cuál has cogido.
- **Ninguna, o más de una** → pregúntale, enseñándole lo que has encontrado.

**No fijes el código que salga.** `CodigoReferencia` no es estable entre encargos:
el mismo código apunta a papeles distintos en expedientes distintos. Lo estable es
el texto de `Referencia`, y por eso se busca por él.

La línea **Fuente** se compone sola con lo que de verdad se ha usado: «Balance de
situación, Cuenta de pérdidas y ganancias y módulo de Revisión analítica
plurianuales disponibles en Gesia». Si no pasas `--analisis-ra`, no menciona el
módulo; y si la entidad es sin ánimo de lucro, dice **Cuenta de resultados**. Solo
usa `--fuente` si quieres escribirla a mano.

La cabecera del informe lleva **los mismos campos que el papel de continuidad de
saldos** —cliente, «AUDITORIA A <fecha>», título, fuente, y el bloque
`REF. P.T.` / `Realizado` / `Verificado`, estos dos en blanco— para que los
papeles del expediente se lean igual. La fuente se cambia con `--fuente`.

El informe lleva las cifras en tablas y un gráfico de la evolución del resultado.
Si `matplotlib` no está disponible, sale sin gráfico y con las mismas cifras en
tabla. El PNG del gráfico se incrusta en el `.docx` y el script lo borra solo.

**Si inspeccionas el `.docx` por dentro, lee siempre en UTF-8.** El título de
`docProps/core.xml` sale bien; el 04/09/2026 se dio por corrupto porque se leyó con
la codificación de la consola, que enseña `Identificaci?n`. Comprobado a nivel de
byte: son `c3 b3`, que es UTF-8 correcto. No hay nada que arreglar ahí.

### Paso 9 — Entregar

Di dónde ha quedado, **cuántos riesgos** lleva y de qué áreas. Si has propuesto
menos de los pedidos, di por qué. Recuérdale que el informe es una propuesta y que
la valoración del riesgo y la firma son suyas.

**Los temporales.** Los volcados de `exportar_consulta` los borra
`limpiar_exportaciones()`, y esa es la vía: funciona igual en local y en Cowork
—lo borra el MCP, que corre en la máquina del usuario— y no hay que decirle qué
ficheros, porque borra los que él escribió. Si alguno no se deja borrar, lo dice
con su ruta.

El directorio de trabajo va aparte:

```bash
rm -rf "$TRABAJO"
```

**Y cuenta con que en Cowork no te dejen**: el puente no tiene permiso de borrado
en el equipo del usuario (comprobado el 25/08/2026). Por eso los volcados van a la
carpeta temporal del sistema y **nunca a `AsistenteIA`**, donde solo debe quedar
el entregable.

Si el borrado del directorio de trabajo falla, dos cosas, en este orden:

1. **Si el entorno ofrece una herramienta para pedir permiso de borrado**<!-- solo-cowork --> —en
   Cowork suele llamarse algo como `device_request_delete_permission`—<!-- /solo-cowork -->, pídelo
   **una vez**. Es mejor que informar y no hacer nada, y si el usuario lo concede
   queda resuelto para el resto de la sesión.
2. **Si no la hay o la deniega, di las rutas exactas** de lo que queda. Sin
   adornos: son datos de su cliente y tiene que poder borrarlos él.

Lo que no vale es dejarlo en un «puede que queden temporales» sin decir dónde.


---

## Lo que este skill no hace

- **No escribe en el expediente.** El MCP solo lee; los riesgos se pasan a Gesia a
  mano.
- **No valora el riesgo**: la valoración que muestra es la que el máster trae por
  defecto para cada riesgo, no una valoración de este encargo.
- **No lee el diario ni las cuentas anuales en PDF.** Solo el balance, la cuenta
  de resultados y los ratios del expediente.
- **No usa el campo `Clasificacion`** del catálogo (I/R/A): no se sabe qué
  significa y no se muestra nada que no se pueda explicar.
- **No detecta el sector.** Lo pregunta.

## Degradación

| Situación | Qué sale |
|---|---|
| 90 % o más de los importes a cero | **para.** No hay cifras que analizar |
| Sector desconocido | sigue sin filtrar y lo dice en el informe |
| No se localiza la fila de resultado | sigue, y omite el análisis de pérdidas diciéndolo |
| Base del ejercicio anterior despreciable | informa «aparece» o «base despreciable», sin porcentaje |
| Un id que no está en el catálogo | **aborta.** No se genera el informe |
| Falta uno de los dos riesgos obligatorios | **aborta** |
| Los dos obligatorios no se resuelven por nombre en el catálogo | **aborta.** Suele ser un máster sin riesgos |
| El máster es de otro año que el ejercicio auditado | avisa, y el aviso consta en el informe |
| `matplotlib` no disponible | informe sin gráfico, cifras en tabla |

## Arnés

```bash
python "$SKILL/scripts/probar_riesgos.py"
python "$SKILL/scripts/probar_riesgos.py" --catalogo "$TRABAJO/riesgos.json"
```

No necesita Gesia, ni red, ni un máster en disco: lleva dentro las dos
numeraciones medidas y comprueba que los dos riesgos obligatorios se resuelven por
nombre en cada una. Con `--catalogo` comprueba además uno de verdad, y es la forma
rápida de ver con qué número salen los obligatorios en el máster del cliente.

Se escribió el 04/09/2026 con el fallo delante, y muerde: devolviendo los ids fijos
que había antes, nueve de sus comprobaciones fallan.
