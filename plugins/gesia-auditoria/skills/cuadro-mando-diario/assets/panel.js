"use strict";
const D = window.__PANEL__;
const NS = "http://www.w3.org/2000/svg";
const MESES = ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"];
const DIAS = ["lunes","martes","miércoles","jueves","viernes","sábado","domingo"];
const SEQ = ["--seq1","--seq2","--seq3","--seq4","--seq5","--seq6","--seq7"];

/* ---------------------------------------------------------------- formato --- */
const nf0 = new Intl.NumberFormat("es-ES", {maximumFractionDigits:0});
const nf1 = new Intl.NumberFormat("es-ES", {minimumFractionDigits:1, maximumFractionDigits:1});
const nf2 = new Intl.NumberFormat("es-ES", {minimumFractionDigits:2, maximumFractionDigits:2});
const eur  = v => nf0.format(Math.round(v)) + " €";
const eur2 = v => nf2.format(v) + " €";
function comp(v){
  const a = Math.abs(v);
  if (a >= 1e6) return nf1.format(v/1e6) + " M";
  if (a >= 1e3) return nf0.format(v/1e3) + " k";
  return nf0.format(v);
}
const pct = v => (v===null||v===undefined) ? "—" : nf1.format(v) + " %";
const fecha = s => s ? s.slice(8,10)+"/"+s.slice(5,7)+"/"+s.slice(0,4) : "";

/* ---------------------------------------------------------------- tooltip --- */
const tip = document.getElementById("tip");
function showTip(ev, titulo, filas){
  tip.textContent = "";
  const h = document.createElement("div"); h.className = "tt";
  h.textContent = titulo; tip.appendChild(h);
  filas.forEach(f => {
    const d = document.createElement("div"); d.className = "tr";
    if (f.color){ const k=document.createElement("i"); k.className="sw";
      k.style.background=f.color; d.appendChild(k); }
    const n = document.createElement("span"); n.className="tn"; n.textContent=f.name; d.appendChild(n);
    const v = document.createElement("span"); v.className="tv2"; v.textContent=f.value; d.appendChild(v);
    tip.appendChild(d);
  });
  tip.style.opacity="1"; tip.style.visibility="visible"; moveTip(ev);
}
function moveTip(ev){
  const b = tip.getBoundingClientRect();
  let x = ev.clientX+14, y = ev.clientY-10;
  if (x+b.width > innerWidth-8) x = ev.clientX-b.width-14;
  if (y+b.height > innerHeight-8) y = innerHeight-b.height-8;
  if (y < 8) y = 8;
  tip.style.left = x+"px"; tip.style.top = y+"px";
}
function hideTip(){ tip.style.opacity="0"; tip.style.visibility="hidden"; }
document.addEventListener("scroll", hideTip, true);
function hover(el, titulo, filas){
  el.addEventListener("pointerenter", e => showTip(e, titulo, filas));
  el.addEventListener("pointermove", moveTip);
  el.addEventListener("pointerleave", hideTip);
}

/* -------------------------------------------------------------- svg utils --- */
function el(t,a){ const e=document.createElementNS(NS,t); for(const k in a) e.setAttribute(k,a[k]); return e; }
function txt(x,y,s,cls,anchor){
  const t = el("text",{x,y,class:cls||"tick","text-anchor":anchor||"middle"});
  t.textContent = s; return t;
}
function barV(x,y,w,h,r){
  r = Math.min(r, w/2, Math.abs(h));
  if (h <= 0.5) return `M${x} ${y+h} h${w} v${-h} h${-w} Z`;
  return `M${x} ${y+h} V${y+r} Q${x} ${y} ${x+r} ${y} H${x+w-r} Q${x+w} ${y} ${x+w} ${y+r} V${y+h} Z`;
}
function barH(x,y,w,h,r){
  r = Math.min(r, h/2, Math.abs(w));
  if (w <= 0.5) return `M${x} ${y} h${w} v${h} h${-w} Z`;
  return `M${x} ${y} H${x+w-r} Q${x+w} ${y} ${x+w} ${y+r} V${y+h-r} Q${x+w} ${y+h} ${x+w-r} ${y+h} H${x} Z`;
}
function niceMax(v, pasos){
  pasos = pasos || 4;
  if (v <= 0) return 1;
  const bruto = v/pasos, mag = Math.pow(10, Math.floor(Math.log10(bruto))), n = bruto/mag;
  const C = [1,1.2,1.5,1.6,2,2.5,3,3.5,4,5,6,6.5,8,10];
  let m = 10; for (const c of C){ if (n <= c+1e-9){ m = c; break; } }
  return m*mag*pasos;
}
function mkSvg(id,w,h){
  const host = document.getElementById(id); host.textContent = "";
  const s = el("svg",{viewBox:`0 0 ${w} ${h}`,role:"img"}); host.appendChild(s); return s;
}
function cssv(n){ return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }

/* --------------------------------------------------------------- tablas --- */
function numEs(txt){
  // "1.234,56 €" -> 1234.56. Permite ordenar columnas numericas sin tener que
  // pasar el valor crudo desde cada sitio que construye una tabla.
  if (typeof txt === "number") return txt;
  const t = String(txt).replace(/[^\d,\-]/g, "").replace(/\./g, "").replace(",", ".");
  const v = parseFloat(t);
  return isNaN(v) ? -Infinity : v;
}
function textoDe(v){
  if (v === null || v === undefined) return "";
  if (v.html) return v.html.textContent || "";
  return String(v);
}
const ESTADO_TABLA = {};
function tabla(id, cols, filas, opts){
  opts = opts || {};
  const host = document.getElementById(id);
  const est = ESTADO_TABLA[id] || (ESTADO_TABLA[id] = {col:-1, dir:1, q:""});
  host.textContent = "";
  if (!filas.length){
    const e = document.createElement("div"); e.className="empty";
    e.textContent = "Sin datos en esta sección."; host.appendChild(e); return;
  }
  let vista = filas;
  if (est.q){
    const q = est.q.toLowerCase();
    vista = vista.filter(r => r.some(c => textoDe(c).toLowerCase().includes(q)));
  }
  if (est.col >= 0){
    const numerica = !!cols[est.col].n;
    vista = vista.slice().sort((a,b) => {
      const x = a[est.col], y = b[est.col];
      const va = numerica ? numEs(textoDe(x)) : textoDe(x).toLowerCase();
      const vb = numerica ? numEs(textoDe(y)) : textoDe(y).toLowerCase();
      return (va < vb ? -1 : va > vb ? 1 : 0) * est.dir;
    });
  }

  if (opts.buscar){
    const w = document.createElement("div"); w.className = "tsearch";
    const i = document.createElement("input"); i.type = "text";
    i.placeholder = "Buscar en la tabla…"; i.value = est.q;
    i.addEventListener("input", () => {
      est.q = i.value.trim();
      tabla(id, cols, filas, opts);
      const nuevo = host.querySelector(".tsearch input");
      if (nuevo){ nuevo.focus(); nuevo.setSelectionRange(est.q.length, est.q.length); }
    });
    w.appendChild(i); host.appendChild(w);
  }

  const t = document.createElement("table");
  const th = document.createElement("thead"), tr = document.createElement("tr");
  cols.forEach((c,i) => {
    const e = document.createElement("th");
    if (c.n) e.className = "n";
    e.textContent = c.t + (est.col === i ? (est.dir > 0 ? " ▲" : " ▼") : "");
    if (opts.orden !== false && c.t){
      e.classList.add("srt");
      e.addEventListener("click", () => {
        if (est.col === i) est.dir = -est.dir; else { est.col = i; est.dir = 1; }
        tabla(id, cols, filas, opts);
      });
    }
    tr.appendChild(e);
  });
  th.appendChild(tr); t.appendChild(th);
  const tb = document.createElement("tbody");
  vista.forEach(r => {
    const x = document.createElement("tr");
    r.forEach((v,i) => {
      const d = document.createElement("td");
      if (cols[i].n) d.className = "n";
      if (v && v.html){ d.appendChild(v.html.cloneNode(true)); }
      else { d.textContent = v === null ? "—" : String(v); }
      if (cols[i].wrap){ d.style.whiteSpace = "normal"; d.style.minWidth = "220px"; }
      x.appendChild(d);
    });
    tb.appendChild(x);
  });
  t.appendChild(tb); host.appendChild(t);
  if (est.q && vista.length !== filas.length){
    const p = document.createElement("div"); p.className = "empty";
    p.style.padding = "8px"; p.style.fontSize = "11.5px";
    p.textContent = `${vista.length} de ${filas.length} filas`;
    host.appendChild(p);
  }
}
function tablaB(id, cols, filas){ tabla(id, cols, filas, {orden:true, buscar:true}); }
function badge(texto, clase){
  const s = document.createElement("span"); s.className = "est "+clase; s.textContent = texto;
  return {html:s};
}
document.querySelectorAll(".tbtn[data-tv]").forEach(b => {
  b.addEventListener("click", () => {
    const t = document.getElementById(b.dataset.tv);
    b.setAttribute("aria-pressed", t.classList.toggle("on") ? "true" : "false");
  });
});

