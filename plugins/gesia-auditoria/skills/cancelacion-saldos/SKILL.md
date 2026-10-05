---
name: cancelacion-saldos-gesia
description: >
  Empareja los saldos positivos y negativos del mayor de una o varias cuentas del diario
  de un expediente de Gesia —típicamente facturas contra pagos o cobros— y asigna un
  ÍNDICE de cancelación a cada grupo que suma cero. Respeta el punteo que ya trae el
  diario en el campo Indice y empareja lo que quedó sin puntear. Deja el papel en Excel,
  una hoja por cuenta: gris lo punteado en contabilidad, amarillo lo que compone el saldo
  vivo. Úsalo si piden cancelar, conciliar o cuadrar los saldos de una cuenta, emparejar
  facturas con pagos o cobros, ver qué queda pendiente o completar el punteo, o dicen
  "cancela los saldos de esta cuenta" o "casa los cobros con las facturas". NO es la
  continuidad de saldos de apertura (eso compara ejercicios) ni el cuadro de mando del
  diario. Requiere el servidor API de Gesia arrancado y un expediente con diario
  importado.
---

# Cancelación de saldos (Gesia)

Dentro de una cuenta —normalmente clientes o proveedores— cada factura
suele tener su pago o su cobro en otro apunte distinto. El objetivo es
encontrar qué apuntes se cancelan entre sí, para que lo que quede sin
cancelar sea el saldo pendiente de verdad, no una cifra agregada que
esconde facturas ya liquidadas.

