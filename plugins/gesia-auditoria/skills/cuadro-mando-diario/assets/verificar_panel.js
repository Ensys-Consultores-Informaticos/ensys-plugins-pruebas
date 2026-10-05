// Comprobacion del panel antes de entregarlo.
//
// El validador de datos no ve la maquetacion: un grafico puede salirse de su
// tarjeta, una etiqueta puede solaparse con otra y los JSON seguiran siendo
// correctos. Esto abre el fichero de verdad, recoge los errores de consola y
// deja una captura para mirarla.
//
// Uso:  node verificar_panel.js <ruta.html> [<prefijo-capturas>]

const { chromium } = require("playwright");

(async () => {
  const ruta = process.argv[2];
  const prefijo = process.argv[3] || "panel";
  if (!ruta) {
    console.error("uso: node verificar_panel.js <ruta.html> [prefijo]");
    process.exit(2);
  }

  const navegador = await chromium.launch({
    executablePath: "/opt/pw-browsers/chromium",
  });
  const pagina = await navegador.newPage({ viewport: { width: 1400, height: 1100 } });

  const errores = [];
  pagina.on("pageerror", (e) => errores.push("PAGEERROR: " + e.message));
  pagina.on("console", (m) => { if (m.type() === "error") errores.push(m.text()); });

  await pagina.goto("file://" + ruta, { waitUntil: "load" });
  await pagina.waitForTimeout(1800);

  // Comprobaciones estructurales: que las piezas esperadas existan de verdad.
  const estado = await pagina.evaluate(() => ({
    hechos: document.querySelectorAll("#finds .find").length,
    graficos: document.querySelectorAll("svg").length,
    tablas: document.querySelectorAll("table").length,
    filtros: document.querySelectorAll(".filtros select, .filtros input").length,
    vacios: [...document.querySelectorAll("svg")].filter(s => !s.children.length).length,
    alto: document.body.scrollHeight,
  }));

  const alturaVentana = 1100;
  const paginas = Math.min(10, Math.ceil(estado.alto / alturaVentana));
  for (let i = 0; i < paginas; i++) {
    await pagina.evaluate((y) => window.scrollTo(0, y), i * alturaVentana);
    await pagina.waitForTimeout(300);
    await pagina.screenshot({ path: `${prefijo}_${i + 1}.png` });
  }

  // Y el modo oscuro, que tiene su propia rampa y se rompe por separado.
  await pagina.evaluate(() => window.scrollTo(0, 0));
  await pagina.click("#temaBtn");
  await pagina.waitForTimeout(900);
  await pagina.screenshot({ path: `${prefijo}_oscuro.png` });

  console.log("tarjetas de hechos :", estado.hechos);
  console.log("graficos           :", estado.graficos, estado.vacios ? `(${estado.vacios} VACIOS)` : "");
  console.log("tablas             :", estado.tablas);
  console.log("controles de filtro:", estado.filtros);
  console.log("alto               :", estado.alto, "px");
  console.log("capturas           :", paginas, "+ oscuro");
  console.log("errores de consola :", errores.length ? errores.join("\n") : "ninguno");

  await navegador.close();

  const mal = errores.length > 0 || estado.vacios > 0 || estado.hechos === 0;
  process.exit(mal ? 1 : 0);
})();