/* ================================================================ filtros == */
const F = {m1:1, m2:12, estado:"", cuenta:""};

function mesesSel(){
  const nombres = ["Enero","Febrero","Marzo","Abril","Mayo","Junio","Julio",
    "Agosto","Septiembre","Octubre","Noviembre","Diciembre"];
  [["fM1","m1"],["fM2","m2"]].forEach(([id,k]) => {
    const sel = document.getElementById(id);
    if (sel.options.length) return;
    nombres.forEach((n2,i) => {
      const o = document.createElement("option"); o.value = i+1; o.textContent = n2;
      sel.appendChild(o);
    });
    sel.value = F[k];
    sel.addEventListener("change", () => {
      F[k] = +sel.value;
      if (F.m2 < F.m1){ F.m2 = F.m1; document.getElementById("fM2").value = F.m2; }
      actividad();
    });
  });
  document.querySelectorAll("[data-tri]").forEach(b => {
    if (b.dataset.listo) return; b.dataset.listo = "1";
    b.addEventListener("click", () => {
      const t = +b.dataset.tri;
      F.m1 = t ? (t-1)*3+1 : 1; F.m2 = t ? t*3 : 12;
      document.getElementById("fM1").value = F.m1;
      document.getElementById("fM2").value = F.m2;
      actividad();
    });
  });
}
function enRango(mes){ return mes >= F.m1 && mes <= F.m2; }
function filtrosConc(){
  const e = document.getElementById("fEstado"), c = document.getElementById("fCuenta");
  if (!e.dataset.listo){
    e.dataset.listo = "1";
    e.addEventListener("change", () => { F.estado = e.value; conciliacion(); });
    c.addEventListener("input", () => { F.cuenta = c.value.trim(); conciliacion(); });
  }
  e.value = F.estado; c.value = F.cuenta;
}

/* ================================================================ cabecera == */
function cabecera(){
  const m = D.meta, r = D.resultado;
  document.getElementById("eyebrow").textContent =
    `Procedimientos analíticos · Diario contable · Cierre ${fecha(m.cierre)}`;
  document.getElementById("titulo").textContent = m.cliente;
  document.getElementById("subtitulo").textContent =
    `${nf0.format(m.apuntes)} apuntes y ${nf0.format(m.asientos)} asientos sobre `
    + `${nf0.format(m.cuentas)} cuentas, analizados apunte a apunte y conciliados `
    + `contra los saldos del expediente.`;

  const sello = document.getElementById("sello");
  const campos = [
    ["Fichero del diario", m.fichero],
    ["Apuntes", nf0.format(m.apuntes)],
    ["Importancia relativa (IR_T)", m.ir_t ? eur(m.ir_t) : "no indicada"],
    ["Contrato del diario", m.veredicto_contrato],
    ["Generado", m.generado],
  ];
  campos.forEach(([k,v]) => {
    const d = document.createElement("div");
    const s = document.createElement("span"); s.textContent = k; d.appendChild(s);
    const b = document.createElement("b"); b.textContent = v; d.appendChild(b);
    sello.appendChild(d);
  });
  const d = document.createElement("div");
  const s = document.createElement("span"); s.textContent = "Opciones de importación"; d.appendChild(s);
  [["apertura", m.opciones.apertura],["punteo", m.opciones.punteo],
   ["aging", m.opciones.aging_publicable]].forEach(([n,v]) => {
    const p = document.createElement("span");
    p.className = "pill " + (v ? "si" : "no");
    p.textContent = (v ? "✓ " : "✕ ") + n;
    p.style.marginRight = "5px";
    d.appendChild(p);
  });
  sello.appendChild(d);

  /* --- hero --- */
  const hero = document.getElementById("hero");
  const izq = document.createElement("div");
  izq.innerHTML = "";
  const lab = document.createElement("div"); lab.className="lab";
  lab.textContent = "Resultado del ejercicio (cuenta 08)";
  const fig = document.createElement("div"); fig.className="fig";
  fig.textContent = eur(r.diario);
  const nota = document.createElement("div"); nota.className="note";
  if (r.gesia_08 !== null && r.cuadra){
    nota.textContent = "Coincide al céntimo con la cuenta 08 del expediente: "
      + "el diario analizado es el que sostiene los saldos.";
  } else if (r.gesia_08 !== null){
    nota.textContent = "No coincide con la cuenta 08 del expediente ("
      + eur(r.gesia_08) + "): revisar antes de usar este panel.";
  } else {
    nota.textContent = "Calculado como ingresos menos gastos: el diario no trae "
      + "asiento de regularización.";
  }
  izq.append(lab, fig, nota); hero.appendChild(izq);

  const kpis = document.createElement("div"); kpis.className="kpis";
  const varAnt = (r.anterior && r.anterior !== 0)
    ? ((r.diario / r.anterior - 1) * 100) : null;
  const items = [
    ["Ejercicio anterior", r.anterior !== null ? eur(r.anterior) : "—",
     varAnt !== null ? (varAnt >= 0 ? "+" : "") + nf0.format(varAnt) + " % de variación" : ""],
    ["Ajustes de auditoría", r.ajustes !== null ? eur(r.ajustes) : "—",
     (r.ajustes !== null && D.meta.ir_t)
       ? nf0.format(Math.abs(r.ajustes)/D.meta.ir_t*100) + " % de IR_T" : ""],
    ["Resultado tras ajustes", r.auditoria !== null ? eur(r.auditoria) : "—",
     "Saldo de auditoría de la 08"],
    ["Volumen movido", eur(D.meta.volumen_neto), "Medido en neto (Debe − Haber)"],
    ["Conciliación con Gesia", D.conciliacion
       ? nf1.format(D.conciliacion.pct_volumen_conciliado) + " %" : "—",
     D.conciliacion ? D.conciliacion.resumen.materiales + " descuadres materiales" : ""],
    ["Ingresos / gastos", comp(r.ingresos) + " / " + comp(r.gastos),
     "Grupos 7 y 6 del PGC"],
  ];
  items.forEach(([k,v,d2]) => {
    const c = document.createElement("div"); c.className="kpi";
    const a = document.createElement("div"); a.className="k"; a.textContent=k;
    const b = document.createElement("div"); b.className="v"; b.textContent=v;
    const e = document.createElement("div"); e.className="d"; e.textContent=d2;
    c.append(a,b,e); kpis.appendChild(c);
  });
  hero.appendChild(kpis);
}

