---
name: cuadro-mando-diario-gesia
description: >
  Genera el cuadro de mando HTML del diario contable de un expediente de auditoría de
  Gesia. Lee el diario vinculado al expediente (.smn), lo verifica, lo concilia contra
  los saldos del expediente, analiza el punteo y los apuntes atípicos, y produce un
  panel autocontenido en la carpeta AsistenteIA\CuadroMandoDiario del propio
  expediente.
  Usa este skill cuando el usuario pida el cuadro de mando del diario, el panel del
  diario, los procedimientos analíticos del diario, revisar el diario de un cliente,
  analizar los asientos del ejercicio, o diga cosas como "lanza el cuadro de mando",
  "saca el panel del diario", "analiza el diario del cliente", "revisión analítica
  del diario" o "genera el informe del diario".
  Requiere Gesia abierto con un expediente que tenga diario importado.
---

# Cuadro de mando del diario contable (Gesia)

Produce un papel de trabajo, no una publicación. El panel se escribe **como fichero**
en la carpeta del expediente y **nunca se publica** en ninguna URL: contiene el diario
íntegro de un cliente auditado.

El modelo **no escribe HTML ni cálculos en tiempo de ejecución**. La plantilla, el
JavaScript y los seis scripts son activos de este skill. El trabajo del modelo es
orquestar, leer resúmenes acotados y explicar el resultado.

---

## Antes de empezar: dos principios que gobiernan todo

**1. Verificar el contrato, no fiarse de la documentación.** La semántica de los campos
del `.smn` no coincide con lo documentado en más de un expediente. La fase 1 lo comprueba
en ejecución y **aborta** si algo no encaja. Si `verificar_contrato.py` devuelve 2, se
para: no se genera panel. Un panel bonito sobre datos mal entendidos es peor que no
tener panel.

**2. Describir, no dictaminar.** El panel dice cuánto vale cada cosa y deja el juicio al
auditor. Nunca afirma que un patrón sea normal. Todo lo que sale del punteo se presenta
como *lista de revisión*, nunca como medida contable.

---

## Dónde están los scripts

Al cargarse, el runtime indica el **directorio base de este skill**. Todas las rutas
`scripts/…` y `assets/…` de este documento son relativas a ese directorio, no al
directorio de trabajo. Guárdalo al empezar y úsalo siempre:

```bash
SKILL="<directorio base indicado al cargar el skill>"
TRABAJO="$(pwd)/trabajo" && mkdir -p "$TRABAJO"
python3 "$SKILL/scripts/verificar_contrato.py" "$TRABAJO/diario.mdb" ...
```

**No copies los scripts al directorio de trabajo.** `generar_panel.py` localiza la
plantilla como `../assets/` respecto a su propio fichero, así que `scripts/` y `assets/`
tienen que seguir siendo hermanos dentro del skill. Lo que va al directorio de trabajo
son solo el `.mdb` y los JSON.

---

## Secuencia

### Paso 1 — Localizar el expediente y el diario

```
configurar(perfil = "cuadro-mando-diario")   # primero: nombres de terceros tokenizados
```

**Lo primero, antes de leer nada: `configurar(perfil = "cuadro-mando-diario")`.** Con el perfil, el
MCP retira del extracto las columnas que este skill no necesita y **tokeniza los nombres de
terceros** en todo lo que devuelve: verás `PROV 40000012` o `CLI 43000007` donde iría la razón
social. El nombre no sale del equipo del auditor —ni al contenedor ni a este chat—; el papel lo
recupera al final con `rehidratar`. Trabaja y habla **por cuenta y por token**: «la apertura de
PROV 40001013 no cierra». **Nunca preguntes al auditor a quién corresponde un token ni lo
adivines** por el concepto o por los importes: él lo lee en el papel. Si `configurar()` dice
`nombres_terceros: en claro — forzado por el auditor`, es que lo ha apagado él; no lo
vuelvas a encender tú.

- Si falta `gs3_file`, **pide la ruta al usuario**. No la adivines.
- Si la respuesta dice que el expediente **no tiene diario importado**, para aquí y
  dícelo: no es un problema de configuración y no se arregla apuntando a otro `.smn`.
- La ruta del diario sale de `smn_file` en la respuesta. **Nunca la construyas tú**:
  el skill analiza el diario que Gesia tiene vinculado, y solo ese.

```
contexto_expediente()
```

De aquí salen `RazonSocialCliente`, `FechaCierre` e **`IR_T`** (la importancia relativa
de trabajo), que es el ancla de todos los umbrales del panel.

