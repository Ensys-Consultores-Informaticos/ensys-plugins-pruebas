# Plugins de Ensys para Claude — canal de PRUEBAS

**Esto no es para clientes.** Es el marketplace donde Ensys prueba las versiones beta del
los plugins `gesia-auditoria` y `forsampling-auditoria` antes de publicarlas en el canal de
producción, [`ensys-plugins`](https://github.com/Ensys-Consultores-Informaticos/ensys-plugins).
Lo que hay aquí puede cambiar sin aviso y puede tener defectos.

## Instalar para probar

1. **Desactiva el plugin de producción** (`gesia-auditoria` del marketplace `ensys`) en
   Configuración > Plugins. Los dos declaran el mismo servidor MCP y las mismas
   herramientas: con ambos activos no se sabe cuál contesta.
2. Añade el marketplace de pruebas: `Ensys-Consultores-Informaticos/ensys-plugins-pruebas`
   (aparece como **`ensys-pruebas`**).
3. Instala **uno** de los dos, y reinicia Claude del todo:
   - **Gesia — Expediente de auditoría (PRUEBAS)** si tienes la suite de Gesia. Ya incluye
     las pruebas de muestreo de ForSampling.
   - **ForSampling — Pruebas de muestreo (PRUEBAS)** si solo tienes ForSampling.

   **Nunca los dos**: comparten el programa que lee los ficheros, y con los dos activos no se
   sabe cuál contesta. Si pasa, `configurar()` lo avisa y dice cuál sobra.
4. La descripción del plugin termina en `(PRUEBAS · MCP X.Y.Z) (vA.B.C)`: el primero es el
   programa que lee el expediente y el segundo, el plugin. Son las versiones que tienes.

Para volver a producción: desactiva o desinstala este, reactiva el de `ensys` y reinicia.

## Qué se prueba ahora

Lo que haya aquí es una versión candidata del plugin, por delante de la de producción. **Puede
cambiar sin aviso y puede tener defectos.**

La versión instalada y la del programa que lee el expediente salen en la ficha del plugin, y
`configurar()` las dice también al empezar una sesión. Qué trae cada candidata se acuerda con
quien la va a probar: no se publica aquí.

Si algo falla, el propio plugin trae un **registro de ejecución** que lo resume de forma
anónima —pídelo con «cómo ha ido»— y que es la mejor manera de reportarlo.

## Requisitos

Los mismos que el canal de producción: Windows, y Gesia o ForSampling instalado. Para el
diario hace falta el driver de Access de 64 bits. El servidor API lo arranca el propio plugin si no responde; a mano
sigue estando en *Herramientas > Gesia - Cuadro de mando > Arrancar servidor API*.