/* ======================================================== hechos relevantes == */
const SEV = {
  critico:  ["Crítico",  "var(--crit)"],
  alto:     ["Alto",     "var(--serious)"],
  medio:    ["Medio",    "var(--warn)"],
  bajo:     ["Bajo",     "var(--s1)"],
  correcto: ["Correcto", "var(--good)"],
};
function hechos(){
  const H = D.hechos || [];
  const host = document.getElementById("finds"); host.textContent = "";
  const cnt = document.getElementById("cnt-hechos");
  const por = {};
  H.forEach(h => { por[h.severidad] = (por[h.severidad]||0)+1; });
  cnt.textContent = "— " + Object.keys(SEV).filter(k => por[k])
    .map(k => `${por[k]} ${SEV[k][0].toLowerCase()}`).join(" · ");
  cnt.style.color = "var(--muted)";
  cnt.style.fontWeight = "500";
  cnt.style.fontSize = "13px";

  H.forEach(h => {
    const c = document.createElement("article");
    c.className = "find " + h.severidad;
    const b = document.createElement("div"); b.className = "badge";
    const dot = document.createElement("i"); dot.style.background = SEV[h.severidad][1];
    b.append(dot, document.createTextNode(SEV[h.severidad][0] + " · " + h.categoria));
    c.appendChild(b);
    const t = document.createElement("h3"); t.textContent = h.titulo; c.appendChild(t);
    h.parrafos.forEach(p => {
      const e = document.createElement("p");
      // Los generadores marcan enfasis con **...**; se convierte a <b> sin
      // pasar por innerHTML con texto no controlado.
      p.split(/(\*\*[^*]+\*\*)/g).forEach(tr => {
        if (tr.startsWith("**") && tr.endsWith("**")){
          const s2 = document.createElement("b");
          s2.textContent = tr.slice(2,-2); e.appendChild(s2);
        } else if (tr) e.appendChild(document.createTextNode(tr));
      });
      c.appendChild(e);
    });
    if (h.cifras.length){
      const ch = document.createElement("div"); ch.className = "chips";
      h.cifras.forEach(x => {
        const s2 = document.createElement("span"); s2.className = "chip";
        s2.textContent = x; ch.appendChild(s2);
      });
      c.appendChild(ch);
    }
    if (h.ancla){
      const a = document.createElement("div"); a.className = "act";
      const link = document.createElement("a"); link.href = "#" + h.ancla;
      link.textContent = "Ver la sección →"; a.appendChild(link);
      c.appendChild(a);
    }
    host.appendChild(c);
  });
}

/* ---------------------------------------------------------------- avisos --- */
function aviso(host, clase, titulo, texto){
  const d = document.createElement("div"); d.className = "aviso " + clase;
  const t = document.createElement("span"); t.className="t"; t.textContent=titulo;
  d.appendChild(t);
  const p = document.createElement("div"); p.textContent = texto;
  d.appendChild(p);
  document.getElementById(host).appendChild(d);
  return d;
}

/* =========================================================== conciliación == */
function conciliacion(){
  const C = D.conciliacion;
  const host = document.getElementById("lede-conc");
  if (!C){ host.textContent = "No se ha aportado el plan de cuentas del expediente: "
    + "el diario no se ha podido conciliar."; return; }
  host.textContent = "Se compara el neto del diario por grupo de cuenta con el saldo "
    + "del cliente en el expediente. Las cuentas que Gesia calcula y el diario no lleva "
    + "se excluyen y se listan aparte.";

  const R = C.resumen;
  if (R.materiales){
    aviso("avisos-conc","crit","No concilia",
      `${R.materiales} grupos descuadran por encima del umbral de materialidad `
      + `(${eur(C.umbral_trivial)}). El panel no debe publicarse sin resolverlos.`);
  } else if (R.triviales){
    aviso("avisos-conc","","Concilia con diferencias triviales",
      `${R.triviales} grupos descuadran por debajo de ${eur(C.umbral_trivial)}.`);
  } else {
    aviso("avisos-conc","ok","Concilia",
      `${R.conformes} grupos coinciden al céntimo y ${R.conformes_saldo_cero} más `
      + `tienen movimiento con saldo cero al cierre. Ningún descuadre. `
      + `${nf1.format(C.pct_volumen_conciliado)} % del volumen del diario queda cubierto.`);
  }

  /* barras horizontales de los mayores saldos, coloreadas por estado */
  filtrosConc();
  const coincide = g => {
    if (F.estado && !g.estado.startsWith(F.estado)) return false;
    if (F.cuenta){
      const q = F.cuenta.toLowerCase();
      if (!(g.cuenta+" "+(g.nombre||"")).toLowerCase().includes(q)) return false;
    }
    return true;
  };
  const visibles = C.grupos.filter(coincide);
  document.getElementById("estadoConc").innerHTML =
    `<b>${nf0.format(visibles.length)}</b> de ${nf0.format(C.grupos.length)} grupos`;
  const filas = visibles.filter(g => Math.abs(g.gesia) > 0 || Math.abs(g.diario) > 0)
    .sort((a,b) => Math.abs(b.gesia||b.diario) - Math.abs(a.gesia||a.diario)).slice(0,14);
  const W=620, fh=26, PL=210, PR=70, PT=6, H=PT+filas.length*fh+8;
  const svg = mkSvg("ch-conc", W, H);
  const max = Math.max(1, ...filas.map(f => Math.abs(f.gesia||f.diario)));
  const colorEstado = e => e.startsWith("DESCUADRE") ? "var(--crit)"
    : e.startsWith("descuadre") ? "var(--warn)"
    : e === "calculada por Gesia" ? "var(--muted)" : "var(--s1)";
  filas.forEach((f,i) => {
    const y = PT+i*fh, bh = 16, v = Math.abs(f.gesia||f.diario);
    const w = (W-PL-PR)*v/max;
    const nom = (f.nombre || f.cuenta).slice(0,30);
    svg.appendChild(txt(PL-10, y+bh/2+4, f.cuenta+" "+nom, "tick", "end"));
    svg.appendChild(el("path",{d:barH(PL,y+2,w,bh,4), fill:colorEstado(f.estado)}));
    svg.appendChild(txt(PL+w+7, y+bh/2+4, comp(f.gesia||f.diario)+" €", "dlab", "start"));
    const hit = el("rect",{x:0,y,width:W,height:fh,class:"hit"});
    hover(hit, f.cuenta+" · "+(f.nombre||""), [
      {name:"Saldo en el diario", value:eur2(f.diario)},
      {name:"Saldo en Gesia", value:eur2(f.gesia)},
      {name:"Diferencia", value:eur2(f.dif)},
      {name:"Estado", value:f.estado},
      {name:"Apuntes", value:nf0.format(f.apuntes)},
    ]);
    svg.appendChild(hit);
  });
  document.getElementById("cs-conc").innerHTML =
    `Los <b>${filas.length}</b> grupos de mayor saldo, de ${C.resumen.grupos} comparados. `
    + `La longitud mide la magnitud del saldo y el signo va en la etiqueta; `
    + `el color indica el estado de la conciliación.`;
  const lg = document.getElementById("lg-conc");
  [["var(--s1)","Conforme"],["var(--warn)","Descuadre trivial"],
   ["var(--crit)","Descuadre material"],["var(--muted)","Calculada por Gesia"]]
   .forEach(([c,t]) => {
    const s = document.createElement("span");
    const i = document.createElement("i"); i.className="sw"; i.style.background=c;
    s.append(i, document.createTextNode(t)); lg.appendChild(s);
  });
  tablaB("tv-conc",
    [{t:"Cuenta"},{t:"Nombre",wrap:1},{t:"Diario",n:1},{t:"Gesia",n:1},
     {t:"Diferencia",n:1},{t:"Apuntes",n:1},{t:"Estado"}],
    visibles.map(g => [g.cuenta, g.nombre||"", eur2(g.diario), eur2(g.gesia),
      eur2(g.dif), nf0.format(g.apuntes),
      badge(g.estado.startsWith("DESCUADRE") ? "material"
        : g.estado.startsWith("descuadre") ? "trivial"
        : g.estado === "calculada por Gesia" ? "calculada" : "conforme",
        g.estado.startsWith("DESCUADRE") ? "mat"
        : g.estado.startsWith("descuadre") ? "triv"
        : g.estado === "calculada por Gesia" ? "calc" : "ok")]));

  /* ajustes de auditoría */
  const aj = visibles.filter(g => Math.abs(g.ajuste) > 0.01)
    .sort((a,b) => Math.abs(b.ajuste) - Math.abs(a.ajuste));
  if (!aj.length){
    document.getElementById("ch-conc-vacio");
    document.getElementById("cs-aj").textContent =
      "El expediente no tiene ajustes de auditoría propuestos sobre estas cuentas.";
    mkSvg("ch-aj", 10, 10);
    tablaB("tv-aj", [{t:"—"}], []);
    return;
  }
  const A = aj.slice(0,12);
  const W2=620, fh2=26, PL2=196, PR2=96, PT2=6, H2=PT2+A.length*fh2+8;
  const s2 = mkSvg("ch-aj", W2, H2);
  const max2 = Math.max(...A.map(a => Math.abs(a.ajuste)));
  const cx = PL2 + (W2-PL2-PR2)/2;
  s2.appendChild(el("line",{x1:cx,x2:cx,y1:PT2,y2:H2-8,stroke:"var(--axis)","stroke-width":1}));
  A.forEach((a,i) => {
    const y = PT2+i*fh2, bh=16;
    const w = ((W2-PL2-PR2)/2)*Math.abs(a.ajuste)/max2;
    const neg = a.ajuste < 0;
    const x = neg ? cx-w : cx;
    s2.appendChild(txt(PL2-10, y+bh/2+4,
      a.cuenta+" "+(a.nombre||"").slice(0,26), "tick", "end"));
    s2.appendChild(el("path",{d:barH(x,y+2,w,bh,4), fill: neg ? "var(--s2)" : "var(--s1)"}));
    // La etiqueta va SIEMPRE en la columna de la derecha. Colgada del extremo
    // de la barra, las negativas se solapaban con el nombre de la cuenta.
    s2.appendChild(txt(W2-PR2+82, y+bh/2+4, comp(a.ajuste)+" €", "dlab", "end"));
    const hit = el("rect",{x:0,y,width:W2,height:fh2,class:"hit"});
    hover(hit, a.cuenta+" · "+(a.nombre||""), [
      {name:"Ajuste propuesto", value:eur2(a.ajuste)},
      {name:"Saldo del cliente", value:eur2(a.gesia)},
      {name:"% de IR_T", value: D.meta.ir_t
        ? nf1.format(Math.abs(a.ajuste)/D.meta.ir_t*100)+" %" : "—"},
    ]);
    s2.appendChild(hit);
  });
  // Los ajustes de auditoria netean a cero por construccion (cada asiento de
  // ajuste cuadra), asi que el neto no informa de nada. La cifra util es el
  // importe movido: la mitad de la suma de valores absolutos.
  const movido = aj.reduce((s,a) => s+Math.abs(a.ajuste), 0) / 2;
  const neto = aj.reduce((s,a) => s+a.ajuste, 0);
  document.getElementById("cs-aj").innerHTML =
    `<b>${aj.length}</b> cuentas con ajuste propuesto, por un importe de `
    + `<b>${eur(movido)}</b>`
    + (D.meta.ir_t ? ` (${nf0.format(movido/D.meta.ir_t*100)} % de IR_T)` : "")
    + `. A la izquierda del eje, los que reducen el saldo. `
    + (Math.abs(neto) < 1
       ? `El neto es cero porque cada asiento de ajuste cuadra por sí mismo.`
       : `Efecto neto sobre los saldos: ${eur(neto)}.`);
  tablaB("tv-aj", [{t:"Cuenta"},{t:"Nombre",wrap:1},{t:"Saldo cliente",n:1},
    {t:"Ajuste",n:1},{t:"% IR_T",n:1}],
    aj.map(a => [a.cuenta, a.nombre||"", eur2(a.gesia), eur2(a.ajuste),
      D.meta.ir_t ? nf1.format(Math.abs(a.ajuste)/D.meta.ir_t*100)+" %" : "—"]));
}