### Paso 2 — Traer el plan de cuentas del expediente

Una sola consulta, acotada:

```sql
SELECT Cuenta, Nombre, SaldoAnterior, SaldoCliente, SaldoAj
FROM Cuentas
WHERE Val(Digitos)=3 AND (SaldoCliente<>0 OR SaldoAnterior<>0 OR SaldoAj<>0)
ORDER BY Cuenta
```

Guarda la respuesta **tal cual** en `<trabajo>/cuentas_gesia.json`. De la fila de la
cuenta **`080`** salen tres cifras que alimentan la cabecera del panel:
`SaldoCliente` (resultado del ejercicio), `SaldoAnterior` (ejercicio precedente) y
`SaldoAj` (ajustes de auditoría).

### Paso 3 — Traer el diario al contenedor

> **Corregido el 27/08/2026 — la ruta de este bloque ya no es válida.**
> `device_stage_files` solo sube ficheros que estén **dentro de una carpeta conectada** a
> la sesión, y el `$TEMP` de Windows no lo está: desde ahí no se puede subir. El
> comprimido tiene que escribirse en una subcarpeta de trabajo de la raíz de la carpeta
> conectada —`<raíz conectada>\_tmp_cowork\`—, nunca dentro del expediente, y borrarse al
> terminar. Lo que sigue valía cuando el mecanismo admitía cualquier ruta; el resto del
> bloque (comprimir, los límites de tamaño) sigue vigente. Ver `docs/arquitectura.md`.

El `.smn` es una base Access JET4. Directo **da tiempo de espera**: el presupuesto de
transferencia de `device_stage_files` es de unos 50 segundos y un diario de un ejercicio
no cabe. Medido: 11 MB no pasan, y 6,98 MB tampoco; comprimidos son 1,17-2 MB y sí pasan.

```bash
# en la máquina del usuario
mkdir -p "<expediente>/AsistenteIA/CuadroMandoDiario"
gzip -c "<smn_file>" > "$TEMP/gesia-cuadro-mando/diario.smn.gz"
```

Luego `device_stage_files` con esa ruta, y en el contenedor:

```bash
which mdb-export || apt-get install -y mdbtools
gunzip -c "<staged>/diario.smn.gz" > <trabajo>/diario.mdb
```

**El temporal va a la carpeta temporal del sistema, no a `AsistenteIA`.** En el
expediente solo se archivan papeles de trabajo; un `.gz` con la contabilidad del cliente al
lado del panel firmado es contabilidad ajena en una carpeta que se archiva. Y al terminar se
borra, en el paso de entrega.

### Paso 4 — Contrato del diario (puede abortar)

```bash
python3 scripts/verificar_contrato.py <trabajo>/diario.mdb \
  --json <trabajo>/contrato.json --cierre <FechaCierre> --ir-t <IR_T> \
  --resultado-08=<SaldoCliente de 080> \
  --resultado-anterior=<SaldoAnterior de 080> \
  --ajustes=<SaldoAj de 080>
```

Los importes de Gesia llegan con coma decimal; los argumentos la aceptan. **Usa la forma
`--ajustes=-98481,72`** con signo igual: un valor negativo sin `=` lo interpreta argparse
como una opción.

| Código de salida | Qué hacer |
|---|---|
| 0 | seguir |
| 1 | seguir; los avisos se muestran en el panel |
| **2** | **parar**. Explica el motivo al usuario y no generes panel |

### Paso 5 — Conciliación con el expediente

```bash
python3 scripts/conciliar_gesia.py <trabajo>/diario.mdb \
  --cuentas <trabajo>/cuentas_gesia.json --nivel 3 --ir-t <IR_T> \
  --json <trabajo>/conciliacion.json
```

Si devuelve **2** (descuadres materiales) el panel **se genera igual** —lleva una tarjeta
crítica en cabecera— pero **avisa al usuario en tu respuesta de que no es un papel de
trabajo válido** hasta resolverlos.

### Paso 6 — Punteo y partidas abiertas

```bash
python3 scripts/analizar_punteo.py <trabajo>/diario.mdb \
  --cierre <FechaCierre> --ir-t <IR_T> --json <trabajo>/punteo.json
```

Devuelve 2 si no hay punteo o si el aging queda suprimido. **No es un error**: el panel
degrada y lo explica. Sigue adelante.

### Paso 7 — Análisis del diario

```bash
python3 scripts/analizar_diario.py <trabajo>/diario.mdb \
  --cierre <FechaCierre> --ir-t <IR_T> --json <trabajo>/analisis.json
