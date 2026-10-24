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
- **Ningún nombre de tercero sale del equipo del auditor.** Se trabaja con el perfil
  `fsp-mum-nia530`, que seudonimiza igual que el de `fsp-mum`, y los terceros van por su token
  (`PROV`, `CLI`, `TER`). Si la muestra llega sin seudonimizar, el constructor **para** y manda
  volver a configurar. El Word se escribe con tokens, y los nombres se recuperan al archivarlo,
  en el equipo del auditor, con `rehidratar` (paso 5).
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
TRABAJO="$(mktemp -d)"     # uno NUEVO en cada ejecución
DATOS="$TRABAJO"
```

**Un directorio de trabajo nuevo en cada ejecución**, aunque `fsp-mum` u otra ejecución de este
skill hayan dejado uno en la sesión: reutilizarlo mezcla exportaciones de otra prueba o de otro
perfil con las de esta, y el papel las tomaría por suyas. **No hagas `cd` dentro**: trabaja con
rutas absolutas (`"$TRABAJO/…"`), para poder borrarlo entero desde fuera al terminar (paso 5).

`<DATOS>` es ese mismo directorio, en local y en un contenedor: ahí van los JSON que escribes tú
y la copia de lo que exporta el MCP. El papel de `fsp-mum` no se copia aquí: se lee de donde
esté (paso 3).

---

## Secuencia

### Paso 1 — Contexto y prueba

`configurar(gs3_file=…, perfil="fsp-mum-nia530")`. Con un `.gs3` que vincula el cliente de
muestreo vale igual que con el `.cli` directamente. Si responde que el API no contesta, llama a
`arrancar_api` y sigue.

**El perfil va lo primero, aunque `fsp-mum` se haya ejecutado en la sesión con el suyo.**
Seudonimiza igual, con los mismos tokens, y además marca el comienzo de este procedimiento: desde
ahí el MCP lleva la cuenta de lo que se facilita a la herramienta para este papel, aparte de lo
que se facilitó para la MUM, y eso es lo que el Word dirá en su apartado de uso de IA.

**Si `configurar` trae `aviso_otra_conversacion`** —hace poco se trabajaba en el mismo servidor
con otro expediente o con otro perfil—, mira primero si fue **esta** conversación: si aquí mismo
acabas de ejecutar `fsp-mum` u otro procedimiento, es eso y se sigue sin decir nada. Si no,
díselo al auditor tal cual y **no sigas hasta que confirme que la otra conversación ha
terminado**: en Cowork todas comparten un mismo MCP y se pisan el expediente activo, el perfil,
la cuenta de lo facilitado y los ficheros de trabajo.

Si el fichero es un `.gs3`, llama **siempre** a `contexto_expediente()` justo después de
`configurar`, **aunque ya lo tengas en la conversación** —de `fsp-mum` o de una ejecución
anterior—: lo leído con otro perfil no consta como facilitado para este papel, y puede ser de
otro expediente. Escribe la respuesta tal cual en `<DATOS>/contexto.json`. Trae la razón social,
el cierre y la importancia relativa (`IR_P`, `IR_T`, `IR_I`). Con un `.cli` solo, **no hay
contexto**: el papel sale en modo `solo_fs` y lo de Gesia se solicita en el apartado 9.

`obtener_entidad('pruebas')` → guárdalo en `<DATOS>/pruebas.json`. Elige la prueba MUM
(`Tipo = MUM`); si hay varias, **pregunta cuál**. Anota su `MuestraId`.

**Lo que devuelven `obtener_entidad` y `contexto_expediente` se guarda TAL CUAL**: copia el JSON
íntegro de la respuesta al fichero, sin reescribirlo, sin reordenarlo y sin transcribir a mano
un solo importe, fecha o código. Un importe reescrito es un error que nada detecta después: el
papel lo da como leído de ForSampling. `pruebas.json` puede reducirse a la fila de la prueba
elegida, pero **copiándola** entera tal como vino, no reescribiéndola.

### Paso 2 — Las cuatro exportaciones de la prueba

```
obtener_entidad('parametros', id = <MuestraId>)   → <DATOS>/parametros.json   (el JSON íntegro, copiado)
obtener_entidad('resumen',    id = <MuestraId>)   → <DATOS>/resumen.json      (el JSON íntegro, copiado)
exportar_consulta(entidad = "muestra",    id = <MuestraId>, ruta = "<DATOS>/muestra.json")
exportar_consulta(entidad = "evaluacion", id = <MuestraId>, ruta = "<DATOS>/evaluacion.json")
```

<!-- solo-cowork:alt=Los ficheros exportados van a `<DATOS>`, que es una carpeta local: aquí no hay contenedor ni copias que subir. **Que sea una carpeta nueva en esta ejecución**, no la de `fsp-mum` ni la de otra prueba —se mezclarían exportaciones de otro perfil—, y no entres en ella con `cd`: usa rutas completas, para poder borrarla entera desde fuera al terminar (paso 5). -->
**En Cowork el MCP escribe en el disco del auditor y los scripts corren en el contenedor**, así
que `muestra.json` y `evaluacion.json` no pueden ir directos a `$DATOS`. Expórtalos a
`<raíz de la carpeta conectada>\_tmp_cowork\`, súbelos con `device_stage_files` **por su nombre
exacto** —nunca con comodín: en esa carpeta puede haber exportaciones de otros procedimientos— y
copia lo subido a `$DATOS`. La ruta subida cuelga de una subcarpeta con el nombre de la carpeta
conectada: `/mnt/user-data/uploads/<carpeta conectada>/_tmp_cowork/muestra.json`.

**Si `device_stage_files` falla por permisos**, pide acceso con `device_request_folder_access`
sobre la raíz de la carpeta conectada y repite **una sola vez**. Si vuelve a fallar, para y
díselo al auditor con la ruta. Los JSON que escribes tú (`pruebas`, `parametros`, `resumen`,
`contexto`) van directos a `$DATOS`: no pasan por el equipo del auditor.
<!-- /solo-cowork -->

`parametros` trae el bloque **`descodificado`**: confianza y factor del riesgo general, criterio
y método de selección, si el error tolerable se definió por valor o por tasa, y **los dos
factores de confianza** con su fuente. `resumen` trae la población en cifras sin una sola fila:
elementos, valor, máximo, seleccionados, selecciones, intervalo, cobertura, el desglose por
grupo y **el cuadre del `.smp` de importación con el fichero de la prueba**. Si alguna de las
dos no trae eso, el MCP es anterior a la 1.23.0: el papel saldrá con más PENDIENTES y hay que
decirlo.

Si `fsp-mum` se ejecutó en la sesión, la muestra y la evaluación ya se exportaron una vez, pero
con su perfil y a su directorio: **expórtalas otra vez** con el perfil de este papel y a este
directorio. Salen iguales, y lo que no se exporte desde el paso 1 no constará como facilitado en
el apartado de uso de IA.

### Paso 3 — Construir el JSON del papel (puede abortar)

```bash
python "$SKILL/scripts/construir_nia530.py" --id <MuestraId> \
  --pruebas "$DATOS/pruebas.json" --parametros "$DATOS/parametros.json" \
  --resumen "$DATOS/resumen.json" --muestra "$DATOS/muestra.json" \
  --evaluacion "$DATOS/evaluacion.json" \
  [--contexto "$DATOS/contexto.json"] [--excel "<papel de fsp-mum>.xlsx"] \
  --salida "$DATOS/nia530.json"