/* ============================================================== actividad == */
function actividad(){
  const A = D.diario;
  mesesSel();
  document.getElementById("lede-act").textContent =
    "Los picos se miden contra la línea base del propio cliente, no contra reglas "
    + "universales: lo que se marca es el día que se sale de la distribución de su "
    + "mismo día de la semana. El nivel absoluto —cuánto se contabiliza en fin de "
    + "semana, por ejemplo— se informa aparte y su interpretación es del auditor.";

  /* --- mensual --- */
  const M = A.mensual.filter(m => enRango(m.mes));
  const W=620,H=250,PL=58,PR=14,PT=16,PB=30;
  const svg = mkSvg("ch-mes", W, H);
  const max = niceMax(Math.max(...M.map(m => m.volumen)));
  const x0=PL,x1=W-PR,y0=PT,y1=H-PB,ph=y1-y0,bw=(x1-x0)/M.length;
  for (let k=0;k<=4;k++){
    const y = y1-ph*k/4;
    svg.appendChild(el("line",{x1:x0,x2:x1,y1:y,y2:y,stroke:"var(--grid)","stroke-width":1}));
    svg.appendChild(txt(x0-8,y+3.5,comp(max*k/4),"tick","end"));
  }
  svg.appendChild(el("line",{x1:x0,x2:x1,y1:y1,y2:y1,stroke:"var(--axis)","stroke-width":1}));
  const bwid = Math.min(24, bw-8);
  const maxMes = M.reduce((a,b) => b.volumen > a.volumen ? b : a, M[0]);
  M.forEach((m,i) => {
    const h = ph*m.volumen/max, cx = x0+bw*i+bw/2;
    svg.appendChild(el("path",{d:barV(cx-bwid/2, y1-h, bwid, h, 4), fill:"var(--s1)"}));
    if (m === maxMes) svg.appendChild(txt(cx, y1-h-6, comp(m.volumen), "dlab"));
    svg.appendChild(txt(cx, y1+16, MESES[m.mes-1], "tick"));
    const hit = el("rect",{x:x0+bw*i,y:y0,width:bw,height:ph,class:"hit"});
    hover(hit, MESES[m.mes-1], [
      {name:"Volumen", value:eur(m.volumen), color:cssv("--s1")},
      {name:"Apuntes", value:nf0.format(m.apuntes)},
      {name:"Asientos", value:nf0.format(m.asientos)},
      {name:"% del año", value:nf1.format(m.pct_volumen)+" %"},
    ]);
    svg.appendChild(hit);
  });
  document.getElementById("estadoAct").innerHTML =
    (F.m1 === 1 && F.m2 === 12)
      ? `Todo el ejercicio · <b>${nf0.format(M.reduce((s2,m)=>s2+m.apuntes,0))}</b> apuntes`
      : `${MESES[F.m1-1]}–${MESES[F.m2-1]} · <b>`
        + `${nf0.format(M.reduce((s2,m)=>s2+m.apuntes,0))}</b> apuntes`;
  document.getElementById("cs-mes").innerHTML =
    `Máximo en <b>${MESES[maxMes.mes-1]}</b> con ${eur(maxMes.volumen)} `
    + `(${nf1.format(maxMes.pct_volumen)} % del año).`;
  tabla("tv-mes", [{t:"Mes"},{t:"Apuntes",n:1},{t:"Asientos",n:1},{t:"Volumen",n:1},{t:"% año",n:1}],
    M.map(m => [MESES[m.mes-1], nf0.format(m.apuntes), nf0.format(m.asientos),
      eur2(m.volumen), nf1.format(m.pct_volumen)+" %"]));

  /* --- perfil semanal, recalculado sobre el rango ----------------------
     Se reconstruye desde la serie diaria en vez de usar el agregado anual:
     asi el filtro de meses alcanza tambien a este cuadro. */
  const acum = Array.from({length:7}, () => ({apuntes:0, asientos:0, volumen:0}));
  A.serie_diaria.filter(d => enRango(+d.fecha.slice(5,7))).forEach(d => {
    const a = acum[d.dow];
    a.apuntes += d.apuntes; a.asientos += d.asientos; a.volumen += d.volumen;
  });
  const P = acum.map((a,i) => ({dia: DIAS[i], ...a}));
  const W2=620,H2=250,PL2=52,PR2=14,PT2=20,PB2=30;
  const s2 = mkSvg("ch-dow", W2, H2);
  const totalAp = P.reduce((s,p) => s+p.apuntes, 0);
  const max2 = niceMax(Math.max(...P.map(p => p.apuntes)));
  const a0=PL2,a1=W2-PR2,b0=PT2,b1=H2-PB2,ph2=b1-b0,bw2=(a1-a0)/P.length;
  for (let k=0;k<=4;k++){
    const y=b1-ph2*k/4;
    s2.appendChild(el("line",{x1:a0,x2:a1,y1:y,y2:y,stroke:"var(--grid)","stroke-width":1}));
    s2.appendChild(txt(a0-8,y+3.5,nf0.format(max2*k/4),"tick","end"));
  }
  s2.appendChild(el("line",{x1:a0,x2:a1,y1:b1,y2:b1,stroke:"var(--axis)","stroke-width":1}));
  P.forEach((p,i) => {
    const fin = i >= 5, h = ph2*p.apuntes/max2, cx = a0+bw2*i+bw2/2;
    const bwid2 = Math.min(24, bw2-10);
    s2.appendChild(el("path",{d:barV(cx-bwid2/2, b1-h, bwid2, h, 4),
      fill: fin ? "var(--s2)" : "var(--s1)"}));
    s2.appendChild(txt(cx, b1-h-6, nf0.format(p.apuntes), "dlab"));
    s2.appendChild(txt(cx, b1+16, p.dia.slice(0,3), "tick"));
    const hit = el("rect",{x:a0+bw2*i,y:b0,width:bw2,height:ph2,class:"hit"});
    hover(hit, p.dia, [
      {name:"Apuntes", value:nf0.format(p.apuntes), color: fin?cssv("--s2"):cssv("--s1")},
      {name:"Asientos", value:nf0.format(p.asientos)},
      {name:"Volumen", value:eur(p.volumen)},
      {name:"% de apuntes", value:nf1.format(p.apuntes/totalAp*100)+" %"},
    ]);
    s2.appendChild(hit);
  });
  const fds = P[5].apuntes + P[6].apuntes;
  const fuerte = P.reduce((a,b) => b.apuntes > a.apuntes ? b : a, P[0]);
  document.getElementById("cs-dow").innerHTML =
    `<b>${nf0.format(fds)}</b> apuntes en fin de semana (${nf1.format(fds/totalAp*100)} %). `
    + `El día fuerte es el <b>${fuerte.dia}</b>, con ${nf1.format(fuerte.apuntes/totalAp*100)} % `
    + `de los apuntes. El panel describe el patrón, no lo juzga: si no encaja con la `
    + `actividad del cliente, <b>esta distribución es en sí misma el hallazgo</b>.`;
  tabla("tv-dow", [{t:"Día"},{t:"Apuntes",n:1},{t:"Asientos",n:1},{t:"Volumen",n:1}],
    P.map(p => [p.dia, nf0.format(p.apuntes), nf0.format(p.asientos), eur2(p.volumen)]));

  calendario();
  tipos();
}

