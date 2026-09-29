'use strict';
const DATA = JSON.parse(document.getElementById('datos-resultados').textContent);
const $ = id => document.getElementById(id);
const esc = v => String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money = v => v == null ? 'No disponible' : new Intl.NumberFormat('es-AR',{minimumFractionDigits:2,maximumFractionDigits:2}).format(v/100);
const qty = v => new Intl.NumberFormat('es-AR',{maximumFractionDigits:4}).format(v);
const sum = (rs, key) => rs.reduce((a,r)=>a+(r[key]||0),0);
const records = new Map(DATA.registros.map(r=>[r.id,r]));
const excluidos = DATA.excluidos || [];
const MESES = ['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic'];
const COLORS = ['#107c82','#173349','#c39732','#a8621c','#5b8c5a','#7a5195','#d45087','#2f6f9f','#8a6d3b','#4c9f70','#93313d','#3b6fb6'];
const table = (head, body) => '<div class="scroll"><table><thead><tr>'+head.map(h=>'<th>'+esc(h)+'</th>').join('')+'</tr></thead><tbody>'+body+'</tbody></table></div>';
const num = v => '<td class="num">'+money(v)+'</td>';
const norm = v => String(v||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toUpperCase();
const labelMes = m => m === 'Sin fecha' ? m : (MESES[+m.slice(5,7)-1] + ' ' + m.slice(2,4));
let currentLines = [], currentRecords = [], currentExcluded = [],
    articleRows = [], articleVisible = [], articleLines = new Map(),
    timelineMonths = [], timelineVisible = [], collapsed = new Set();
const claveEmp = e => 'E:' + e.empresa;
const claveGrp = e => 'G:' + e.empresa + ' § ' + e.grupo;

function inRange(r){
  const from = $('desde').value, to = $('hasta').value;
  if(from && (!r.fecha || r.fecha < from)) return false;
  if(to && (!r.fecha || r.fecha > to)) return false;
  return true;
}
function disclosure(title, rows, detailFactory){
  const el=document.createElement('details');const s=document.createElement('summary');s.textContent=title;el.append(s);
  el.addEventListener('toggle',()=>{if(el.open&&!el.dataset.loaded){const body=document.createElement('div');body.innerHTML=detailFactory(rows);el.append(body);el.dataset.loaded='1'}});
  return el;
}
function recordTable(rows){
  return table(['Registro','Fecha','Referencia / cliente','Estado','Empresa (cuenta)','Neto cabecera','Fuera de producto terminado','Motivo'],rows.map(r=>'<tr><td>'+r.id+'</td><td>'+esc(r.fecha)+'</td><td>'+esc(r.referencia)+'<br><small>'+esc(r.cliente)+'</small></td><td>'+esc(r.estado)+'<br><small>flujo '+esc(r.flujo)+' · estado '+esc(r.estado_id)+'</small></td><td>'+esc(r.empresa)+'</td>'+num(r.neto)+num(r.neto_pt != null ? r.neto_pt : null)+'<td>'+esc(r.motivo||'')+'</td></tr>').join(''));
}
function lineTable(rows){
  return table(['Registro / línea','Fecha','Empresa','Artículo / categoría','Cantidad','Neto sin IVA','Total','Alícuota'],rows.map(b=>{const r=records.get(b.registro_id);return '<tr><td>'+r.id+' / '+b.linea_id+'</td><td>'+esc(r.fecha)+'</td><td>'+esc(b.empresa)+'</td><td>'+esc(b.articulo)+'<br><small>'+esc(b.categoria)+'</small></td><td class="num">'+qty(b.cantidad)+'</td>'+num(b.neto)+num(b.total)+'<td>'+esc(b.alicuota)+'</td></tr>'}).join(''));
}

function applyFilters(){
  const from=$('desde').value, to=$('hasta').value, empresa=$('empresa').value;
  const invalid=from&&to&&from>to;
  $('error').hidden=!invalid;
  $('error').textContent=invalid?'La fecha desde no puede ser posterior a la fecha hasta. Corregí el rango.':'';
  if(invalid){currentLines=[];currentRecords=[];currentExcluded=[];return}
  currentLines=DATA.lineas.filter(b=>{const r=records.get(b.registro_id);
    return r&&inRange(r)&&(!empresa||b.empresa===empresa)});
  const ids=new Set(currentLines.map(b=>b.registro_id));
  currentRecords=DATA.registros.filter(r=>ids.has(r.id));
  currentExcluded=excluidos.filter(r=>inRange(r));
}

function buildArticleRows(){
  const modo=$('agrupar').value;
  const map=new Map(); articleLines=new Map();
  currentLines.forEach(b=>{
    const r=records.get(b.registro_id);
    const grupo=modo==='mes'?(r.fecha?r.fecha.slice(0,7):'Sin fecha'):(b.categoria||'Sin categoría');
    const key=[b.empresa,grupo,b.articulo,'ID '+b.articulo_id].join(' § ');
    let e=map.get(key);
    if(!e){e={key:key,empresa:b.empresa,grupo:grupo,art:b.articulo,um:b.unidad||'',artId:b.articulo_id,unidades:0,revisar:0,ventas:0,renglones:0,meses:new Set(),comps:new Set()};map.set(key,e)}
    if(!articleLines.has(key))articleLines.set(key,[]);
    articleLines.get(key).push(b);
    if(b.cantidad_venta===null)e.revisar++;else e.unidades+=b.cantidad_venta||0;
    e.ventas+=b.neto||0; e.renglones++;
    e.meses.add(r.fecha?r.fecha.slice(0,7):'Sin fecha'); e.comps.add(b.registro_id);
  });
  return [...map.values()].filter(e=>e.ventas!==0||e.unidades);
}
const unitsText = rows => {
  let u=0,rev=0;
  rows.forEach(e=>{u+=e.unidades;rev+=e.revisar});
  let out=qty(u);
  if(rev)out+=' <small class="rev">('+rev+' a revisar)</small>';
  return out;
};
function renderArticles(){
  const target=$('article-table'), note=$('article-note');
  const q=$('articulo').value.trim().toLocaleLowerCase('es'), modo=$('agrupar').value;
  const rows=articleRows.filter(e=>!q||(e.empresa+' § '+e.grupo+' § '+e.art+' [ID '+e.artId+']').toLocaleLowerCase('es').includes(q));
  articleVisible=rows;
  if(!rows.length){target.innerHTML='<p class="empty">Sin productos terminados vendidos para la selección.</p>';note.textContent='';$('contraer').textContent='Contraer todo';$('contraer').disabled=true;return}
  $('contraer').disabled=false;
  rows.sort((a,b)=>a.empresa.localeCompare(b.empresa,'es')||a.grupo.localeCompare(b.grupo,'es')||b.ventas-a.ventas||a.art.localeCompare(b.art,'es'));
  const total=rs=>rs.reduce((s,e)=>({u:s.u+e.unidades,v:s.v+e.ventas}),{u:0,v:0});
  const cobertura=rs=>{const m=new Set(),c=new Set();rs.forEach(e=>{e.meses.forEach(v=>m.add(v));e.comps.forEach(v=>c.add(v))});return{meses:m.size,comps:c.size}};
  const prom=(v,n)=>n>0?money(v/n):'—';
  const compTot=new Map(),grpTot=new Map();
  rows.forEach(e=>{const ck=e.empresa,gk=ck+' § '+e.grupo;
    [[compTot,ck],[grpTot,gk]].forEach(([m,k])=>{const v=m.get(k)||{rows:[]};v.rows.push(e);m.set(k,v)})});
  let html='<div class="scroll"><table id="sales-table" class="flat"><thead><tr><th>'+(modo==='mes'?'Mes / Artículo':'Categoría / Artículo')+'</th><th class="num">Unidades vendidas</th><th class="num">Importe sin IVA</th><th class="num">Ticket prom.</th><th class="num">Prom. mensual</th></tr></thead>';
  let comp=null,grp=null,open=false;
  rows.forEach((e,i)=>{
    const ocultaEmp=collapsed.has(claveEmp(e)), ocultaGrp=ocultaEmp||collapsed.has(claveGrp(e));
    if(e.empresa!==comp){if(open){html+='</tbody>';open=false}comp=e.empresa;grp=null;
      const rowsC=compTot.get(comp).rows,t=total(rowsC),cov=cobertura(rowsC);
      html+='<tbody class="company"><tr class="empresa" data-emp="'+esc(e.empresa)+'" title="Clic para contraer o mostrar la empresa"><td>EMPRESA: '+esc(comp)+'</td><td class="num">'+unitsText(rowsC)+'</td><td class="num">'+money(t.v)+'</td><td class="num">'+prom(t.v,cov.comps)+'</td><td class="num">'+prom(t.v,cov.meses)+'</td></tr></tbody>'}
    if(e.grupo!==grp){if(open){html+='</tbody>';open=false}grp=e.grupo;
      const rowsG=grpTot.get(comp+' § '+grp).rows,t=total(rowsG),cov=cobertura(rowsG);
      if(!ocultaEmp){html+='<tbody class="grupo"><tr class="grp" data-grp="'+esc(e.empresa+' § '+e.grupo)+'" title="Clic para contraer o mostrar la categoría"><td>'+(modo==='mes'?'MES: ':'CATEGORÍA: ')+esc(grp)+'</td><td class="num">'+unitsText(rowsG)+'</td><td class="num">'+money(t.v)+'</td><td class="num">'+prom(t.v,cov.comps)+'</td><td class="num">'+prom(t.v,cov.meses)+'</td></tr>';open=true}}
    if(ocultaGrp)return;
    html+='<tr class="art"><td><span class="art-name" title="'+esc(e.art+' [ID '+e.artId+']'+(e.um?' · '+e.um:''))+'">'+esc(e.art)+' <small>[ID '+e.artId+']'+(e.um?' · '+esc(e.um):'')+'</small></span> <button class="ghost" data-i="'+i+'">Ver renglones</button></td><td class="num">'+(e.unidades||e.revisar?qty(e.unidades)+(e.revisar?' <small class="rev">('+e.revisar+' a revisar)</small>':''):'—')+'</td><td class="num">'+money(e.ventas)+'</td><td class="num">'+prom(e.ventas,e.comps.size)+'</td><td class="num">'+prom(e.ventas,e.meses.size)+'</td></tr>';
  });
  if(open)html+='</tbody>';
  const t=total(rows),cov=cobertura(rows);
  html+='<tbody><tr class="total"><td>TOTAL '+(q?'VISIBLE':'PRODUCTO TERMINADO VENDIDO')+'</td><td class="num">'+unitsText(rows)+'</td><td class="num">'+money(t.v)+'</td><td class="num">'+prom(t.v,cov.comps)+'</td><td class="num">'+prom(t.v,cov.meses)+'</td></tr></tbody></table></div>';
  target.innerHTML=html;
  const hay=rows.some(e=>!collapsed.has(claveEmp(e))&&!collapsed.has(claveGrp(e)));
  const btn=$('contraer');
  btn.textContent=hay?'Contraer todo':'Mostrar artículos';
  btn.onclick=()=>{if(hay){rows.forEach(e=>collapsed.add(claveGrp(e)))}else{collapsed.clear()}renderArticles()};
  const unidades=rows.reduce((s,e)=>s+e.unidades,0);
  note.innerHTML=rows.length+' renglones de artículo · '+currentRecords.length+' comprobantes · importe de la tabla '+money(t.v)+
    ' · unidades '+qty(unidades)+'. Solo productos bajo P.T. FABRICADOS / P.T. IMPORTADOS: fletes, bordados, logos, almohadones y demás conceptos quedan fuera de este informe.';
}

function renderCompanies(){
  const target=$('company-table');
  const porEmpresa=new Map();
  currentLines.forEach(b=>{
    let e=porEmpresa.get(b.empresa);
    if(!e){e={empresa:b.empresa,registros:new Set(),articulos:new Set(),unidades:0,revisar:0,neto:0};porEmpresa.set(b.empresa,e)}
    e.registros.add(b.registro_id);e.articulos.add(b.articulo_id);
    if(b.cantidad_venta===null)e.revisar++;else e.unidades+=b.cantidad_venta||0;
    e.neto+=b.neto||0;
  });
  const rows=[...porEmpresa.values()].sort((a,b)=>b.neto-a.neto);
  const totalNeto=rows.reduce((s,e)=>s+e.neto,0);
  if(!rows.length){target.innerHTML='<p class="empty">Sin ventas para la selección.</p>';return}
  target.innerHTML=table(['Empresa','Comprobantes','Artículos','Unidades','Importe sin IVA','Participación'],
    rows.map(e=>'<tr><td>'+esc(e.empresa)+'</td><td class="num">'+e.registros.size+'</td><td class="num">'+e.articulos.size+'</td><td class="num">'+qty(e.unidades)+(e.revisar?' <small class="rev">('+e.revisar+' a revisar)</small>':'')+'</td>'+num(e.neto)+'<td class="num">'+(totalNeto?(e.neto*100/totalNeto).toFixed(1):'0,0')+' %</td></tr>').join('')+
    '<tr class="total"><td>TOTAL</td><td class="num">'+currentRecords.length+'</td><td class="num">'+new Set(currentLines.map(b=>b.articulo_id)).size+'</td><td class="num">'+qty(rows.reduce((s,e)=>s+e.unidades,0))+'</td>'+num(totalNeto)+'<td class="num">100,0 %</td></tr>');
}

function buildTimeline(){
  const months=new Map();
  currentLines.forEach(b=>{
    const r=records.get(b.registro_id);
    const mes=r.fecha?r.fecha.slice(0,7):'Sin fecha';
    let m=months.get(mes);
    if(!m){m={mes:mes,neto:0,unidades:0,revisar:0,registros:new Set(),arts:new Map()};months.set(mes,m)}
    m.neto+=b.neto||0;
    if(b.cantidad_venta===null)m.revisar++;else m.unidades+=b.cantidad_venta||0;
    m.registros.add(b.registro_id);
    let a=m.arts.get(b.articulo_id);
    if(!a){a={art:b.articulo,artId:b.articulo_id,um:b.unidad||'',unidades:0,revisar:0,neto:0,renglones:0};m.arts.set(b.articulo_id,a)}
    if(b.cantidad_venta===null)a.revisar++;else a.unidades+=b.cantidad_venta||0;
    a.neto+=b.neto||0;a.renglones++;
  });
  timelineMonths=[...months.values()].sort((a,b)=>a.mes.localeCompare(b.mes));
}
function renderTimeline(){
  const q=$('articulo').value.trim().toLocaleLowerCase('es');
  renderChart($('chart-unidades'),timelineMonths.map(m=>({label:labelMes(m.mes),value:m.unidades})),false);
  renderChart($('chart-importe'),timelineMonths.map(m=>({label:labelMes(m.mes),value:m.neto/100})),true);
  renderTopChart();
  const match=a=>!q||(a.art+' [ID '+a.artId+']').toLocaleLowerCase('es').includes(q);
  const visibles=timelineMonths.map(m=>({mes:m.mes,arts:[...m.arts.values()].filter(match).sort((a,b)=>b.neto-a.neto)}))
                               .filter(m=>!q||m.arts.length);
  timelineVisible=visibles.flatMap(m=>m.arts.map(a=>Object.assign({mes:m.mes},a)));
}

function renderChart(host, items, isMoney){
  if(!items.length){host.innerHTML='<p class="empty">Sin datos en el rango.</p>';return}
  const W=680,H=270,pad={l:76,r:14,t:16,b:58};
  const max=Math.max(...items.map(i=>i.value),1);
  const bw=(W-pad.l-pad.r)/items.length;
  const fmt=v=>isMoney?new Intl.NumberFormat('es-AR',{maximumFractionDigits:0}).format(v):qty(v);
  let g='';
  for(let t=0;t<=4;t++){
    const v=max*t/4, y=pad.t+(H-pad.t-pad.b)*(1-t/4);
    g+='<line x1="'+pad.l+'" y1="'+y.toFixed(1)+'" x2="'+(W-pad.r)+'" y2="'+y.toFixed(1)+'" class="axis"/>';
    g+='<text x="'+(pad.l-8)+'" y="'+(y+4).toFixed(1)+'" class="tick" text-anchor="end">'+esc(fmt(v))+'</text>';
  }
  items.forEach((it,i)=>{
    const h=Math.max(0,(H-pad.t-pad.b)*(it.value/max)), x=pad.l+i*bw, y=H-pad.b-h;
    g+='<rect x="'+(x+1).toFixed(1)+'" y="'+y.toFixed(1)+'" width="'+Math.max(1,bw-2).toFixed(1)+'" height="'+h.toFixed(1)+'" class="bar"><title>'+esc(it.label)+' · '+esc(fmt(it.value))+'</title></rect>';
    g+='<text x="'+(x+bw/2).toFixed(1)+'" y="'+(H-pad.b+16)+'" class="tick xtick" text-anchor="end" transform="rotate(-45 '+(x+bw/2).toFixed(1)+' '+(H-pad.b+16)+')">'+esc(it.label)+'</text>';
  });
  host.innerHTML='<svg viewBox="0 0 '+W+' '+H+'" preserveAspectRatio="xMidYMid meet" role="img">'+g+'</svg>';
}
function renderTopChart(){
  const host=$('chart-articulos');
  if(!timelineMonths.length){host.innerHTML='<p class="empty">Sin datos en el rango.</p>';return}
  const metrica=$('metrica').value, topn=+$('topn').value;
  const byArt=new Map();
  timelineMonths.forEach(m=>m.arts.forEach((a,id)=>{
    let e=byArt.get(id);
    if(!e){e={art:a.art,artId:a.artId,total:0,points:new Map()};byArt.set(id,e)}
    const v=metrica==='neto'?a.neto/100:a.unidades;
    e.total+=v; e.points.set(m.mes,v);
  }));
  const series=[...byArt.values()].sort((a,b)=>b.total-a.total).slice(0,topn);
  if(!series.length){host.innerHTML='<p class="empty">Sin artículos en el rango.</p>';return}
  const months=timelineMonths.map(m=>m.mes);
  const all=series.flatMap(s=>months.map(m=>s.points.get(m)||0));
  const max=Math.max(...all,1);
  const W=680,H=320,pad={l:76,r:16,t:16,b:58};
  const x=i=>pad.l+(months.length<2?(W-pad.l-pad.r)/2:(W-pad.l-pad.r)*i/(months.length-1));
  const y=v=>pad.t+(H-pad.t-pad.b)*(1-v/max);
  const fmt=v=>metrica==='neto'?new Intl.NumberFormat('es-AR',{maximumFractionDigits:0}).format(v):qty(v);
  let g='';
  for(let t=0;t<=4;t++){
    const v=max*t/4, yy=y(v);
    g+='<line x1="'+pad.l+'" y1="'+yy.toFixed(1)+'" x2="'+(W-pad.r)+'" y2="'+yy.toFixed(1)+'" class="axis"/>';
    g+='<text x="'+(pad.l-8)+'" y="'+(yy+4).toFixed(1)+'" class="tick" text-anchor="end">'+esc(fmt(v))+'</text>';
  }
  months.forEach((m,i)=>{
    g+='<text x="'+x(i).toFixed(1)+'" y="'+(H-pad.b+16)+'" class="tick xtick" text-anchor="end" transform="rotate(-45 '+x(i).toFixed(1)+' '+(H-pad.b+16)+')">'+esc(labelMes(m))+'</text>';
  });
  series.forEach((s,k)=>{
    const color=COLORS[k%COLORS.length];
    const pts=months.map((m,i)=>x(i).toFixed(1)+','+y(s.points.get(m)||0).toFixed(1)).join(' ');
    g+='<polyline points="'+pts+'" fill="none" stroke="'+color+'" stroke-width="2.2"/>';
    months.forEach((m,i)=>{
      const v=s.points.get(m);
      if(v) g+='<circle cx="'+x(i).toFixed(1)+'" cy="'+y(v).toFixed(1)+'" r="3.4" fill="'+color+'"><title>'+esc(s.art)+' · '+esc(labelMes(m))+' · '+esc(fmt(v))+'</title></circle>';
    });
  });
  const legend='<div class="legend">'+series.map((s,k)=>'<span><i style="background:'+COLORS[k%COLORS.length]+'"></i>'+esc(s.art)+' <small>ID '+s.artId+'</small></span>').join('')+'</div>';
  host.innerHTML='<svg viewBox="0 0 '+W+' '+H+'" preserveAspectRatio="xMidYMid meet" role="img">'+g+'</svg>'+legend;
}

function renderControl(){
  const c=DATA.controles;
  const filas=[
    ['Cabeceras leídas en el origen',c.registros],
    ['Renglones leídos en el origen',c.lineas],
    ['Comprobantes de venta con producto terminado',c.incluidos],
    ['Renglones de producto terminado',c.lineas_producto],
    ['Comprobantes de venta fuera de alcance',c.excluidos_ventas],
    ['Renglones de producto en otros flujos (remitos/compras)',c.lineas_producto_fuera_de_alcance],
    ['Cabeceras de esos otros flujos',c.registros_producto_fuera_de_alcance],
    ['Diferencias cabecera / renglones',c.diferencias_cabecera_renglon],
    ['Renglones con unidades a revisar',c.unidades_a_revisar],
    ['Comprobantes sin cuenta propia de resultados',c.sin_cuenta_propia]
  ];
  $('controls').innerHTML=table(['Control','Cantidad'],filas.map(f=>'<tr><td>'+esc(f[0])+'</td><td class="num">'+qty(f[1])+'</td></tr>').join('')+
    Object.entries(c.fuera_de_alcance_por_flujo||{}).map(([k,v])=>'<tr><td>↳ '+esc(k)+'</td><td class="num">'+qty(v)+'</td></tr>').join(''));
  const target=$('audit');target.replaceChildren();
  const q=$('buscar-control').value.trim().toLocaleLowerCase('es');
  const rows=currentExcluded.filter(r=>!q||[r.id,r.referencia,r.cliente,r.motivo].join(' ').toLocaleLowerCase('es').includes(q));
  for(const [reason,rs] of groupBy(rows,r=>r.motivo))target.append(disclosure(reason+' · '+rs.length+' comprobantes · '+money(sum(rs,'neto')),rs,recordTable));
  if(!rows.length)target.innerHTML='<p class="empty">Sin comprobantes de venta fuera de alcance en el rango.</p>';
}
function groupBy(rows, key){const out=new Map();rows.forEach(r=>{const k=key(r);if(!out.has(k))out.set(k,[]);out.get(k).push(r)});return [...out.entries()].sort(([a],[b])=>a.localeCompare(b,'es'))}

function renderPromedios(){
  const host=$('promedios');
  if(!currentLines.length){host.innerHTML='';return}
  const neto=sum(currentLines,'neto');
  const unidades=currentLines.reduce((s,b)=>s+(b.cantidad_venta||0),0);
  const meses=new Set(currentLines.map(b=>{const r=records.get(b.registro_id);return r.fecha?r.fecha.slice(0,7):'Sin fecha'}));
  const nM=meses.size||1, nC=currentRecords.length||1;
  const chip=(l,v)=>'<span class="chip"><small>'+esc(l)+'</small><b>'+v+'</b></span>';
  host.innerHTML=chip('Promedio mensual',money(neto/nM))+chip('Ticket promedio',money(neto/nC))+
    chip('Unidades por mes',qty(unidades/nM))+chip('Meses con ventas',qty(meses.size));
}

function render(){
  applyFilters();
  articleRows=buildArticleRows();
  buildTimeline();
  const neto=sum(currentLines,'neto');
  const unidades=currentLines.reduce((s,b)=>s+(b.cantidad_venta||0),0);
  const revisar=currentLines.filter(b=>b.cantidad_venta===null).length;
  const kpis=[
    ['Ventas netas de producto terminado',money(neto)],
    ['Unidades vendidas',qty(unidades)+(revisar?' <small class="rev">('+revisar+' a revisar)</small>':'')],
    ['Artículos vendidos',qty(new Set(currentLines.map(b=>b.articulo_id)).size)],
    ['Comprobantes',qty(currentRecords.length)],
    ['Empresas con ventas',qty(new Set(currentLines.map(b=>b.empresa)).size)],
    ['Comprobantes fuera de alcance',qty(currentExcluded.length)]
  ];
  $('kpis').innerHTML=kpis.map(([l,v])=>'<div class="kpi"><small>'+esc(l)+'</small><b>'+v+'</b></div>').join('');
  $('range').textContent=($('desde').value||'Inicio disponible')+' → '+($('hasta').value||'Fin disponible')+' · '+currentRecords.length+' comprobantes · '+currentLines.length+' renglones';
  renderPromedios();
  renderArticles();renderCompanies();renderTimeline();renderControl();
}

function csv(name,heads,rows){
  const cell=v=>'"'+String(v??'').replace(/^[=+@\t\r]/,"'$&").replace(/"/g,'""')+'"';
  const content='\ufeff'+[heads,...rows].map(r=>r.map(cell).join(';')).join('\r\n');
  const url=URL.createObjectURL(new Blob([content],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
['desde','hasta','empresa'].forEach(id=>$(id).addEventListener('change',render));
const rebuildTable=()=>{articleRows=buildArticleRows();renderArticles();renderTimeline()};
$('agrupar').addEventListener('change',rebuildTable);
$('metrica').addEventListener('change',renderTopChart);
$('topn').addEventListener('change',renderTopChart);
$('articulo').addEventListener('input',()=>{renderArticles();renderTimeline()});
$('buscar-control').addEventListener('input',renderControl);
function attachDetail(){
  $('article-table').addEventListener('click',ev=>{
    const btn=ev.target.closest('button[data-i]');
    if(!btn){
      const emp=ev.target.closest('tr[data-emp]');
      if(emp){const k='E:'+emp.dataset.emp;collapsed.has(k)?collapsed.delete(k):collapsed.add(k);renderArticles();return}
      const grp=ev.target.closest('tr[data-grp]');
      if(grp){const k='G:'+grp.dataset.grp;collapsed.has(k)?collapsed.delete(k):collapsed.add(k);renderArticles();return}
      return;
    }
    const tr=btn.closest('tr'),next=tr.nextElementSibling;
    if(next&&next.classList.contains('detalle')){next.remove();btn.textContent='Ver renglones';return}
    const e=articleVisible[+btn.dataset.i];
    const dr=document.createElement('tr');dr.className='detalle';
    const td=document.createElement('td');td.colSpan=tr.children.length;
    const ls=articleLines.get(e.key)||[];
    td.innerHTML=ls.length?lineTable(ls):'<p class="empty">Sin renglones de artículo.</p>';
    dr.append(td);tr.after(dr);btn.textContent='Ocultar renglones';
  });
}
attachDetail();
$('limpiar').onclick=()=>{$('desde').value='';$('hasta').value='';$('empresa').value='';$('articulo').value='';$('buscar-control').value='';render()};
$('exportar').onclick=()=>csv('estado_resultados_comprobantes.csv',['ID','Fecha','Empresa','Referencia','Cliente','Flujo','Estado','Tratamiento','Neto cabecera','Producto terminado','Fuera de PT','Motivo'],
  [...currentRecords.map(r=>[r.id,r.fecha,r.empresa,r.referencia,r.cliente,r.flujo,r.estado,'incluido',r.neto==null?'':r.neto/100,r.neto_pt/100,r.neto_fuera_pt/100,'']),
   ...currentExcluded.map(r=>[r.id,r.fecha,r.empresa,r.referencia,r.cliente,r.flujo,r.estado,'fuera de alcance',r.neto==null?'':r.neto/100,'','','',r.motivo])]);
$('exportar-articulos').onclick=()=>csv('estado_resultados_productos.csv',['Empresa','Agrupación','Artículo','ID artículo','Unidad','Unidades vendidas','Ajustes de cantidad a revisar','Renglones','Ventas netas sin IVA','Ticket promedio','Promedio mensual'],
  (articleVisible.length?articleVisible:articleRows).map(r=>[r.empresa,r.grupo,r.art,r.artId,r.um,r.unidades,r.revisar,r.renglones,r.ventas/100,
    r.comps.size?(r.ventas/r.comps.size/100).toFixed(2):'',r.meses.size?(r.ventas/r.meses.size/100).toFixed(2):'']));
$('exportar-timeline').onclick=()=>csv('estado_resultados_timeline.csv',['Mes','Artículo','ID artículo','Unidad','Unidades','Ajustes de cantidad a revisar','Precio unitario promedio','Importe sin IVA'],
  timelineVisible.map(r=>[r.mes,r.art,r.artId,r.um,r.unidades,r.revisar,r.unidades>0?(r.neto/r.unidades).toFixed(2):'',r.neto/100]));
$('stamp').textContent='Datos consultados: '+DATA.generado.replace('T',' ')+' · '+DATA.controles.registros+' cabeceras verificadas';
render();