Los ficheros se escriben en `<expediente>\AsistenteIA\CancelacionSaldos\`
y **nunca se publican** en ninguna URL: son la contabilidad de un cliente
auditado. **`<expediente>` es la carpeta del `gs3_file` que devuelve `configurar()`**,
no una ruta escrita a mano ni recordada de otra sesión: el 10/09/2026 apareció en la
carpeta de un expediente el papel de otro.

---

## El punteo previo del diario

Muchos `.smn` traen la columna `Indice`: el punteo hecho en la contabilidad
o en Gesia, **numerado por cuenta** (la clave es CUENTA + Indice), que suele
recoger el pareo directo. Es una opción de importación del diario: **falta
con normalidad**, y su ausencia no es un error.

Cuando el extracto la trae, el skill la **respeta y la completa**:

- Los apuntes con índice previo > 0 son grupos ya cancelados: no entran al
  emparejamiento y conservan su número tal cual.
- Los índices que asigna el skill arrancan por encima del máximo previo de
  cada cuenta, así el papel resultante es una única numeración coherente.
- Cada grupo previo se verifica igualmente (¿suma 0?). Si alguno no suma,
  **se avisa pero se respeta**: la contabilidad del cliente manda y lo
  juzga el auditor. El papel lo lista como descuadre del punteo contable.

Si la columna no existe, el emparejamiento parte de cero, como siempre.

## Cómo funciona el emparejamiento

Se aplica cuenta por cuenta **sobre los apuntes sin puntear**, en este
orden, y en cuanto uno resuelve toda la cuenta se para ahí:

0. **Grupos por NÚMERO DE DOCUMENTO** (`NN_Factura` o, si el diario no trae esa
   columna con ningún nombre, el número que el MCP deriva del concepto en local:
   `NumeroEnConcepto`), y **solo si suman 0**.
   Es la clave con la que el auditor empareja a mano, y llega donde ningún
   criterio de importes puede: una factura de 2.743,70 muerta por tres pagos de
   914,48 / 914,48 / 914,74 a 30, 60 y 90 días. Los pagos no se parecen a la
   factura ni entre sí, y la combinatoria del punto 4 tampoco alcanza —no por su
   tope, sino porque entre 135 apuntes sueltos son más de 7.000 millones de
   subconjuntos—. Agrupar por documento no busca: **particiona**.

0b. **La apertura contra los pagos de facturas que no están en el ejercicio.**
   Después del paso 0, un apunte que sigue pendiente, que lleva número de
   factura, cuyo grupo de ese número no cierra, y que va en sentido contrario a
   la apertura, es un **pago cuya factura no está aquí**; y si no está, está
   dentro de la apertura. Si la suma no cierra, se admite **un único apunte más,
   sin número, cuyo importe sea exactamente el hueco** —la regularización de
   cierre—. Medido en tres cuentas reales: cierra al céntimo.

1. **Si todo lo pendiente suma 0**, un único índice para esos apuntes.
2. **Si el total pendiente coincide con el saldo del último apunte** en
   orden cronológico, se cancela todo menos ese último —que queda como
   saldo pendiente—.
2b. **La apertura primero.** Matar el saldo de apertura es el objetivo del
   procedimiento, así que la apertura busca sus pagos **antes que nadie**:
   se acumulan los apuntes de signo contrario en orden hasta dar su importe
   exacto, y si así no cuadra se prueban subconjuntos de los primeros. Si
   ningún conjunto da el importe exacto, **no se fuerza nada**: la apertura
   se queda pendiente y el auditor la ve.

   Se reconoce por estructura y no por el texto del concepto: es del **1 de
   enero** —no puede haber saldo anterior a eso— y es el apunte más antiguo
   de la cuenta. Tampoco se presupone el signo: en una cuenta acreedora es
   un abono que cancelan pagos, y en una deudora al revés.

   Por qué hace falta un paso propio: sin él la apertura era un apunte más,
   el pareo directo del punto 3 se llevaba sus pagos y la apertura se
   quedaba viva. Medido el 30/08/2026 sobre las cuentas 40 y 41 de un
   expediente real: **74 aperturas sin cancelar por 169.332 €, y con este
   paso 67 por 49.637 €** —un 71 % menos—, sin ningún grupo descuadrado. Y
   la agrupación no solo cuadra: en las cuentas revisadas, **todos** los
   pagos que cancelan la apertura llevan en el concepto facturas del
   ejercicio anterior, que es lo que tenían que ser. El algoritmo no lee ese
   texto, así que es una confirmación independiente.
3. **Pareo directo**: apuntes de igual importe absoluto y signo contrario
   se emparejan uno a uno, sin mirar la fecha. Es el caso más común —cada
   "Ntra Fra: N" con su "Fac. Nº N"— y resuelve la mayoría de los grupos.
4. **Lo que queda** se intenta cancelar en orden cronológico, acumulando
   el saldo hasta que dé cero (un tramo continuo en el tiempo que sume
   cero se cierra como grupo); y lo que sigue sin cancelar se intenta con
   combinaciones acotadas —hasta 6 apuntes a la vez, entre un máximo de 22
   sin cancelar— buscando subconjuntos, no necesariamente contiguos en
   fecha, que sumen cero.

**La regla que gobierna los pasos 0 y 0b: el número PROPONE y la suma DECIDE.**
Un grupo por documento se acepta solo si sus apuntes suman cero. Si el campo
viniera sucio, repetido entre ejercicios o significase otra cosa, ningún grupo
cerraría y el resultado sería idéntico a no haberlo mirado. El campo nunca es
autoridad: solo dice por dónde empezar a sumar. Por eso usarlo no tiene riesgo, y
por eso `reconocer.py` mide **sobre cada cliente** cuánto aporta en vez de darlo
por bueno en general.

**No se usa el texto de CONCEPTO para decidir qué apuntes van juntos.**
Fue una posibilidad planteada en el encargo original que dio pie a este
skill, pero es un emparejamiento difuso sin regla objetiva de cuándo
aceptar una coincidencia de texto, y el criterio numérico —fecha e
importe— ya resolvió sin ambigüedad el caso real usado para calibrar esto
(una cuenta de clientes del expediente de calibración: 46 de 46 grupos
correctos, incluida una apertura que solo cancela agrupando tres pagos del
mismo día). Del concepto solo se usan **el número y la fecha que el MCP extrae en local** —y el
número, solo si el grupo suma cero—; el texto se conserva en el informe para que el
auditor lo lea, si decidió que viajara, no para que el algoritmo decida por él. **Los `NN_Cta*` tampoco se usan** para agrupar cuentas: ahí habría que *fiarse*
de ellos, y para eso están `Left(CUENTA, n)` y el nivel de auditoría.

`NN_Factura` es el caso distinto, y conviene saber por qué: **su semántica no está
garantizada entre expedientes** —comprobado en el de calibración, donde la factura
y su pago llevan números distintos, y ahí el paso 0 no habría cerrado nada—. Lo que
lo hace utilizable no es fiarse de él, es que **un grupo se acepta solo si suma
cero**: donde el campo no significa lo que parece, no cancela y no estorba. En el
expediente que motivó el paso, en cambio, pasó de 27 grupos a 50 en una sola cuenta.

La verificación es estructural, no una comprobación externa: **para cada
índice asignado por el skill, la suma de SALDO de sus apuntes es
exactamente 0** por cómo se construyen los grupos, y **la suma de los
apuntes en ÍNDICE 0 coincide con el total de la cuenta menos el descuadre
que traiga el punteo previo** (0 si no hay punteo o está bien hecho). Si
`generar_papel.py` marca una cuenta como REVISAR, hay un error de
programación, no un caso límite de los datos — avisa antes de entregar
nada. El descuadre del punteo previo NO es un REVISAR: es un aviso, y del
cliente.

---

## Dónde están los scripts

Al cargarse, el runtime indica el **directorio base del skill**. Las rutas
`scripts/…` son relativas a él, no al directorio de trabajo.

```bash
SKILL="<directorio base indicado al cargar el skill>"
TRABAJO="$(pwd)/trabajo" && mkdir -p "$TRABAJO"
```

`reconocer.py` (pasada en seco antes de nada), `verificar_contrato.py`,
`generar_papel.py` y `ejecutar_cancelacion.py`, que encadena los dos ultimos. Mas
`probar_cancelacion.py`, el arnes.

---

## Secuencia

### Paso 1 — Expediente y cuenta(s) a procesar

```
configurar(perfil = "cancelacion-saldos")   # primero: lista blanca y nombres tokenizados
contexto_expediente()
```

**Lo primero, antes de leer nada: `configurar(perfil = "cancelacion-saldos")`.** Con el perfil, el
MCP retira del extracto las columnas que este skill no necesita y **tokeniza los nombres de
terceros** en todo lo que devuelve: verás `PROV 40000012` o `CLI 43000007` donde iría la razón
social. El nombre no sale del equipo del auditor —ni al contenedor ni a este chat—; el papel lo
recupera al final con `rehidratar`. Trabaja y habla **por cuenta y por token**: «la apertura de
PROV 40001013 no cierra». **Nunca preguntes al auditor a quién corresponde un token ni lo
adivines** por el concepto o por los importes: él lo lee en el papel. Si `configurar()` dice
`nombres_terceros: en claro — forzado por el auditor`, es que lo ha apagado él; no lo
vuelvas a encender tú.

Si falta `gs3_file`, pide la ruta. Si el servidor API no responde, dile que
lo arranque en *Herramientas > Gesia - Cuadro de mando > Arrancar servidor
API*. Si el expediente no tiene diario importado, **para**: sin diario no
hay apuntes que cancelar.

**Pregunta qué cuenta o grupo de cuentas quiere procesar**: una cuenta
concreta, un grupo (43 clientes, 40 proveedores...), varias cuentas sueltas, o **las N
con más apuntes de un grupo**. No asumas "todo el diario" — con miles de cuentas el
papel sería enorme y la mayoría no tiene nada que cancelar.

Para el «top N por apuntes», **el filtro de saldo vivo va antes del ranking**, no después:
si se cogen las cinco más grandes y luego se filtra, una que cierre a cero deja el papel con
cuatro hojas tras haber anunciado cinco (pasó el 10/09/2026). La consulta hecha:

```
consultar_diario(sql = "SELECT TOP 5 CUENTA, Count(*) AS N FROM Diario
  WHERE CUENTA LIKE '400%'
  GROUP BY CUENTA HAVING Abs(Sum(SALDO)) > 0.005
  ORDER BY Count(*) DESC, CUENTA")
```

Con esas cuentas se escribe el `SELECT` del paso 2 con `CUENTA IN ('…','…')`, y el
recuento que se le dice al auditor es el de esas cuentas.

**«Salvo que ya lo haya dicho» significa en esta petición, no en cualquier
momento de la conversación.** Un alcance mencionado antes y a otro
propósito —«el área de clientes», dicho al hablar de otra cosa— no es una
instrucción para este skill: heredarlo es cómodo y acaba procesando
cientos de cuentas que nadie pidió. Pasó el 27/08/2026: se procesó el
grupo 43 completo, 261 cuentas, por un «área de clientes» de un turno
anterior.

**Y antes de procesar, cuenta cuántas cuentas caen y confírmalo si son
muchas.** Sale de una consulta y no cuesta nada:

```
consultar_diario(sql = "SELECT Count(*) AS Cuentas, Sum(N) AS Apuntes FROM
  (SELECT CUENTA, Count(*) AS N FROM Diario WHERE CUENTA LIKE '43%'
    GROUP BY CUENTA HAVING Abs(Sum(SALDO)) > 0.005)")
```

**Las dos cifras salen de la misma consulta y con el mismo `HAVING`, y son las que se
le dicen al auditor.** En la prueba en frío del 10/09/2026 se le dijeron 1.346 apuntes
—los de todo el grupo— y el papel llevó 967: los de las cuentas con saldo vivo. **El
`HAVING` no es opcional: es el mismo filtro que la exportación del paso 2**,
que deja fuera las cuentas que ya cierran a cero. Sin él, el número que se le da
al auditor no es el de hojas que va a recibir. Medido el 08/09/2026 en un
expediente real: el grupo 43 tiene **419 cuentas** y solo **71** con saldo vivo,
así que la pregunta iba con una cifra seis veces mayor que el papel.

Por encima de **20 cuentas**, di cuántas son y espera confirmación —el
papel llevará una hoja por cada una, y el auditor tiene derecho a saber
que va a recibir doscientas antes de que se generen—. Por debajo, sigue sin
preguntar: ahí el trámite molesta más de lo que protege.

**Y una pregunta más, siempre, antes de exportar nada.** El `CONCEPTO` de cada
apunte es texto libre —nombres, matrículas, referencias— que el auditor lee en el
papel. **Lo que el skill necesita de él no depende de la respuesta**: el número de
factura y la fecha del documento que lleva escritos los extrae el MCP en local y
viajan siempre en el extracto como `NumeroEnConcepto` y `FechaEnConcepto`, aunque el
texto no viaje. Medido el 10/09/2026 en seis diarios reales: donde no hay `NN_Factura`
—cuatro de siete expedientes— ese número cierra el 78–90 % de los grupos que forma. Lo
único que se decide es si el **texto** sale del equipo, y eso lo decide el auditor, con
esta frase y ninguna más:

> *¿Quieres el concepto de cada apunte en el papel de trabajo? Ese texto libre —que
> puede llevar nombres, matrículas o referencias— sale de tu equipo con el extracto: un
> riesgo de confidencialidad pequeño, pero real. El número de factura y la fecha que
> lleva escritos se usan igual, viaje o no.*

Si dice que sí: `configurar(concepto = true)` **antes** de exportar, y el fichero llevará
`CONCEPTO` además de las dos derivadas —con los DNI, CIF, IBAN, matrículas, teléfonos y
correos que hubiera en el texto **enmascarados** como `[DNI]`, `[CIF]`…: eso lo hace el MCP
siempre, y no hay que pedirlo ni intentar recuperarlos—. Si dice que no: no hay nada que configurar; el
MCP ya retiene el texto por defecto. Sin respuesta, **no se exporta**. No hay tercera
opción ni valor por defecto: es una decisión de confidencialidad y es suya.

### Paso 2 — Exportar el extracto del diario

**Primero mira qué columnas tiene este diario** — cambian de un `.smn` a
otro y no se asume ninguna opcional—, y hazlo **sin traer ningún apunte**:

```
columnas(fuente = "diario")
```

Devuelve nombre y tipo de cada columna y ninguna fila. **No uses `SELECT TOP 1 *`
para esto**: trae un apunte real del cliente —nombre, concepto, importe— al contexto,
y el 10/09/2026 así entraron tres en una ejecución, incluida una apertura de seis
cifras.

Con eso decides el SELECT. Tres columnas opcionales, y las tres **se incluyen si
existen**; si no, no se piden — pedir una que no está da el error de Access
*«Pocos parámetros»*, que no dice cuál falta:

- **`Indice`**, el punteo previo de la contabilidad. El skill lo respeta y lo
  completa.
- **La columna del número de documento**, que **no tiene un nombre fijo**:
  `NN_Factura`, `NN_NumFactura`, `Factura`, `Documento`… Pide **todas** las que
  `columnas()` enseñe con «factura» o «documento» en el nombre —un diario puede traer
  `NN_Factura` y `NN_Documento` a la vez, pasó el 10/09/2026—: **no elijas tú**. El script
  puntúa cada una por los grupos que cierra a cero, se queda con la que más cierra, y
  el reconocimiento y la hoja de criterios dicen cuál y por cuánto. **Esa puntuación es
  del extracto de este alcance, no del diario**: la misma columna estaba llena en el
  grupo 400 y vacía en el 43 del mismo `.smn`. No la heredes de una ejecución anterior
  sobre otro grupo, aunque sea el mismo expediente y el mismo día. Es la clave con la que el auditor
  empareja a mano, y con ella el skill cancela lo que ningún criterio de importes
  alcanza: una factura pagada en tres plazos desiguales. **Un grupo por número solo
  se acepta si suma cero**, así que si el campo viniera sucio no cambia nada. Si no
  existe con ningún nombre, no pasa nada: el MCP deriva `NumeroEnConcepto` y el skill
  lo usa en su lugar.
- **`CONCEPTO`**, que casi siempre está. **Pídelo siempre que exista, diga lo que
  diga el auditor**: el MCP no lo exporta como texto —salvo que se haya autorizado en
  el paso 1— sino convertido en `NumeroEnConcepto` y `FechaEnConcepto`, que es lo que
  el skill necesita. Si no lo pides, el papel se queda sin fecha de documento y los
  hallazgos por fecha no se evalúan.

**Los demás `NN_*` no se piden nunca**, y `NN_Factura` no es una excepción a esa
regla sino a su motivo: los `NN_Cta*` se descartan porque habría que *fiarse* de
ellos para agrupar cuentas, y aquí no se fía nadie — el número propone y la
aritmética decide.

**Se exporta a fichero, no se trae al contexto.** `exportar_consulta`
ejecuta la consulta y la deja en disco; solo hace falta el recuento de
filas que devuelve, no las filas.

**Deja fuera las cuentas cuyo saldo total es cero.** Una cuenta que ya cierra a
cero no tiene nada pendiente que localizar: entra en el papel como una hoja más
que el auditor tiene que abrir para no encontrar nada. Se filtra en el propio
SQL, con una subconsulta por `CUENTA`:

```
exportar_consulta(
  fuente = "diario",
  sql = "SELECT FECHA, ASIENTO, CUENTA, NOMBRE, CONCEPTO, DEBE, HABER, SALDO
         FROM Diario
         WHERE CUENTA IN (SELECT CUENTA FROM Diario
                           WHERE CUENTA LIKE '43%'
                           GROUP BY CUENTA HAVING Abs(Sum(SALDO)) > 0.005)
         ORDER BY CUENTA, FECHA",
  ruta = "<TEMP>/gesia-cancelacion/extracto.csv")
```

**Ese SELECT es el mínimo seguro: a él se le AÑADEN `Indice` y la columna del número
de documento, una a una y solo si `columnas()` las ha mostrado.** `CONCEPTO` va dentro
del ejemplo porque casi siempre existe; si `columnas()` no lo enseña, quítalo. Las otras
van fuera del ejemplo
a propósito, porque el ejemplo es lo que se copia: pedir una columna que no está
aborta la consulta con el «Pocos parámetros» de Access, que no dice cuál falta. Pasó
el 08/09/2026 en este mismo diario, que trae `NN_Factura` pero no `Indice`.

El umbral de `0,005` es medio céntimo, el mismo `TOL` que usa
`lib_cancelacion.py`: por debajo de eso el saldo es residuo de redondeo, no un
saldo vivo. Medido en un expediente real: de todo el grupo 43 quedaron **17
cuentas** con saldo, y el resto habrían sido hojas vacías.

El `WHERE` lo decides según lo que haya pedido el usuario en el paso 1.
`SALDO` ya viene calculado por Gesia como DEBE-HABER de cada apunte —no es
un saldo acumulado, pese al nombre—; si por lo que sea no la pides, el
script la deriva de DEBE y HABER igual.

**El fichero va a la carpeta temporal del sistema, nunca al expediente**:
es contabilidad de trabajo, no un papel para archivar.

**Y siempre a esa misma ruta**, `extracto.csv`, aunque se procesen varios
grupos de cuentas en la misma sesión: nada de `extracto_clientes.csv` ni
variantes por ejecución. `exportar_consulta` sobrescribe avisando, así que
el residuo queda en un fichero en vez de acumularse.

<!-- solo-cowork:export -->
#### En Cowork: subir el extracto antes de seguir (en local no aplica)

**Quien exporta y quien calcula no son la misma máquina, y esto se pasa por
alto con facilidad.** El MCP corre en el equipo del auditor y escribe ahí;
los scripts, en Cowork, corren en el contenedor de la nube y **no ven un
fichero que esté en el `$TEMP` de ese equipo**. Sin este paso, la
exportación es inservible para el siguiente y hay que repetirla — medido en
una ejecución real el 27/08/2026.

**`device_stage_files` solo puede subir ficheros que estén dentro de una
carpeta conectada a la sesión.** Una ruta del `$TEMP` de Windows no se
puede subir, y ahí se pierde la exportación. Así que en Cowork **el paso 2
exporta dentro de la carpeta conectada**, en una subcarpeta de trabajo de
su raíz:

```
exportar_consulta(..., ruta = "<raíz de la carpeta conectada>/_tmp_cowork/extracto.csv")
```

Y **nunca en `AsistenteIA`**: ahí van los papeles que el auditor archiva, y un
CSV con la contabilidad del cliente al lado del papel firmado es contabilidad
ajena en la carpeta que se archiva. `device_list_dir` sirve para ver qué hay
conectado si no lo tienes claro.

**Si la carpeta conectada ES el expediente** —lo habitual cuando el auditor conecta
la carpeta del cliente—, no hay otra: `_tmp_cowork\` en la raíz del expediente, fuera
de `AsistenteIA`, y **al terminar `limpiar_exportaciones()` borra el fichero y la
carpeta si queda vacía**. Dile al auditor que ahí ha habido contabilidad hasta el
borrado, por si el expediente se sincroniza a la nube.

Luego se sube y se trabaja con la copia del sandbox, que aparece bajo
`/mnt/user-data/uploads/` con la misma ruta relativa:

```bash
# device_stage_files con la ruta absoluta del extracto
EXTRACTO="/mnt/user-data/uploads/_tmp_cowork/extracto.csv"
```

**En la máquina del auditor (Claude Code) no hay nada de esto**: MCP y
scripts comparten disco, así que el paso 2 exporta a la carpeta temporal
del sistema y se lee de ahí.

```bash
EXTRACTO="<TEMP>/gesia-cancelacion/extracto.csv"
```

**Comprueba que el fichero se lee antes de seguir** —`head -1 "$EXTRACTO"` y `wc -l`, nunca `head -2`
basta—. Es lo que separa un fallo evidente de exportar dos veces sin
entender por qué la primera no valía, que es lo que pasó el 27/08/2026.
<!-- /solo-cowork -->

### Paso 2b — Comprobar que el extracto se lee

```bash
EXTRACTO="<TEMP>/gesia-cancelacion/extracto.csv"
```

**Comprueba que el fichero se lee antes de seguir**, y hazlo **sin traer ningún apunte al
contexto**: `head -1 "$EXTRACTO"` enseña la cabecera —las columnas que de verdad han
venido— y `wc -l "$EXTRACTO"` cuántas filas hay. Con eso basta. **No hagas `head -2` ni
`head -3`**: cada línea de más es un apunte real del cliente —nombre, concepto, importe—
que se queda en la transcripción, y el 08/09/2026 así entraron dos, incluida una apertura
de seis cifras. Es lo que separa un fallo evidente de exportar dos veces sin entender por
qué la primera no valía, que es lo que pasó el 27/08/2026.

### Paso 2c — Reconocer el extracto y preguntar (no te lo saltes)

**La cancelación de saldos no tiene un algoritmo único: depende de cómo pague el cliente
y de qué columnas trajo el diario.** La mejora más grande que ha tenido este skill vino de
una columna **opcional** que antes no se pedía nunca. Lanzarse a cincuenta cuentas sin
haber mirado eso es gastar el trabajo entero para acabar con un papel malo.

Así que antes de generar nada, una pasada en seco:

```bash
python "$SKILL/scripts/reconocer.py" --entrada "<extracto>"
```

No escribe ningún fichero. Dice qué columnas hay, **cuánto cancelaría cada señal medido
sobre este cliente**, cuántas aperturas se quedarían sin cerrar y con qué importe, qué
cuentas se atascan, y los grupos que se quedan a un céntimo de cuadrar.

**Y termina con una lista numerada de PREGUNTAS AL AUDITOR, cada una con sus opciones.**
Esa lista es la buena: son las que el script no puede contestar solo, y ya vienen
redactadas con la cuenta y el importe de los que hablan.

**Hazlas con la herramienta de preguntas al usuario si el entorno la tiene** —una entrada
por pregunta, el texto tal cual, las opciones que trae el script; la herramienta ya ofrece
«otra» libre, y si una opción acaba en «...» el auditor escribe ahí lo que falta—. El
auditor prefiere contestar así a leer un bloque de texto (10/09/2026). **Si no hay
herramienta, pásalas como lista numerada TAL CUAL: todas, con su número, sin resumirlas y
sin convertir ninguna en una afirmación.** En los dos casos, luego **espera respuesta**. Medido el 08/09/2026 en ChatGPT Cowork: el
modelo reescribió el bloque a su manera y se dejó una pregunta entera por el camino —la del
número de documento reutilizado entre ejercicios— y convirtió la de la apertura en un dato
informativo, así que nadie preguntó por el mayor del ejercicio anterior. La lista del script
crece y cambia con lo que encuentra; una lista paralela escrita aquí se queda atrasada.

Lo que cambia cada respuesta, para que sepas qué hacer con ella:

- **El número de documento con otro nombre** → se rehace el `SELECT` del paso 2 incluyendo
  esa columna y se vuelve a reconocer. Es la señal que más cancela.
- **El mayor del ejercicio anterior** → todavía no se usa: apúntalo y dilo al entregar. La
  apertura es lo que más vale del procedimiento, así que la respuesta interesa aunque hoy
  no se pueda aprovechar.
- **Los grupos a menos de 5 céntimos** ya no se preguntan: el script los da como **dato**,
  porque el skill **no sabe barrer céntimos** y preguntar lo que después no se puede aplicar
  es peor que no preguntar (pasó dos veces). Se quedan pendientes y **se cuenta al entregar**,
  con el importe.
- **Cómo paga o cobra el cliente** → **no cambia el cálculo**: no hay parámetro que lo lleve
  al script, y la pregunta ya no promete que lo haya. Sirve para leer los tamaños de grupo del
  papel y para la entrega: si dice algo que el dato no muestra —remesas, confirming—, dilo al
  entregar: es donde el papel se queda corto.
- **El número reutilizado entre ejercicios** → si dice que sí, avísalo al entregar: los
  grupos por documento siguen exigiendo suma cero, así que no se inventa nada, pero conviene
  que lo sepa.

Lo que responda **no manda sobre la aritmética**: una pista del auditor propone por dónde
sumar, y el grupo se acepta solo si suma cero. Por eso preguntar no tiene riesgo.

### Paso 3 — Verificar y generar el papel (puede abortar)

Una sola orden: comprueba el contrato y, solo si se puede seguir, escribe el
papel. Antes eran dos llamadas y no hacía falta volver entre una y otra.

```bash
PAPEL="Cancelacion Saldos <GRUPO> <CLIENTE> <EJERCICIO>.xlsx"
python "$SKILL/scripts/ejecutar_cancelacion.py" --entrada "$EXTRACTO" --salida "$TRABAJO/$PAPEL"
```

Salida `2` → **para**: el contrato no se cumple —faltan columnas, hay fechas o
importes que no se interpretan— y **no se ha escrito nada**.

Salida `1` → el papel **sí está escrito**, pero hay avisos: grupos del punteo
previo que no suman 0, cuentas muy grandes donde el paso 4 del algoritmo se
queda corto, cuentas con un solo signo donde no hay nada que cancelar, CONCEPTO
vacío que hace el papel menos legible. Que el extracto no traiga el texto de
`CONCEPTO` **no es un aviso**: es lo normal, y el papel lleva en su lugar `FECHA DOC.`
y `FACTURA` derivadas. El aviso A01 salta solo si tampoco trae `FechaEnConcepto`
—porque el SELECT no pidió `CONCEPTO`—: entonces **los hallazgos por fecha de
documento y el plazo de pago quedan sin evaluar** —la hoja de criterios lo dice—;
**cuéntalo al entregar**, y la próxima vez pide `CONCEPTO`. **Léelos y cuéntalos al entregar**, no
los escondas. La línea C05 dice si el diario trae punteo previo y cuánto: úsala
al explicar el resultado.

<!-- solo-cowork:entrega -->
**En Cowork el script escribe en el sandbox, no en el expediente**, así que
la ruta de destino no se cumple sola: hay que bajar el fichero. Se envía con
`SendUserFile`, que devuelve un `file_uuid`, y con `device_commit_files` se
escribe en el disco del auditor:

```
device_commit_files → "<expediente>/AsistenteIA/CancelacionSaldos/<PAPEL>"
```

En la máquina del auditor esto no hace falta: pásale directamente a
`--salida` la ruta del expediente y el script escribe ahí, creando el árbol
si no existe.
<!-- /solo-cowork -->

**Si el expediente está en OneDrive, el entorno puede rechazar la escritura antes
de ejecutar nada** y pedir autorización expresa para escribir datos contables ahí.
No es un fallo del skill ni del expediente: pídesela al usuario, explicando que es
el papel de trabajo que ha encargado, y repite la misma orden. Comprobado el
30/08/2026 en un expediente real.

Los dos scripts que hay debajo —`verificar_contrato.py` y `generar_papel.py`—
siguen valiendo por separado si hay que depurar uno de los dos, con los mismos
argumentos.

Imprime, por cuenta: apuntes / grupos previos (contabilidad) / grupos
nuevos (este papel) / sin cancelar / pendiente, y si alguna cuenta no
verifica o trae el punteo previo descuadrado. **Lee esa salida antes de
entregar** — no hace falta abrir el Excel para saber si algo falló.

**La primera hoja es «Criterios y hallazgos»**, y es la que hay que leer
antes de nada: dice bajo qué reglas se han formado los grupos, qué fecha se
usa para cada cosa, y **qué no prueba este papel** —un grupo es una
cancelación aritmética, no la evidencia documental de que ese pago liquide
esa factura—. Debajo van los recuentos: aperturas canceladas y vivas, pagos
anteriores a su factura, y el plazo de pago medido.

Ojo con la distinción que hace esa hoja, porque es la que evita perseguir
fantasmas: **muchas contabilidades registran la factura a fin de mes** y
escriben en el concepto la fecha del documento. Comparar contra la fecha del
asiento fabrica «pagos anteriores a su factura» que no lo son. Medido en un
expediente real: 835 casos con la fecha contable y **195** con la del
documento. Los otros 640 se cuentan aparte y se dicen como lo que son.

Para contar esos hallazgos hay que saber qué apuntes son facturas y cuáles
pagos, y **no se presupone el signo** —en una cuenta de proveedor la factura
es un abono y en una de cliente un cargo—. Se deduce en dos pasos: primero por
**estructura**, con el signo de la apertura, que arrastra las facturas
pendientes del ejercicio anterior y por tanto lleva el suyo; y si la cuenta no
tiene apertura y cierra a cero, como respaldo, mirando qué lado trae fecha de
documento. Si ninguno de los dos decide, **el grupo no se evalúa y la hoja lo
dice**: un cero ahí significaría «no hay hallazgos» cuando lo cierto sería «no
se ha mirado».

Esa fecha del documento **llega ya extraída por el MCP** (`FechaEnConcepto`): el
texto del concepto no hace falta para esto, y el papel la enseña en la columna
`FECHA DOC.`. Se usa **solo para informar**. El emparejamiento sigue trabajando con
la fecha contable: hacerlo depender de un campo de texto libre sería frágil, y hay
facturas que no lo traen —la hoja dice qué porcentaje, para que se sepa cuándo el
recuento vale menos—.

Cómo se lee el papel, por si el auditor pregunta: las hojas van en **orden
cronológico** con autofiltro en la cabecera, y solo hay dos colores —**gris**
en la fila de lo que ya venía punteado en la contabilidad, y **amarillo en la
celda del importe** de lo que no se ha podido parear, que es lo que compone el
saldo vivo de la cuenta. Lo que cancela este papel no lleva color: para saber
de dónde salió cada grupo está la columna ORIGEN, que dice **el paso que lo formó**:
`documento`, `apertura`, `total`, `importe`, `acumulación` o `combinación` (y `contable`
si venía punteado). Los de `acumulación` y `combinación` cierran por aritmética sobre
importes que no se parecen: **un grupo de 26 apuntes por acumulación puede ser real o
casualidad**, y la hoja de criterios cuenta cuántos hay de cada paso para que el auditor
sepa dónde mirar. Al entregar, si hay grupos grandes por acumulación o combinación, dilo.

Y en los pagos anteriores a su factura, **tres filas, no dos**: «con la fecha del
documento» (los que hay que mirar), «lo parecen solo por la fecha de registro» (no son
anomalía) y **«solo con la fecha contable»**, que son los de facturas **sin** fecha de
documento: ahí no se puede distinguir un registro tardío de un pago anticipado, y **no se
presentan como hallazgos ciertos**. En la prueba en frío del 10/09/2026, con el 0 % de
facturas con fecha, se entregaron seis «reales según la fecha del documento» que no lo
eran.

### Paso 4 — Entregar

Di dónde ha quedado el fichero, cuántas cuentas lleva, y **para cada una
cuántos grupos venían punteados de la contabilidad, cuántos añadió este
papel y cuántos apuntes quedan pendientes**. El listado del script se corta a 30
cuentas, pero **la línea `TOTAL` del final va siempre**: cuentas, apuntes, grupos,
sin cancelar, pendiente total y si todas verifican. Es la que se le da al auditor;
no hace falta abrir el Excel para el agregado. Si alguna cuenta no verifica
(columna VERIFICACION = REVISAR en la hoja Resumen), dilo antes que nada:
ese papel no se entrega tal cual. Si hay descuadre del punteo previo,
cuéntalo como lo que es: un posible error de punteo en la contabilidad del
cliente, que el auditor tendrá que mirar.


**Los nombres.** El fichero se ha escrito con tokens. Cuando ya esté en el disco del auditor
—en Cowork, después de bajarlo al expediente; en local, directamente—, llama a
`rehidratar(ruta = "<expediente>/AsistenteIA/…/<fichero>", leyenda = true)`: sustituye cada
token por el nombre real, en local, y devuelve recuentos —ni un nombre vuelve aquí—. Con
`leyenda = true` añade la tabla token → nombre (hoja «Tokens» en el Excel), para que lo que
has dicho en el chat con tokens se pueda leer en el papel. **Cuéntale al auditor los dos
números que devuelve** (sustituciones y tokens distintos) y, si hay `tokens_sin_nombre`,
dilos tal cual: son cuentas que el diccionario no conoce, no las completes tú.

Con este párrafo, y sin llamar «rehidratar» a nada delante del auditor —para él es
**desanonimizar**—:

> *Papel generado y archivado en el expediente: `AsistenteIA\…\<fichero>` (también lo tienes
> en el chat, aunque esa copia está anonimizada). Nombres ya desanonimizados: N sustituciones,
> M terceros distintos, ninguno sin nombre, y hoja «Tokens» con la leyenda. El extracto
> temporal está borrado.*

Si hubo tokens sin nombre, en vez de «ninguno sin nombre» van listados. <!-- solo-cowork:papel-unico -->La copia del chat
**siempre** está anonimizada —viajó por el contenedor—: dilo, para que no la confunda con el
papel bueno.<!-- /solo-cowork -->

**Los temporales.** Llama a `limpiar_exportaciones()`: borra el extracto,
que lleva contabilidad del cliente. Funciona igual en local y en Cowork —lo
borra el MCP, que corre en la máquina del usuario— y no hay que decirle qué
fichero: borra lo que él escribió. Si algo no se puede borrar (típicamente
un `.csv` abierto en Excel), lo dice con su ruta: trasládala al usuario.
Borra tú el directorio de trabajo aparte, si creaste uno. **El diccionario de nombres no se
borra**: vive con el encargo, cifrado, y es lo que permite rehidratar un papel de hace días.

---

## Lo que este skill no hace

- **No escribe en el expediente.** El MCP solo lee.
- **No rehace ni corrige el punteo contable.** Lo punteado se respeta tal
  cual, incluso si un grupo no suma 0 —eso se avisa y lo juzga el auditor—.
- **No usa el texto de CONCEPTO** para decidir qué apuntes van juntos, ni
  los campos `NN_*` —ver arriba por qué.
- **No es un subset-sum exacto e ilimitado.** La combinatoria del paso 4 del
  algoritmo se acota a 22 apuntes sin cancelar y grupos de hasta 6: por encima de
  eso, sencillamente no se busca, y esos apuntes quedan en ÍNDICE 0. No es
  un recorte silencioso —`verificar_contrato.py` avisa cuando una cuenta es
  lo bastante grande para que esto importe—, pero tampoco hace magia con
  miles de apuntes sueltos.
- **No decide qué cuenta o grupo de cuentas procesar.** Eso lo dice el
  auditor en el paso 1.
- **No explica por qué un apunte queda pendiente**, solo lo localiza. Que
  una factura siga en ÍNDICE 0 puede ser porque de verdad está impagada, o
  porque el pago viene en otro ejercicio, u otra cuenta, o con un importe
  distinto por una retención o un descuento: eso lo investiga el auditor.

## Degradación

| Situación | Qué sale |
|---|---|
| Sin diario importado | **para.** No hay apuntes que cancelar |
| Extracto sin FECHA, CUENTA o NOMBRE | **para.** Faltan columnas obligatorias |
| Extracto sin CONCEPTO pero con `FechaEnConcepto` y `NumeroEnConcepto` | sigue: es lo normal. El papel va sin el texto y con `FECHA DOC.` y `FACTURA` derivadas; la hoja de criterios dice de dónde salen |
| Extracto sin fecha de documento (ni `FechaEnConcepto` ni CONCEPTO) | sigue: los hallazgos por fecha de documento quedan sin evaluar; A01 lo dice y se cuenta al entregar |
| `rehidratar` devuelve `tokens_sin_nombre` | sigue: el papel se entrega con esos tokens tal cual y se dicen al auditor; no se completan a mano |
| FECHA o SALDO no interpretables | **para**, y dice cuántos apuntes |
| El diario no trae columna `Indice` | sigue: el emparejamiento parte de cero (C05 lo dice) |
| Grupo del punteo previo que no suma 0 | sigue: se respeta, se avisa (A04) y el papel lo lista como descuadre del punteo contable |
| Cuenta con más de 500 apuntes sin puntear | sigue, y avisa de que la combinatoria del paso 4 del algoritmo se acota |
| Cuenta con apuntes pendientes de un solo signo | sigue: todo queda en ÍNDICE 0, y se avisa de que no había nada que cancelar |
| Un grupo del skill no suma exactamente 0 (bug, no debería pasar) | la hoja de esa cuenta marca VERIFICACION = REVISAR |
| Fichero de salida abierto en Excel | **para** al guardar, y dice que hay que cerrarlo |

## Comprobar que el skill funciona

```bash
python "$SKILL/scripts/probar_cancelacion.py"
```

No hace falta Gesia: usa un fixture sintético con ocho cuentas de prueba
(una por procedimiento, una que combina pareo directo y acumulación, y
tres de punteo previo: parcial, descuadrado y completo). Si algo falla
aquí, no se ha tocado nada del expediente — es el momento de arreglarlo
antes de correr esto contra datos reales.