/* ------------------------------------------------------------ calendario --- */
function calendario(){
  const S = D.diario.serie_diaria.filter(d => enRango(+d.fecha.slice(5,7)));
  const porFecha = new Map(S.map(d => [d.fecha, d]));
  const vals = S.map(d => d.apuntes).sort((a,b) => a-b);
  const cortes = [1,2,3,4,5,6].map(k => vals[Math.floor(vals.length*k/7)]);
  const paso = n => { for (let k=0;k<cortes.length;k++) if (n <= cortes[k]) return k; return 6; };

  const anio = S.length ? +S[0].fecha.slice(0,4) : 2025;
  const W=1240, cell=18, gap=3, PL=34, PT=20, dias=31, H=PT+12*(cell+gap)+8;
  const svg = mkSvg("ch-cal", W, H);
  const cw = (W-PL-14)/dias;
  for (let d=1; d<=dias; d++) if (d%2===1) svg.appendChild(txt(PL+cw*(d-0.5), PT-7, String(d), "tick"));
  let atip = 0;
  for (let m=0;m<12;m++){
    const y = PT+m*(cell+gap);
    svg.appendChild(txt(PL-8, y+cell/2+3.5, MESES[m], "tick", "end"));
    for (let d=1; d<=dias; d++){
      const ds = `${anio}-${String(m+1).padStart(2,"0")}-${String(d).padStart(2,"0")}`;
      const dt = new Date(ds+"T00:00:00");
      if (dt.getMonth() !== m) continue;
      const info = porFecha.get(ds);
      const x = PL+cw*(d-1), wd = cw-gap;
      let fill = "var(--surface)", stroke = "var(--grid)", sw = 1;
      if (info){ fill = `var(${SEQ[paso(info.apuntes)]})`; stroke = "transparent"; }
      if (info && info.z !== null){ stroke = "var(--s2)"; sw = 2; atip++; }
      const rc = el("rect",{x,y,width:wd,height:cell,rx:3,fill,stroke,"stroke-width":sw,class:"hm-cell"});
      const filas = info
        ? [{name:"Apuntes", value:nf0.format(info.apuntes)},
           {name:"Asientos", value:nf0.format(info.asientos)},
           {name:"Volumen", value:eur(info.volumen)}]
        : [{name:"Sin movimiento", value:"—"}];
      if (info && info.z !== null) filas.push({name:"⚠ Actividad anómala", value:"z = "+nf1.format(info.z)});
      if (info && info.fin_de_mes) filas.push({name:"Cierre de mes", value:"sí"});
      hover(rc, fecha(ds), filas);
      svg.appendChild(rc);
    }
  }
  const lg = document.getElementById("lg-cal"); lg.textContent = "";
  const l1 = document.createElement("span"); l1.textContent = "Menos apuntes"; lg.appendChild(l1);
  SEQ.forEach(v => { const i=document.createElement("i"); i.className="sw";
    i.style.background=`var(${v})`; i.style.width="18px"; lg.appendChild(i); });
  const l2 = document.createElement("span"); l2.textContent = "Más apuntes"; lg.appendChild(l2);
  const l3 = document.createElement("span");
  const b = document.createElement("i"); b.className="sw"; b.style.background="transparent";
  b.style.border = "2px solid var(--s2)";
  l3.append(b, document.createTextNode("Día con actividad anómala"));
  lg.appendChild(l3);

  const DA = D.diario.dias_atipicos || [];
  const fdm = DA.filter(d => d.fin_de_mes).length;
  document.getElementById("cs-cal").innerHTML =
    `Cada celda es un día; el color mide el número de apuntes sobre `
    + `<b>${nf0.format(S.length)}</b> días con movimiento. Los <b>${DA.length}</b> días `
    + `marcados se salen de la distribución de su propio día de la semana, y `
    + `<b>${fdm}</b> de ellos son el último día natural del mes: el cliente concentra `
    + `trabajo en el cierre mensual. Los ${DA.length-fdm} restantes son los que piden explicación.`;
  tablaB("tv-cal", [{t:"Fecha"},{t:"Día"},{t:"Apuntes",n:1},{t:"Asientos",n:1},
    {t:"Volumen",n:1},{t:"z",n:1},{t:"Cierre de mes"}],
    S.map(d => [fecha(d.fecha), DIAS[d.dow], nf0.format(d.apuntes),
      nf0.format(d.asientos), eur2(d.volumen),
      d.z === null ? "—" : nf1.format(d.z), d.fin_de_mes ? "sí" : ""]));
}

/* ----------------------------------------------------------------- tipos --- */
function tipos(){
  // Reagregado desde el desglose mensual para que el filtro le alcance.
  const PM = (D.diario.tipos_por_mes||[]).filter(x => enRango(x.mes));
  const acc = {};
  PM.forEach(x => {
    const a = acc[x.tipo] || (acc[x.tipo] = {tipo:x.tipo, apuntes:0, asientos:0, volumen:0});
    a.apuntes += x.apuntes; a.asientos += x.asientos; a.volumen += x.volumen;
  });
  let T = Object.values(acc).sort((a,b) => b.volumen - a.volumen);
  const totV = T.reduce((s2,t) => s2+t.volumen, 0) || 1;
  T.forEach(t => t.pct_volumen = t.volumen/totV*100);
  if (!T.length) T = D.diario.tipos_asiento;
  const W=1240, fh=26, PL=230, PR=90, PT=6, H=PT+T.length*fh+8;
  const svg = mkSvg("ch-tipo", W, H);
  const max = Math.max(...T.map(t => t.volumen));
  T.forEach((t,i) => {
    const y = PT+i*fh, bh=16, w=(W-PL-PR)*t.volumen/max;
    svg.appendChild(txt(PL-10, y+bh/2+4, t.tipo, "tick", "end"));
    svg.appendChild(el("path",{d:barH(PL,y+2,w,bh,4), fill:"var(--s1)"}));
    svg.appendChild(txt(PL+w+7, y+bh/2+4,
      comp(t.volumen)+" €  ·  "+nf1.format(t.pct_volumen)+" %", "dlab", "start"));
    const hit = el("rect",{x:0,y,width:W,height:fh,class:"hit"});
    hover(hit, t.tipo, [
      {name:"Volumen", value:eur(t.volumen), color:cssv("--s1")},
      {name:"Asientos", value:nf0.format(t.asientos)},
      {name:"Apuntes", value:nf0.format(t.apuntes)},
      {name:"% del volumen", value:nf1.format(t.pct_volumen)+" %"},
    ]);
    svg.appendChild(hit);
  });
  document.getElementById("cs-tipo").innerHTML =
    "Deducido de <b>qué grupos del PGC toca cada asiento en cada lado</b>, no del texto "
    + "del concepto: en un diario real el concepto es intratable. Un asiento que carga "
    + "un 6 y abona un 40 es una compra, escriba el ERP lo que quiera.";
  tabla("tv-tipo", [{t:"Tipo"},{t:"Asientos",n:1},{t:"Apuntes",n:1},{t:"Volumen",n:1},{t:"%",n:1}],
    T.map(t => [t.tipo, nf0.format(t.asientos), nf0.format(t.apuntes),
      eur2(t.volumen), nf1.format(t.pct_volumen)+" %"]));
}