```

### Paso 8 — Generar el panel

```bash
python3 scripts/generar_panel.py \
  --contrato <trabajo>/contrato.json \
  --conciliacion <trabajo>/conciliacion.json \
  --punteo <trabajo>/punteo.json \
  --analisis <trabajo>/analisis.json \
  --cliente "<RazonSocialCliente>" --cierre <FechaCierre> \
  --generado "$(date -I)" --ir-t <IR_T> \
  --salida <trabajo>/panel.html
```

`--generado` se pasa como parámetro y ningún script lee el reloj por su cuenta: así el
sello de la cabecera es explícito y auditable.

### Paso 9 — Verificar antes de entregar

Abre el HTML en Chromium y comprueba que **no hay errores de consola**. Una captura basta:
el validador de datos no ve la maquetación.

```bash
node <trabajo>/verificar_panel.js     # plantilla en assets/verificar_panel.js
```

### Paso 10 — Entregar

1. `SendUserFile` del `panel.html` y de los cuatro JSON.
2. `device_commit_files` de todos ellos a
   `<expediente>\AsistenteIA\CuadroMandoDiario\` —la regla del proyecto de una
   subcarpeta por skill, y esta es la única ruta donde el auditor los va a buscar—, con
   nombres que incluyan cliente y fecha de cierre:
   `panel_diario_<CLIENTE>_<cierre>.html`, `contrato_diario_...json`, etc.
3. **Los nombres.** El panel y los JSON se han escrito con tokens (`PROV 40000012`…). Ya en
   el disco del auditor, llama a `rehidratar(ruta)` **sobre cada uno de los cinco ficheros**
   —el `.html` y los cuatro `.json`—: sustituye los tokens por los nombres reales en local y
   devuelve recuentos, ni un nombre vuelve aquí. Dile al auditor cuántas sustituciones y, si
   hay `tokens_sin_nombre`, cuáles, sin completarlos tú. Delante de él no se dice
   «rehidratar»: se dice **desanonimizar**, y se le recuerda que la copia del chat está
   anonimizada y la buena es la del expediente.
4. **Nunca** publiques el panel como artefacto ni lo subas a ninguna URL.
5. **Borra los temporales**: `rm -rf "$TEMP/gesia-cuadro-mando" <trabajo>`. En
   `AsistenteIA` solo debe quedar el panel y sus JSON. Si algo no se deja borrar, dilo con
   su ruta: son datos del cliente y no pueden quedarse por olvido.

Los cinco JSON reproducen el panel sin volver a leer el `.smn`: si hay que regenerarlo con
otro umbral, basta el paso 8.

---

## Degradación según las opciones de importación

`Indice` (punteo) y `APERTURA` son **opciones que el auditor activa o no** al importar el
diario en Gesia. **Están acopladas**: el punteo se apoya en la apertura para casar los
pagos de facturas del ejercicio anterior.

| Punteo | Apertura | Qué sale |
|---|---|---|
| Sí | Sí | Panel completo |
| Sí | No | Plazos de liquidación; **aging suprimido** |
| No | Sí | Sin sección de punteo |
| No | No | Núcleo básico y aviso |

Cuando falte alguna, dile al usuario que **reimportar el diario con las dos opciones
activadas** recupera esas secciones. Es accionable en dos minutos.

**Umbral de cobertura: 80 %.** Por debajo, `Indice=0` significa «no punteado», no
«pendiente», y el aging de esa cuenta se muestra **sin cifra de cabecera**.

---

## Trampas del formato (comprobadas en expedientes reales)

Estas no son hipótesis: cada una produjo un resultado falso antes de corregirse.

- **`Indice` no es un indicador de anulación.** Es el número de punteo, y **se numera por
  cuenta**, no globalmente. La clave de agrupación es `(CUENTA, Indice)`. Filtrar
  `WHERE Indice=0` creyendo que lo demás está anulado tira más de la mitad del diario.
- **`SALDO` es `Debe − Haber` de la propia línea**, no un acumulado. La comprobación C16
  lo verifica en cada ejecución y avisa si en ese expediente significa otra cosa.
- **Los campos `NN_*` pueden no existir y su semántica no está garantizada.** Los grupos
  de cuenta se derivan **siempre** de `Left(CUENTA, n)`.
- **El nivel de 4 dígitos de `Cuentas` está incompleto**: Gesia no crea esa agregación en
  todas las ramas. Conciliar a 1, 2 o 3 dígitos, nunca a 4.
- **`Digitos` es exactamente `Len(Cuenta)`.** No aporta nada; existe y punto.
- **Gesia calcula la `080` y, si el diario no trae regularización, la `129`.** Compararlas
  con el diario produce descuadres falsos: van excluidas y listadas aparte.
- **Un grupo con movimiento y saldo cero al cierre no aparece** al filtrar
  `SaldoCliente<>0`. Su ausencia es conforme, no un descuadre.
- **Hay abonos anotados como Debe negativo.** Medir el volumen como `Debe+Haber` los
  *resta*. Todo el panel mide en neto y el volumen como `|neto|`.
- **El punteo a veces casa la cuenta entera consigo misma** (caja, IVA): miles de líneas
  en un grupo cuyo «plazo» es solo la duración del ejercicio. Se detecta y se excluye de
  los plazos, pero sus líneas **sí** cuentan como canceladas.
- **La antigüedad de partidas abiertas solo tiene sentido en cuentas de terceros y
  tesorería** (grupos 4 y 5). En una cuenta de resultados el saldo no son partidas
  pendientes: es el gasto o el ingreso del ejercicio.

### Limitaciones del dialecto de Access (JET)

- **No hay `COUNT(DISTINCT)`.** Usa `SELECT Count(*) FROM (SELECT DISTINCT …)`.
- **No se puede usar como alias el nombre de una columna existente**: da «referencia
  circular».
- **`Mod` es un operador entero y redondea sus operandos.** No sirve para contar importes
  redondos: `1.999,83` pasaría por múltiplo de 1.000. Ese cálculo va en Python.
- No hay CTEs ni funciones de ventana: cuantiles y z-scores se calculan en el cliente.
- `Weekday()` devuelve 1 = domingo, 7 = sábado.

### Disciplina de consultas al MCP

Toda consulta debe tener **cardinalidad acotada por construcción** (`TOP n`, o un
`GROUP BY` cuyo número de filas se conozca). Un `GROUP BY` descuidado puede devolver
cientos de filas y costar más que todo el resto de la ejecución junta.

---

## Lo que este panel no puede hacer

- **No hay hora ni usuario en el diario.** El análisis de registro fuera de horario y por
  operador no es posible. No lo prometas.
- **No lleva el explorador de todos los apuntes.** Con decenas de miles de líneas no cabe
  embebido. Lo que sí lleva es la tabla de **apuntes marcados** (fin de semana, importe
  redondo, por encima de IR_T, duplicado), con el recuento completo y un tope de 150
  filas por marca.
- **El fin de semana no se interpreta.** Se informa el recuento y el porcentaje, y se
  dice explícitamente que si no encaja con la actividad del cliente, esa cifra es en sí
  misma el hallazgo. Un diario puede tener el 12 % de los apuntes en sábado porque el
  negocio abre los sábados, o porque está amañado, y el fichero no lo distingue.
- **Los picos de actividad se miden contra la línea base del propio cliente**, no contra
  reglas universales. Casi todos los días anómalos de un diario real son cierres
  mensuales, y el panel lo marca para que no se confundan con hallazgos.

---

## Ficheros del skill

```
scripts/lib_diario.py         lectura del .smn, columnas derivadas, punteo, apertura
scripts/verificar_contrato.py fase 1 — contrato de datos (puede abortar)
scripts/conciliar_gesia.py    fase 2a — conciliación con los saldos del expediente
scripts/analizar_punteo.py    fase 2b — plazos y partidas abiertas
scripts/analizar_diario.py    fase 2c — evolución, actividad y atípicos
scripts/hechos.py             reglas que generan las tarjetas de hechos relevantes
scripts/generar_panel.py      fase 3 — une los JSON e inyecta la plantilla
assets/panel_estilo.html      plantilla (paleta validada; no cambiar los hex sin revalidar)
assets/panel.js               gráficos, tablas ordenables, filtros
assets/verificar_panel.js     comprobación en Chromium antes de entregar
scripts/probar_*.py           arneses de prueba (38 comprobaciones en total)
```

Los arneses se ejecutan si se toca algún módulo:

```bash
python3 scripts/probar_degradacion.py <diario.mdb>     # 13 escenarios
python3 scripts/probar_conciliacion.py <diario.mdb> <cuentas.json>   # 10 casos
python3 scripts/probar_punteo.py <diario.mdb>          # 15 comprobaciones
```