```

`--excel` es el papel de `fsp-mum` de **esta** sesión —la copia seudonimizada, nunca la que
tiene los nombres recuperados—, leído de donde esté: de él salen el importe según documento y el
error de cada elemento. Sin él, los apartados 6 y 7 salen PENDIENTES; **propón ejecutar
`fsp-mum` antes**, y si el auditor no quiere, sigue sin él. Ese Excel lo lee el script, no el
MCP: el apartado de uso de IA lo declara aparte y dice que sus importes y errores son propuestas
de la herramienta.

Salida `2` → **no hay papel**: la prueba no es MUM, falta una exportación, o **la muestra no
está seudonimizada** (el nombre del tercero iría al Word: se para). Salida `1` → se sigue, y los
avisos van al auditor literales. Salida `0` → todo encaja.

**Antes de generar el Word, di cuántos elementos trae medidos el papel de `fsp-mum`.** El
constructor lo imprime en una línea —«importe según documento (papel de fsp-mum): N de M
elementos · K sin documento localizado · P sin medir»— y va al auditor tal cual. Si además avisa
**«POCOS DOCUMENTOS MEDIDOS»** —menos de la mitad de los elementos con importe según documento—,
**no sigas al paso 4**: los apartados 6 y 7 saldrían casi enteros PENDIENTES y el papel
describiría lo que falta, no la prueba. Propón volver a `fsp-mum` para completar la lectura de
los documentos y documentar después. Solo si el auditor pide seguir igualmente, sigue, y el
aviso se cuenta al entregar como los demás.

Después de construirlo, **abre `nia530.json` y completa lo que es del auditor si él te lo ha
dicho en la conversación**, y solo eso: `afirmacion`, `riesgo_area`, `p.motivacion`,
`conciliacion_detalle`, `causa_errores`, `anomalias`, `por_cuenta` (si te ha dado el saldo
contable por cuenta) y `diario`. Lo que no te haya dicho se queda en `null`. Lo que completes,
el apartado de uso de IA lo da como indicado por el auditor en la conversación.

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

**Y termina con el apartado «Utilización de herramientas de inteligencia artificial»**, con una
marca en la portada, junto a Preparado y Revisado: la evidencia de que el papel se hizo con una
herramienta de IA, de qué se le facilitó y de cómo debe verificarse. Dice qué partes ha
redactado la herramienta, y sus comprobaciones —selección y cuadre de la población contra
ForSampling, parámetros leídos, terceros seudonimizados— las calcula el script sobre lo que
lleva el papel. Los apartados de la herramienta quedan con huecos que se rellenan al archivar
(paso 5); los de verificación, verificado por, efecto en la conclusión y revisión **son del
equipo y salen en blanco**. No escribas nada en ellos ni propongas texto para ellos. No los
confundas con la conclusión del apartado 8, que también queda en blanco y es del auditor.

<!-- solo-cowork:entrega -->
**En Cowork el script escribe en el sandbox, no en el expediente**: pásale a `--salida`
`"$DATOS/<fichero>"` y baja el fichero **por su nombre exacto** —nunca con comodín: en `$DATOS`
hay JSON con datos de la prueba que no son papel—. Se envía con `SendUserFile`, que devuelve un
`file_uuid`, y con `device_commit_files` se escribe en el disco del auditor:

```
device_commit_files → "<expediente>/AsistenteIA/FspMum/<fichero>"
```

**Si el expediente está en OneDrive, el entorno puede rechazar la escritura antes de ejecutar
nada** y pedir autorización expresa para escribir ahí. No es un fallo del skill: pídesela al
usuario y repite.
<!-- /solo-cowork -->

### Paso 5 — Archivar y entregar

**Con el Word ya en el disco del auditor**, en `<expediente>\AsistenteIA\FspMum\`, dos llamadas
sobre esa ruta de Windows, en este orden:

1. **`sellar_uso_ia(ruta = "<expediente>/AsistenteIA/FspMum/<fichero>", modelo = "<el modelo con
   el que trabajas>", procedimiento = "fsp-mum-nia530")`.** Rellena en el apartado de uso de IA lo
   que solo sabe la aplicación: herramienta y versiones, quién lo ejecutó, dónde corrieron los
   scripts y **qué información se facilitó y cómo**, según lo que el MCP ha servido desde el paso
   1. `procedimiento` es el perfil de este skill: con él, el sello lista lo facilitado para este
   papel y no lo de otro procedimiento que haya usado el mismo servidor. En `modelo` pon el
   nombre y la versión que te da tu propio contexto; si no lo sabes, déjalo vacío. **Sin esta
   llamada el papel queda con huecos que dicen «pendiente»**: no se da por entregado. Si la
   respuesta dice que **mientras se hacía el papel se usó el mismo servidor con otro contexto,
   probablemente desde otra conversación**, cuéntaselo al auditor tal cual: la lista de lo
   facilitado puede estar incompleta o mezclada, y lo exportado de verdad consta en
   `AsistenteIA\RegistroEmision.jsonl`.
2. **`rehidratar(ruta = "<expediente>/AsistenteIA/FspMum/<fichero>", leyenda = true)`.** Sustituye
   cada token del Word por el nombre real, en local, y devuelve recuentos —ni un nombre vuelve
   aquí—. Con `leyenda = true` deja la equivalencia token-nombre en `<fichero>.leyenda.csv`, al
   lado del Word, para que lo que has dicho en el chat con tokens se pueda leer en el papel.
   **Cuéntale al auditor los dos números que devuelve** (sustituciones y tokens distintos) y, si
   hay `tokens_sin_nombre`, dilos tal cual: no los completes tú.

**Los temporales**, después de archivar:

- **`limpiar_exportaciones(procedimiento = "fsp-mum-nia530")`** borra la muestra y la evaluación
  que exportaste para este papel, y solo eso: lo que exportó `fsp-mum` u otra conversación se
  queda. Si la respuesta trae `de_otros_procedimientos`, esos ficheros no se tocan porque pueden
  ser de otra conversación en marcha: díselo al auditor en una línea. Si trae un `aviso` de
  ficheros que la herramienta no ha escrito (`no_escritos_por_mi`), dile la carpeta y que los
  mire si alguno es de hoy: una exportación lleva datos del cliente.
- **El directorio de trabajo `$TRABAJO` se borra entero, desde fuera** —no estás dentro, no
  hiciste `cd`—. Ahí están `pruebas.json`, `parametros.json`, `resumen.json`, `contexto.json` y
  `nia530.json`, que escribiste tú y `limpiar_exportaciones` no ve. Si algo no se deja borrar,
  dile al auditor la ruta: son datos del cliente y no pueden quedarse por olvido.

Di al auditor, en pocas líneas:

- dónde está el fichero, con la ruta completa, y la leyenda de tokens al lado
- el **modo**: con expediente de Gesia, o solo ForSampling
- cuántos elementos traía medidos el papel de `fsp-mum` (la línea del paso 3)
- **qué falta**, en una lista corta y con quién lo aporta: la ejecución de `fsp-mum`, el
  saldo contable por cuenta, la motivación y la conclusión; y que **el informe emitido por
  ForSampling se adjunta como anexo**, porque la proyección solo existe ahí
- si la prueba **no está finalizada** en ForSampling
- si hay **elementos sin documento**: el apartado 11 de la NIA manda tratarlos como
  incorrección salvo procedimiento alternativo, y eso lo decide el auditor
- que los nombres de los terceros **se han recuperado en su equipo**: N sustituciones, M
  terceros distintos, y los que hayan quedado sin nombre
- que el apartado de uso de IA deja constancia de la herramienta y de lo que se le facilitó, y
  que **la verificación, quién la hace, su efecto en la conclusión y la revisión están en blanco
  para el equipo**: mientras lo estén, el papel no es evidencia de auditoría
- que los temporales están borrados, o la ruta de lo que no se dejó borrar

Sin llamar «sellar» ni «rehidratar» a nada delante del auditor: para él es **dejar constancia del
uso de IA** y **recuperar los nombres**.

<!-- solo-cowork:papel-unico -->La copia del chat **siempre** está seudonimizada y sin sellar —viajó por el contenedor—: si la
mencionas, dilo, para que no la confunda con el papel archivado.<!-- /solo-cowork --> **El
diccionario de nombres no se borra**: vive con el encargo, cifrado, y es lo que permite recuperar
los nombres de un papel de hace días.

Y nada sobre si la prueba se supera. Eso no es de este papel.

---

## Lo que este skill no hace

- **No valida documentos** ni mide importes: es `fsp-mum`.
- **No proyecta, no compara con el error tolerable como conclusión, no concluye.** Y no
  transcribe nada de un PDF: el informe de ForSampling es un anexo, no una fuente.
- **No rellena lo que es del auditor**: afirmación, motivación, conciliación detallada, causa
  de los errores, anomalías y conclusión quedan en blanco salvo que él los haya dado.
- **No verifica su propio resultado por el equipo.** Propone qué contrastar; la verificación,
  quién la hace y su efecto en la conclusión los escribe el equipo en el apartado de uso de IA.
- **No escribe en ForSampling ni en Gesia.**
- **No abre el `.pcu` ni el `.smp` por su cuenta**: los agregados los da `resumen`, por el API.
- **No hace la prueba de cumplimiento** ni la circularización.

---

## Degradación

| Situación | Qué hace |
|---|---|
| El API no responde | `arrancar_api` y repite; solo si eso falla, se lo dice al auditor |
| `configurar` trae `aviso_otra_conversacion` | si el cambio fue de esta conversación (`fsp-mum` justo antes), sigue; si no, se lo dice al auditor tal cual y **no sigue** hasta que confirme que la otra ha terminado |
| Solo hay `.cli`, sin expediente de Gesia | modo `solo_fs`: lo de Gesia va PENDIENTE y el apartado 9 es la lista de lo que se solicita |
| La muestra llega sin seudonimizar | **para**: vuelve a `configurar(gs3_file=…, perfil="fsp-mum-nia530")` y exporta otra vez |
| El MCP es anterior a la 1.23.0 | sigue: confianza, factor, método, criterio y cuadre salen PENDIENTES, y se dice |
| No se ha ejecutado `fsp-mum` | sigue: importe según documento y error PENDIENTES; propón ejecutarlo |
| El papel de `fsp-mum` trae medidos menos de la mitad de los elementos | el constructor avisa «POCOS DOCUMENTOS MEDIDOS»: no genera el Word, propone volver a `fsp-mum`, y sigue solo si el auditor lo pide |
| La prueba no está finalizada | sigue y lo marca en ámbar en la portada y en los puntos abiertos |
| El `.smp` y el fichero de la prueba no cuadran | el constructor avisa y el generador no escribe sin `--forzar`: hay que entenderlo antes |
| Hay varias pruebas MUM | pregunta cuál |
| La prueba no es MUM | **para**: este papel es de la NIA-ES 530 para MUM |
| `sellar_uso_ia` dice que no hay huecos | el papel ya estaba sellado o no es el que escribió el script: no lo repitas, dilo |
| `sellar_uso_ia` dice que no tiene constancia de lo facilitado | o no se sirvió nada por el plugin, o el MCP se reinició a mitad: el papel lo dice y remite a `RegistroEmision.jsonl`; cuéntaselo al auditor tal cual |
| `rehidratar` devuelve `tokens_sin_nombre` | sigue: el papel se entrega con esos tokens tal cual y se dicen al auditor; no se completan a mano |

---

## Comprobar que el skill funciona

```bash
python "$SKILL/scripts/probar_nia530.py"
```

Exportaciones sintéticas con la forma exacta del MCP 1.23.0 —medida sobre una prueba real—,
constructor y generador de punta a punta, y las reglas que no pueden romperse: solo tokens en
el Word, unidades como suma de repeticiones, errores sin netear, proyección ni calculada ni
transcrita —el apartado 8 remite al informe emitido—, una muestra sin seudonimizar que para el
skill, y el apartado de uso de IA: los huecos de la aplicación, los del equipo en blanco y unas
comprobaciones que dicen «ATENCIÓN» cuando algo no cuadra. También el recuento de lo que trae
medido el papel de `fsp-mum` y su aviso cuando es menos de la mitad, `pruebas.json` reducido a
una fila, y que los scripts arrancan con `python -I` desde otra carpeta.