/* ================================================================= punteo == */
function punteo(){
  const P = D.punteo;
  const host = document.getElementById("bloque-punteo");
  document.getElementById("lede-punt").textContent =
    "El punteo de Gesia empareja las líneas que se cancelan entre sí. De ahí salen el "
    + "plazo real de liquidación y la antigüedad de lo que queda abierto. Es un "
    + "artefacto de un algoritmo, no evidencia contable: lo que sigue es una lista de "
    + "revisión, no una conclusión.";

  if (!P || !P.punteo){
    aviso("avisos-punt","","Sin punteo",
      (P && P.motivo ? P.motivo + ". " : "")
      + "La opción de punteo no se activó al importar el diario en Gesia. Reimportar "
      + "con ella activada añade los plazos de liquidación y la antigüedad de partidas "
      + "abiertas.");
    return;
  }
  const R = P.resumen;
  if (!P.aging_publicable){
    aviso("avisos-punt","crit","Antigüedad suprimida",
      "Hay punteo pero no hay apertura verificada. Los pagos que cancelan facturas del "
      + "ejercicio anterior se quedan sin contrapartida y aparecerían como abiertos, de "
      + "modo que la antigüedad estaría sobreestimada de forma sistemática.");
  }
  if (R.punteos_masivos){
    aviso("avisos-punt","","Punteos masivos excluidos",
      `${R.punteos_masivos} grupos absorben más de la mitad de las líneas de su cuenta: `
      + "no son emparejamientos de partidas, sino la cuenta neteándose consigo misma, y "
      + "su «plazo» es solo la duración del ejercicio. Se excluyen de los plazos, pero "
      + "sus líneas sí cuentan como canceladas para la antigüedad.");
  }

  /* plazos */
  const PL_ = (P.plazos||[]).filter(p => p.muestra_suficiente);
  const c1 = document.createElement("div"); c1.className="grid g2";
  c1.innerHTML = `
    <div class="card">
      <header><h3>Plazos de liquidación por grupo</h3>
        <button class="tbtn" data-tv="tv-plazos" aria-pressed="false">⊞ datos</button></header>
      <p class="cs" id="cs-plazos"></p>
      <div class="legend">
        <span><i class="sw" style="background:var(--s1)"></i>Mediana</span>
        <span><i class="sw" style="background:var(--s3)"></i>Hasta el percentil 90</span></div>
      <div id="ch-plazos"></div><div class="tv" id="tv-plazos"></div>
    </div>
    <div class="card">
      <header><h3>Cobertura del punteo</h3>
        <button class="tbtn" data-tv="tv-cob" aria-pressed="false">⊞ datos</button></header>
      <p class="cs" id="cs-cob"></p>
      <div id="ch-cob"></div><div class="tv" id="tv-cob"></div>
    </div>`;
  host.appendChild(c1);
  document.querySelectorAll(".tbtn[data-tv]").forEach(b => {
    if (b.dataset.listo) return; b.dataset.listo = "1";
    b.addEventListener("click", () => {
      const t = document.getElementById(b.dataset.tv);
      b.setAttribute("aria-pressed", t.classList.toggle("on") ? "true" : "false");
    });
  });

  const A = PL_.slice(0,10);
  const W=620, fh=27, PL0=70, PR=64, PT=8, H=PT+A.length*fh+22;
  const svg = mkSvg("ch-plazos", W, H);
  const max = niceMax(Math.max(1, ...A.map(a => a.p90)));
  const x0=PL0, x1=W-PR;
  const sx = v => x0 + (x1-x0)*v/max;
  for (let k=0;k<=4;k++){
    const x = sx(max*k/4);
    svg.appendChild(el("line",{x1:x,x2:x,y1:PT,y2:H-22,stroke:"var(--grid)","stroke-width":1}));
    svg.appendChild(txt(x, H-8, nf0.format(max*k/4)+" d", "tick"));
  }
  A.forEach((a,i) => {
    const y = PT+i*fh+9;
    svg.appendChild(txt(PL0-10, y+4, a.grupo, "tick", "end"));
    svg.appendChild(el("line",{x1:sx(0),x2:sx(a.p90),y1:y,y2:y,
      stroke:"var(--s3)","stroke-width":4,"stroke-linecap":"round"}));
    svg.appendChild(el("circle",{cx:sx(a.mediana),cy:y,r:5,fill:"var(--s1)",
      stroke:"var(--surface)","stroke-width":2}));
    svg.appendChild(txt(x1+7, y+4, nf0.format(a.mediana)+" d", "dlab", "start"));
    const hit = el("rect",{x:0,y:y-11,width:W,height:fh,class:"hit"});
    hover(hit, "Grupo "+a.grupo, [
      {name:"Partidas", value:nf0.format(a.grupos)},
      {name:"Mediana", value:nf0.format(a.mediana)+" días", color:cssv("--s1")},
      {name:"Media", value:nf1.format(a.media)+" días"},
      {name:"Percentil 90", value:nf0.format(a.p90)+" días", color:cssv("--s3")},
      {name:"Máximo", value:nf0.format(a.maximo)+" días"},
      {name:"Importe", value:eur(a.importe)},
    ]);
    svg.appendChild(hit);
  });
  document.getElementById("cs-plazos").innerHTML =
    `Días desde el primer movimiento de cada partida hasta su cancelación, `
    + `<b>según el punteo automático de Gesia</b>. Solo grupos con al menos `
    + `${P.min_partidas||5} partidas.`;
  tablaB("tv-plazos", [{t:"Grupo"},{t:"Partidas",n:1},{t:"Mediana",n:1},{t:"Media",n:1},
    {t:"P90",n:1},{t:"Máximo",n:1},{t:"Importe",n:1}],
    (P.plazos||[]).map(a => [a.grupo, nf0.format(a.grupos), nf0.format(a.mediana),
      nf1.format(a.media), nf0.format(a.p90), nf0.format(a.maximo), eur2(a.importe)]));

  /* cobertura */
  const CB = (P.cobertura||[]).filter(c => c.lineas >= 30).slice(0,10);
  const W3=620, fh3=24, PL3=64, PR3=104, PT3=6, H3=PT3+CB.length*fh3+8;
  const s3 = mkSvg("ch-cob", W3, H3);
  const u = P.umbral_cobertura;
  const anchoBar = W3-PL3-PR3;
  const xu = PL3 + anchoBar*u/100;
  s3.appendChild(el("line",{x1:xu,x2:xu,y1:PT3,y2:H3-8,stroke:"var(--s7)","stroke-width":2}));
  s3.appendChild(txt(xu, PT3-1, "umbral "+nf0.format(u)+" %", "dlab", "middle"));
  CB.forEach((c,i) => {
    const y = PT3+i*fh3+6, bh=14, w = anchoBar*c.pct_cancelado/100;
    const ok = c.pct_cancelado >= u;
    s3.appendChild(txt(PL3-10, y+bh/2+4, c.grupo, "tick", "end"));
    s3.appendChild(el("path",{d:barH(PL3,y+2,w,bh,4),
      fill: ok ? "var(--s1)" : "var(--warn)"}));
    s3.appendChild(txt(PL3+anchoBar+8, y+bh/2+4,
      nf1.format(c.pct_cancelado)+" %  ("+nf0.format(c.lineas)+" líneas)", "dlab", "start"));
    const hit = el("rect",{x:0,y:y-3,width:W3,height:fh3,class:"hit"});
    hover(hit, "Grupo "+(c.grupo), [
      {name:"Cancelado", value:nf1.format(c.pct_cancelado)+" %"},
      {name:"En partidas emparejadas", value:nf1.format(c.pct_partidas)+" %"},
      {name:"Líneas", value:nf0.format(c.lineas)},
      {name:"En punteo masivo", value:nf0.format(c.en_masivos)},
    ]);
    s3.appendChild(hit);
  });
  document.getElementById("cs-cob").innerHTML =
    `Porcentaje de líneas canceladas por el punteo. Por debajo del `
    + `<b>${nf0.format(u)} %</b>, «no punteado» no equivale a «pendiente» y la `
    + `antigüedad se muestra <b>sin cifra de cabecera</b>.`;
  tablaB("tv-cob", [{t:"Grupo"},{t:"Líneas",n:1},{t:"Cancelado",n:1},
    {t:"En partidas",n:1},{t:"En masivos",n:1}],
    (P.cobertura||[]).map(c => [c.grupo, nf0.format(c.lineas),
      nf1.format(c.pct_cancelado)+" %", nf1.format(c.pct_partidas)+" %",
      nf0.format(c.en_masivos)]));

  aging(host);
}

/* ------------------------------------------------------------------ aging --- */
function aging(host){
  const P = D.punteo;
  const AG = P.aging || [];
  if (!P.aging_publicable || !AG.length) return;
  const card = document.createElement("div"); card.className = "card";
  card.style.marginTop = "14px";
  card.innerHTML = `<header><h3>Antigüedad de las partidas abiertas</h3>
      <button class="tbtn" data-tv="tv-ag" aria-pressed="false">⊞ datos</button></header>
    <p class="cs" id="cs-ag"></p><div class="legend" id="lg-ag"></div>
    <div id="ch-ag"></div><div class="tv" id="tv-ag"></div>`;
  host.appendChild(card);
  card.querySelector(".tbtn").addEventListener("click", ev => {
    const b = ev.currentTarget, t = document.getElementById(b.dataset.tv);
    b.setAttribute("aria-pressed", t.classList.toggle("on") ? "true" : "false");
  });

  const suf = new Set(P.resumen.grupos_cobertura_suficiente || []);
  const tramos = [];
  AG.forEach(a => { if (!tramos.includes(a.tramo)) tramos.push(a.tramo); });
  const orden = t => {
    const i = ["0-30","31-60","61-90","91-180","181-365",">365","de apertura (>365)"].indexOf(t);
    return i < 0 ? 99 : i;
  };
  tramos.sort((a,b) => orden(a)-orden(b));
  const saldoDe = {};
  AG.forEach(a => { saldoDe[a.grupo] = (saldoDe[a.grupo]||0) + Math.abs(a.neto); });
  const todos = Object.keys(saldoDe).sort((a,b) => saldoDe[b]-saldoDe[a]);
  const grupos = todos.slice(0,10);
  const omitidos = todos.length - grupos.length;

  const W=1240, fh=34, PL=96, PR=150, PT=10, H=PT+grupos.length*fh+10;
  const svg = mkSvg("ch-ag", W, H);
  const porGrupo = g => AG.filter(a => a.grupo === g);
  const maxAbs = Math.max(...grupos.map(g =>
    porGrupo(g).reduce((s,a) => s+Math.abs(a.neto), 0)));
  const ancho = W-PL-PR;
  grupos.forEach((g,i) => {
    const y = PT+i*fh, bh = 18;
    const filas = porGrupo(g).sort((a,b) => orden(a.tramo)-orden(b.tramo));
    const total = filas.reduce((s,a) => s+a.neto, 0);
    const conCifra = suf.has(g);
    svg.appendChild(txt(PL-10, y+bh/2+4, g, "tick", "end"));
    let x = PL;
    filas.forEach(a => {
      const w = ancho*Math.abs(a.neto)/maxAbs;
      if (w > 0.5){
        svg.appendChild(el("path",{d:barH(x, y+2, Math.max(w-2,0.5), bh, 3),
          fill:`var(${SEQ[Math.min(6, orden(a.tramo)+1)]})`}));
      }
      const hit = el("rect",{x, y, width:Math.max(w,2), height:fh, class:"hit"});
      hover(hit, "Grupo "+g+" · "+a.tramo, [
        {name:"Apuntes", value:nf0.format(a.apuntes)},
        {name:"Neto", value:eur2(a.neto)},
      ]);
      svg.appendChild(hit);
      x += w;
    });
    svg.appendChild(txt(PL+ancho+8, y+bh/2+4,
      conCifra ? eur(total) : "sin cifra de cabecera", "dlab", "start"));
  });
  const lg = document.getElementById("lg-ag"); lg.textContent = "";
  tramos.forEach(t => {
    const s = document.createElement("span");
    const i = document.createElement("i"); i.className="sw";
    i.style.background = `var(${SEQ[Math.min(6, orden(t)+1)]})`;
    s.append(i, document.createTextNode(t)); lg.appendChild(s);
  });
  const sinCifra = grupos.filter(g => !suf.has(g));
  document.getElementById("cs-ag").innerHTML =
    `Antigüedad de las líneas sin cancelar al cierre, por tramos. `
    + (sinCifra.length
       ? `Los grupos <b>${sinCifra.join(", ")}</b> no alcanzan el `
         + `${nf0.format(P.umbral_cobertura)} % de cobertura, así que se muestra su `
         + `distribución pero <b>no su saldo como cifra</b>: ahí «no punteado» puede `
         + `significar simplemente que nadie lo punteó.`
       : `Todos los grupos superan el umbral de cobertura.`)
    + ` El tramo «de apertura» agrupa lo que viene del ejercicio anterior, cuya `
    + `antigüedad real es mayor que la calculada.`
    + (omitidos > 0 ? ` Se omiten ${omitidos} grupos de saldo menor; están en la tabla.`
                    : "");
  tablaB("tv-ag", [{t:"Grupo"},{t:"Tramo"},{t:"Apuntes",n:1},{t:"Neto",n:1},{t:"Cifra publicable"}],
    AG.map(a => [a.grupo, a.tramo, nf0.format(a.apuntes), eur2(a.neto),
      suf.has(a.grupo) ? "sí" : "no"]));
}

/* =============================================================== atípicos == */
function atipicos(){
  const A = D.diario.atipicos;
  const host = document.getElementById("bloque-atipicos");
  document.getElementById("lede-atip").textContent =
    "Excluido el asiento de apertura, que no son transacciones sino saldos iniciales. "
    + "Los umbrales se anclan a la importancia relativa del encargo.";

  const bloques = [];

  bloques.push({
    t: "Apuntes de importe superior a la importancia relativa",
    cs: `<b>${A.materiales}</b> apuntes por encima de `
        + (D.meta.ir_t ? eur(D.meta.ir_t) : "IR_T") + ". Cada uno es, por sí solo, "
        + "material para el encargo.",
    cols: [{t:"Fecha"},{t:"Asiento"},{t:"Cuenta"},{t:"Tercero"},
           {t:"Concepto",wrap:1},{t:"Importe",n:1}],
    filas: (A.materiales_detalle||[]).map(r =>
      [fecha(r.FECHA), r.ASIENTO, r.CUENTA, r.NOMBRE || "", r.CONCEPTO || "",
       eur2(r.VOL)]),
  });

  bloques.push({
    t: "Contrapartidas que apenas se repiten",
    cs: "Combinaciones de grupos del PGC que aparecen una o dos veces en todo el "
        + "ejercicio. Suelen ser el préstamo, el ajuste de existencias o la operación "
        + "singular del año.",
    cols: [{t:"Debe"},{t:"Haber"},{t:"Veces",n:1},{t:"Mayor asiento",n:1},{t:"Ejemplo"}],
    filas: (A.contrapartidas_raras||[]).map(r =>
      [r.debe, r.haber, nf0.format(r.veces), eur2(r.importe_mayor_asiento), r.ejemplo]),
  });

  const DA = (D.diario.dias_atipicos||[]).filter(d => !d.fin_de_mes);
  bloques.push({
    t: "Días anómalos que no son cierre de mes",
    cs: `De los ${(D.diario.dias_atipicos||[]).length} días que se salen de su propia `
        + `distribución, estos <b>${DA.length}</b> no coinciden con el último día del mes.`,
    cols: [{t:"Fecha"},{t:"Día"},{t:"Apuntes",n:1},{t:"Mediana del día",n:1},{t:"z",n:1}],
    filas: DA.map(d => [fecha(d.fecha), DIAS[d.DOW], nf0.format(d.apuntes),
      nf0.format(d.mediana), nf1.format(d.z)]),
  });

  bloques.forEach((b,i) => {
    const c = document.createElement("div"); c.className="card";
    if (i) c.style.marginTop = "14px";
    const h = document.createElement("header");
    const h3 = document.createElement("h3"); h3.textContent = b.t; h.appendChild(h3);
    c.appendChild(h);
    const p = document.createElement("p"); p.className="cs"; p.innerHTML = b.cs;
    c.appendChild(p);
    const d = document.createElement("div"); d.className="tv always";
    d.id = "tv-atip-"+i; c.appendChild(d);
    host.appendChild(c);
    tablaB("tv-atip-"+i, b.cols, b.filas);
  });

  /* --- apuntes marcados --- */
  const MK = A.marcados || {totales:{}, apuntes:[]};
  if ((MK.apuntes||[]).length){
    const c = document.createElement("div"); c.className="card"; c.style.marginTop="14px";
    const h = document.createElement("header");
    const h3 = document.createElement("h3"); h3.textContent = "Apuntes marcados";
    h.appendChild(h3); c.appendChild(h);
    const p = document.createElement("p"); p.className="cs";
    const tot = Object.entries(MK.totales)
      .map(([k,v]) => `<b>${nf0.format(v.apuntes)}</b> ${k}`).join(", ");
    const excede = Object.values(MK.totales).some(v => v.apuntes > MK.tope_por_marca);
    p.innerHTML = `Recuento completo: ${tot}. `
      + (excede
         ? `La tabla muestra <b>las ${nf0.format(MK.tope_por_marca)} de mayor importe `
           + `de cada marca</b>: volcarlas todas no cabría ni se leería. El recuento de `
           + `arriba es el completo, y es el que dice si una marca es una excepción o `
           + `el modo de operar del cliente.`
         : `Caben todas en la tabla.`);
    c.appendChild(p);
    const d = document.createElement("div"); d.className="tv always";
    d.id = "tv-marcados"; c.appendChild(d);
    host.appendChild(c);
    const clase = m => m === "fin de semana" ? "fds"
      : m === "importe redondo" ? "red"
      : m === "duplicado" ? "dup" : "mat";
    tablaB("tv-marcados",
      [{t:"Fecha"},{t:"Día"},{t:"Asiento"},{t:"Cuenta"},{t:"Tercero"},
       {t:"Concepto",wrap:1},{t:"Importe",n:1},{t:"Marcas"}],
      MK.apuntes.map(r => {
        const cont = document.createElement("span");
        r.marcas.forEach(m => {
          const s2 = document.createElement("span");
          s2.className = "marca " + clase(m);
          s2.textContent = m === "fin de semana" ? "FIN DE SEMANA"
            : m === "importe redondo" ? "REDONDO"
            : m === "duplicado" ? "DUPLICADO" : "SUPERA IR_T";
          cont.appendChild(s2);
        });
        return [fecha(r.fecha), DIAS[r.dow], r.asiento, r.cuenta, r.nombre,
                r.concepto, eur2(r.importe), {html:cont}];
      }));
  }

  /* indicadores sueltos */
  const c = document.createElement("div"); c.className="card"; c.style.marginTop="14px";
  const rd = A.redondos, bf = A.benford, cc = A.cierre;
  const partes = [];
  partes.push(`<b>Importes redondos.</b> ${nf0.format(rd.apuntes)} apuntes múltiplos de `
    + `1.000 € sobre ${nf0.format(rd.sobre_apuntes_de_mas_de_mil)} de más de 1.000 € `
    + `(${nf1.format(rd.pct)} %).`);
  if (bf.aplicable){
    partes.push(`<b>Ley de Benford.</b> Desviación media absoluta ${nf2.format(bf.mad*1000)}‰ `
      + `sobre ${nf0.format(bf.importes)} importes: ajuste <b>${bf.ajuste}</b>. `
      + `El dígito ${bf.digitos_mas_desviados[0].digito} aparece en el `
      + `${nf1.format(bf.digitos_mas_desviados[0].observado_pct)} % de los casos frente al `
      + `${nf1.format(bf.digitos_mas_desviados[0].esperado_pct)} % esperado. `
      + `La no conformidad no es por sí misma un indicio de manipulación: en un negocio `
      + `con importes repetidos es frecuente. Es una pregunta que hacer, no una conclusión.`);
  }
  partes.push(`<b>Concentración en el cierre.</b> Los últimos días del ejercicio `
    + `(desde ${fecha(cc.desde)}) reúnen ${nf0.format(cc.apuntes)} apuntes `
    + `(${nf1.format(cc.pct_apuntes)} %) y el ${nf1.format(cc.pct_volumen)} % del volumen.`);
  partes.push(`<b>Duplicados exactos.</b> ${nf0.format(A.duplicados)} grupos de apuntes `
    + `idénticos el mismo día en la misma cuenta por encima del umbral de interés.`);
  c.innerHTML = "<header><h3>Otros indicadores</h3></header>"
    + partes.map(p => `<p class="cs" style="margin-bottom:9px">${p}</p>`).join("");
  host.appendChild(c);
}

/* =============================================================== contrato == */
function contrato(){
  const H = (D.contrato && D.contrato.hallazgos) || [];
  const orden = {ABORTA:0, AVISO:1, INFO:2, OK:3};
  const filas = H.slice().sort((a,b) =>
      (orden[a.nivel]-orden[b.nivel]) || a.codigo.localeCompare(b.codigo))
    .map(h => [
      badge(h.nivel === "OK" ? "ok" : h.nivel.toLowerCase(),
            h.nivel === "ABORTA" ? "mat" : h.nivel === "AVISO" ? "triv"
            : h.nivel === "OK" ? "ok" : "calc"),
      h.codigo, h.texto]);
  tablaB("tv-contrato", [{t:"Nivel"},{t:"Código"},{t:"Comprobación",wrap:1}], filas);
}

/* ==================================================================== pie == */
function pie(){
  const m = D.meta;
  document.getElementById("pie").innerHTML =
    `Elaborado a partir de <b>${m.fichero}</b> (${nf0.format(m.apuntes)} apuntes, `
    + `${nf0.format(m.asientos)} asientos, ${nf0.format(m.cuentas)} cuentas) y de los `
    + `saldos del expediente de Gesia. Todos los importes en euros, medidos en neto `
    + `(Debe − Haber). El diario no registra hora ni usuario, así que no es posible `
    + `analizar el registro fuera de horario ni por operador. `
    + `Los plazos de liquidación y la antigüedad de partidas proceden del punteo `
    + `automático de Gesia y son una lista de revisión, no una medida contable. `
    + `Panel generado el ${m.generado}; su contenido depende de las opciones de `
    + `importación selladas en la cabecera.`;
}

/* ==================================================================== tema == */
document.getElementById("temaBtn").addEventListener("click", () => {
  const r = document.documentElement;
  r.dataset.theme = r.dataset.theme === "dark" ? "light" : "dark";
  render();
});
if (window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches)
  document.documentElement.dataset.theme = "dark";

function render(){
  document.getElementById("sello").textContent = "";
  document.getElementById("hero").textContent = "";
  document.getElementById("avisos-conc").textContent = "";
  document.getElementById("avisos-punt").textContent = "";
  document.getElementById("bloque-punteo").textContent = "";
  document.getElementById("bloque-atipicos").textContent = "";
  document.getElementById("finds").textContent = "";
  cabecera(); hechos(); conciliacion(); actividad(); punteo(); atipicos(); contrato(); pie();
}
render();
