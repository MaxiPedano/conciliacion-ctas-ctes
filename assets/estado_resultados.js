'use strict';
const DATA = JSON.parse(document.getElementById('datos-resultados').textContent);
const $ = id => document.getElementById(id);
const esc = v => String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money = v => v == null ? 'No disponible' : new Intl.NumberFormat('es-AR',{minimumFractionDigits:2,maximumFractionDigits:2}).format(v/100);
const qty = v => new Intl.NumberFormat('es-AR',{maximumFractionDigits:4}).format(v);
const sum = (rs, key) => rs.reduce((a,r)=>a+(r[key]||0),0);
const records = new Map(DATA.registros.map(r=>[r.id,r]));
const lines = new Map();
DATA.lineas.forEach(b=>{if(!lines.has(b.registro_id))lines.set(b.registro_id,[]);lines.get(b.registro_id).push(b)});
const concepts = ['Ventas netas facturadas','Otros ingresos','Costo de ventas registrado','Gastos de fabricación registrados','Gastos comerciales','Gastos administrativos','Gastos de directorio','Impuestos registrados','Otros gastos','Ingresos financieros','Gastos financieros'];
const amount = rs => sum(rs,'importe_resultado');
const isIncome = r => r.signo === 1;
const groups = (rows, key) => {const out=new Map();rows.forEach(r=>{const k=key(r);if(!out.has(k))out.set(k,[]);out.get(k).push(r)});return [...out.entries()].sort(([a],[b])=>a.localeCompare(b,'es'))};
const table = (head, body) => '<div class="scroll"><table><thead><tr>'+head.map(h=>'<th>'+esc(h)+'</th>').join('')+'</tr></thead><tbody>'+body+'</tbody></table></div>';
const num = v => '<td class="num">'+money(v)+'</td>';
let current = [], included = [], articleRows = [], articleVisible = [], articleLines = new Map(),
    expenseRows = [], expenseVisible = [], expenseLines = new Map(), otherSales = 0, otherSalesRows = [];
const norm = v => String(v||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toUpperCase();
const SERVICE_WORDS = ['FLETE','FREIGHT','SERVICIO','SERVICIOS','DESPACHO','TRASLADO','ENVIO','BORDADO','LOGO','ALQUILER','ANULACION','STAFF','TRANSPORTE','MONOTONO','HANDLING'];
const isServiceLine = b => norm(b.categoria).includes('SERVICIO') ||
  SERVICE_WORDS.some(w=>norm(b.articulo).includes(w));

function disclosure(title, rows, detailFactory) {
  const el=document.createElement('details');const s=document.createElement('summary');s.textContent=title;el.append(s);
  el.addEventListener('toggle',()=>{if(el.open&&!el.dataset.loaded){const body=document.createElement('div');body.innerHTML=detailFactory(rows);el.append(body);el.dataset.loaded='1'}});
  return el;
}
function recordTable(rows){
 return table(['Registro','Fecha','Referencia / cliente','Flujo / estado','Cuenta propia','Neto cabecera','Impuestos','Total','Fiscal separado','Importe en resultado','Relaciones / criterio'],rows.map(r=>'<tr><td>'+r.id+'</td><td>'+esc(r.fecha)+'</td><td>'+esc(r.referencia)+'<br><small>'+esc(r.cliente)+'</small></td><td>'+esc(r.flujo)+'<br><small>'+esc(r.estado)+' · flujo '+esc(r.estado_id)+' / cabecera '+esc(r.estado_cab)+'</small></td><td>'+esc(r.cuenta_id)+' · '+esc(r.cuenta)+'</td>'+num(r.neto)+num(r.impuestos)+num(r.total)+num(r.fiscal_separado)+num(r.importe_resultado)+'<td>'+esc(r.relacionados.join(', ')||'Sin relación')+'<br><small>'+esc(r.motivo)+'</small></td></tr>').join(''));
}
function lineTable(rows){
 return table(['Registro / línea','Fecha','Referencia / cliente','Artículo / unidad','Cantidad del renglón','Neto','Total','Alícuota','Cuenta / concepto'],rows.map(b=>{const r=records.get(b.registro_id);return '<tr><td>'+r.id+' / '+b.linea_id+'</td><td>'+esc(r.fecha)+'</td><td>'+esc(r.referencia)+'<br>'+esc(r.cliente)+'</td><td>'+esc(b.articulo)+'<br>'+esc(b.unidad)+'</td><td class="num">'+qty(b.cantidad)+'</td>'+num(b.neto)+num(b.total)+'<td>'+esc(b.alicuota)+'</td><td>'+esc(r.cuenta)+'<br>'+esc(r.concepto)+'</td></tr>'}).join(''));
}
function resultsTable(rows, key){
 return table([key==='empresa'?'Empresa':'Mes','Comprobantes','Ventas netas','Otros ingresos','Ingresos financieros','Costos registrados','Otros gastos registrados','Resultado parcial'],groups(rows,r=>r[key]||'Sin fecha').map(([label,rs])=>{
   const total=c=>amount(rs.filter(r=>r.concepto===c));
   const costs=total('Costo de ventas registrado');const expenses=amount(rs.filter(r=>!isIncome(r)))-costs;
   const result=rs.reduce((s,r)=>s+r.signo*r.importe_resultado,0);
   return '<tr><td>'+esc(label)+'</td><td>'+rs.length+'</td>'+num(total('Ventas netas facturadas'))+num(total('Otros ingresos'))+num(total('Ingresos financieros'))+num(costs)+num(expenses)+num(result)+'</tr>';
 }).join(''));
}
function renderCompanies(){
 $('company-table').innerHTML=resultsTable(included,'empresa');
 const target=$('company-detail');target.replaceChildren();
 for(const [company,rs] of groups(included,r=>r.empresa)){
  const outer=document.createElement('details');outer.open=true;const title=document.createElement('summary');title.textContent=company+' · '+rs.length+' comprobantes';outer.append(title);
  for(const concept of concepts){const subset=rs.filter(r=>r.concepto===concept);if(!subset.length)continue;
   const box=document.createElement('details');const heading=document.createElement('summary');heading.textContent=concept+' · '+money(amount(subset));box.append(heading);
   for(const [account,docs] of groups(subset,r=>r.cuenta_id+' · '+r.cuenta))box.append(disclosure(account+' · '+docs.length+' registros · '+money(amount(docs)),docs,recordTable));
   outer.append(box);
  }target.append(outer);
 }
 if(!included.length)target.innerHTML='<p class="empty">Sin importes reconocidos para esta selección. Revisá el control de integridad.</p>';
 $('monthly').innerHTML=resultsTable(included.map(r=>({...r,mes:r.fecha.slice(0,7)})),'mes');
}
function buildArticleRows(){
 const modo=$('agrupar').value, showCompany=!$('empresa').value;
 const ids=new Set(included.map(r=>r.id));
 const map=new Map(); const others=new Map(); articleLines=new Map(); otherSales=0; otherSalesRows=[];
 DATA.lineas.forEach(b=>{
  if(b.fiscal)return;
  const r=records.get(b.registro_id); if(!r||!ids.has(r.id))return;
  if(r.concepto!=='Ventas netas facturadas')return;
  const grupo=modo==='mes'?(r.fecha?r.fecha.slice(0,7):'Sin fecha'):(b.categoria||'Sin categoría');
  if(b.generico||b.servicio||isServiceLine(b)){
   otherSales+=b.neto||0;
   const k=[showCompany?r.empresa:'',grupo,b.articulo||'Artículo no identificado'].join(' § ');
   const o=others.get(k)||{empresa:r.empresa,grupo:grupo,art:b.articulo||'Artículo no identificado',unidades:0,ventas:0};
   if(!b.generico&&!b.servicio){if(b.cantidad_venta===null)o.revisar=(o.revisar||0)+1;else o.unidades+=b.cantidad_venta||0}
   o.ventas+=b.neto||0;others.set(k,o);
   return;
  }
  const art=b.articulo||'Artículo no identificado';
  const um=b.unidad||'';
  const key=[showCompany?r.empresa:'',grupo,art,um,'ID '+b.articulo_id].join(' § ');
  let e=map.get(key);
  if(!e){e={key:key,empresa:r.empresa,grupo:grupo,art:art,um:um,artId:b.articulo_id,unidades:0,revisar:0,ventas:0};map.set(key,e)}
  if(!articleLines.has(key))articleLines.set(key,[]);
  articleLines.get(key).push(b);
  if(b.cantidad_venta===null)e.revisar++;else e.unidades+=b.cantidad_venta;
  e.ventas+=b.neto||0;
 });
 otherSalesRows=[...others.values()].sort((a,b)=>b.ventas-a.ventas);
 return [...map.values()].filter(e=>e.ventas!==0);
}
function buildExpenseRows(){
 const modo=$('agrupar').value, showCompany=!$('empresa').value;
 const map=new Map(); expenseLines=new Map();
 const put=(r,grupo,art,um,artId,line)=>{const key=[showCompany?r.empresa:'',grupo,art,um,artId==null?'sin id':'ID '+artId].join(' § ');
  let e=map.get(key);
  if(!e){e={key:key,empresa:r.empresa,grupo:grupo,art:art,um:um,artId:artId,cantidad:0,renglones:0,importe:0};map.set(key,e)}
  if(!expenseLines.has(key))expenseLines.set(key,[]);
  if(line)expenseLines.get(key).push(line);
  e.renglones++;e.importe+=line?((line.neto||0)):0;
  if(line)e.cantidad+=line.cantidad||0;
  return e;};
 included.forEach(r=>{
  if(isIncome(r))return;
  const grupo=modo==='mes'?(r.fecha?r.fecha.slice(0,7):'Sin fecha'):'';
  const own=(lines.get(r.id)||[]).filter(b=>!b.fiscal);
  let acc=0;
  own.forEach(b=>{
   const cat=grupo||b.categoria||'Sin categoría';
   const e=put(r,cat,b.articulo||'Artículo no identificado',b.unidad||'',b.articulo_id,b);
   acc+=b.neto||0;
  });
  const resid=(r.importe_resultado||0)-acc;
  if(resid!==0){
   const cat=grupo||'Sin artículo (cabecera sin renglón)';
   put(r,cat,'Sin renglón de artículo','',null,null).importe+=resid;
  }
 });
 return [...map.values()].filter(e=>e.importe!==0);
}
const unitsByUm = rows => {
 const byUm=new Map();let review=0;
 rows.forEach(e=>{const u=e.um||'';byUm.set(u,(byUm.get(u)||0)+e.unidades);review+=e.revisar});
 const entries=[...byUm.entries()],blank=entries.every(([u])=>!u);
 let out;
 if(blank){const t=entries.reduce((s,[,v])=>s+v,0);out=t?qty(t):'—'}
 else{const parts=entries.filter(([,v])=>v!==0).map(([u,v])=>qty(v)+(u?' '+esc(u):' (sin unidad)'));out=parts.length?parts.join(' · '):'—'}
 if(review)out+=' <small class="rev">('+review+' a revisar)</small>';
 return out;
};
function renderArticles(){
 const target=$('article-table'), note=$('article-note');
 const q=$('articulo').value.trim().toLocaleLowerCase('es'), modo=$('agrupar').value;
 const showCompany=!$('empresa').value;
 const rows=articleRows.filter(e=>!q||(e.empresa+' § '+e.grupo+' § '+e.art+' [ID '+e.artId+']').toLocaleLowerCase('es').includes(q));
 articleVisible=rows;
  if(!rows.length){target.innerHTML='<p class="empty">Sin artículos de venta para la selección.</p>';note.textContent='';$('article-other').innerHTML='';return}
 rows.sort((a,b)=>a.empresa.localeCompare(b.empresa,'es')||a.grupo.localeCompare(b.grupo,'es')||b.ventas-a.ventas||a.art.localeCompare(b.art,'es'));
 const total=rs=>rs.reduce((s,e)=>({u:s.u+e.unidades,v:s.v+e.ventas}),{u:0,v:0});
 const compTot=new Map(),grpTot=new Map();
 rows.forEach(e=>{const ck=showCompany?e.empresa:'__all__',gk=ck+' § '+e.grupo;
  [[compTot,ck],[grpTot,gk]].forEach(([m,k])=>{const v=m.get(k)||{rows:[]};v.rows.push(e);m.set(k,v)})});
 const head='<th>'+(modo==='mes'?'Mes / Artículo':'Categoría / Artículo')+'</th><th class="num">Unidades facturadas</th><th class="num">Importe sin IVA</th>';
  let html='<div class="scroll"><table id="sales-table" class="flat"><thead><tr>'+head+'</tr></thead>';
 let comp=null,grp=null,open=false;
 rows.forEach((e,i)=>{
  const ck=showCompany?e.empresa:'__all__';
  if(ck!==comp){if(open){html+='</tbody>';open=false}comp=ck;grp=null;
   if(showCompany){const t=total(compTot.get(ck).rows);
    html+='<tbody class="company"><tr class="empresa"><td>EMPRESA: '+esc(ck)+'</td><td class="num">'+unitsByUm(compTot.get(ck).rows)+'</td><td class="num">'+money(t.v)+'</td></tr></tbody>'}}
  if(e.grupo!==grp){if(open){html+='</tbody>';open=false}grp=e.grupo;
   const rowsG=grpTot.get(ck+' § '+grp).rows,t=total(rowsG);
   html+='<tbody class="grupo"><tr class="grp"><td>'+(modo==='mes'?'MES: ':'CATEGORÍA: ')+esc(grp)+'</td><td class="num">'+unitsByUm(rowsG)+'</td><td class="num">'+money(t.v)+'</td></tr>';open=true}
  html+='<tr class="art"><td><span class="art-name" title="'+esc(e.art+' [ID '+e.artId+']'+(e.um?' · '+e.um:''))+'">'+esc(e.art)+' <small>[ID '+e.artId+']'+(e.um?' · '+esc(e.um):'')+'</small></span> <button class="ghost" data-i="'+i+'">Ver renglones</button></td><td class="num">'+(e.unidades||e.revisar?qty(e.unidades)+(e.revisar?' <small class="rev">('+e.revisar+' a revisar)</small>':''):'—')+'</td><td class="num">'+money(e.ventas)+'</td></tr>';
 });
 if(open)html+='</tbody>';
  const t=total(rows), gAll=total(articleRows);
  html+='</tbody><tbody><tr class="total"><td>TOTAL '+(q?'VISIBLE':'ARTÍCULOS VENDIDOS')+'</td><td class="num">'+unitsByUm(rows)+'</td><td class="num">'+money(t.v)+'</td></tr></tbody></table></div>';
  target.innerHTML=html;
  const rec=amount(included.filter(r=>r.concepto==='Ventas netas facturadas'));
  note.innerHTML=rows.length+' artículos de venta · importe de la tabla '+money(t.v)+
   ' · servicios y otros conceptos facturados aparte '+money(otherSales)+
   ' · total de ventas facturadas '+money(rec)+
   (q?' · total sin búsqueda '+money(gAll.v):'')+
   '. Solo productos (sillas, mesas, accesorios): fletes, servicios, despachos y similares quedan en la lista siguiente. Unidades de bienes; el sistema no registra unidad de medida.';
  const other=$('article-other');
  if(!otherSalesRows.length){other.innerHTML=''}
  else other.innerHTML='<details><summary>Servicios y otros conceptos facturados · '+otherSalesRows.length+' · '+money(otherSales)+'</summary>'+
   table(['Empresa','Categoría / mes','Concepto','Unidades','Importe sin IVA'],otherSalesRows.map(o=>'<tr><td>'+esc(o.empresa)+'</td><td>'+esc(o.grupo)+'</td><td>'+esc(o.art)+'</td><td class="num">'+(o.unidades||o.revisar?qty(o.unidades)+(o.revisar?' ('+o.revisar+' a revisar)':''):'—')+'</td>'+num(o.ventas)).join(''))+'</details>';
 }
 function renderExpenses(){
  const target=$('expense-table'), note=$('expense-note');
  const q=$('articulo').value.trim().toLocaleLowerCase('es'), modo=$('agrupar').value;
  const showCompany=!$('empresa').value;
  const rows=expenseRows.filter(e=>!q||(e.empresa+' § '+e.grupo+' § '+e.art).toLocaleLowerCase('es').includes(q));
  expenseVisible=rows;
  if(!rows.length){target.innerHTML='<p class="empty">Sin costos ni gastos con artículo para la selección.</p>';note.textContent='';return}
  rows.sort((a,b)=>a.empresa.localeCompare(b.empresa,'es')||a.grupo.localeCompare(b.grupo,'es')||b.importe-a.importe||a.art.localeCompare(b.art,'es'));
  const total=rs=>rs.reduce((s,e)=>s+e.importe,0);
  const qtyOf=rs=>rs.reduce((s,e)=>s+e.cantidad,0);
  const compTot=new Map(),grpTot=new Map();
  rows.forEach(e=>{const ck=showCompany?e.empresa:'__all__',gk=ck+' § '+e.grupo;
   [[compTot,ck],[grpTot,gk]].forEach(([m,k])=>{const v=m.get(k)||{rows:[]};v.rows.push(e);m.set(k,v)})});
  const head='<th>'+(modo==='mes'?'Mes / Artículo':'Categoría / Artículo')+'</th><th class="num">Cantidad</th><th class="num">Importe sin IVA</th>';
  let html='<div class="scroll"><table id="expense-sales-table" class="flat"><thead><tr>'+head+'</tr></thead>';
  let comp=null,grp=null,open=false;
  rows.forEach((e,i)=>{
   const ck=showCompany?e.empresa:'__all__';
   if(ck!==comp){if(open){html+='</tbody>';open=false}comp=ck;grp=null;
    if(showCompany){const rs=compTot.get(ck).rows;
     html+='<tbody class="company"><tr class="empresa"><td>EMPRESA: '+esc(ck)+'</td><td class="num">'+qty(qtyOf(rs))+'</td><td class="num">'+money(total(rs))+'</td></tr></tbody>'}}
   if(e.grupo!==grp){if(open){html+='</tbody>';open=false}grp=e.grupo;
    const rs=grpTot.get(ck+' § '+grp).rows;
    html+='<tbody class="grupo"><tr class="grp"><td>'+(modo==='mes'?'MES: ':'CATEGORÍA: ')+esc(grp)+'</td><td class="num">'+qty(qtyOf(rs))+'</td><td class="num">'+money(total(rs))+'</td></tr>';open=true}
   html+='<tr class="art"><td><span class="art-name" title="'+esc(e.art+(e.artId==null?'':' [ID '+e.artId+']'))+'">'+esc(e.art)+(e.artId==null?'':' <small>[ID '+e.artId+']</small>')+'</span> <button class="ghost" data-i="'+i+'">Ver renglones</button></td><td class="num">'+(e.cantidad?qty(e.cantidad):'—')+'</td><td class="num">'+money(e.importe)+'</td></tr>';
  });
  if(open)html+='</tbody>';
  const t=total(rows);
  html+='</tbody><tbody><tr class="total"><td>TOTAL COSTOS Y GASTOS</td><td class="num">'+qty(qtyOf(rows))+'</td><td class="num">'+money(t)+'</td></tr></tbody></table></div>';
  target.innerHTML=html;
  const rec=amount(included.filter(r=>!isIncome(r)));
  note.innerHTML=rows.length+' conceptos · comprobantes de gasto '+qty(included.filter(r=>!isIncome(r)).length)+
   ' · importe de la tabla '+money(t)+' · costos y gastos reconocidos '+money(rec)+' · diferencia '+money(t-rec)+
   (q?' · total sin búsqueda '+money(total(expenseRows)):'')+
   '. Incluye renglones sin artículo («Sin renglón de artículo») para que el total cierre con el resultado. Las compras de materias primas figuran pendientes de devengamiento y no son costo vendido.';
 }
function renderArticleDetails(){
 const query=$('articulo').value.trim().toLocaleLowerCase('es');
 const includedIds=new Set(included.map(r=>r.id));
 const selected=DATA.lineas.filter(b=>includedIds.has(b.registro_id)&&!b.fiscal);
 const grouped=groups(selected,b=>{const r=records.get(b.registro_id);return r.empresa+' | '+(b.generico?'Sin imputación a producto':b.articulo+' [ID '+b.articulo_id+']')+' | '+(b.generico?'':b.unidad)});
 const target=$('article-detail');target.replaceChildren();
 for(const [label,bs] of grouped){if(query&&!label.toLocaleLowerCase('es').includes(query))continue;
  const sales=bs.filter(b=>records.get(b.registro_id).concepto==='Ventas netas facturadas');
  const costs=bs.filter(b=>records.get(b.registro_id).concepto==='Costo de ventas registrado');
  const expenses=bs.filter(b=>!isIncome(records.get(b.registro_id))&&records.get(b.registro_id).concepto!=='Costo de ventas registrado');
  const other=bs.filter(b=>isIncome(records.get(b.registro_id))&&records.get(b.registro_id).concepto!=='Ventas netas facturadas');
  const units=sales.filter(b=>!b.generico&&!b.servicio&&b.cantidad_venta!==null).reduce((s,b)=>s+b.cantidad_venta,0);
  const review=sales.filter(b=>!b.generico&&!b.servicio&&b.cantidad_venta===null).length;
  const caption=label+' · unidades identificadas '+qty(units)+(review?' · '+review+' ajustes de cantidad a revisar':'')+' · ventas '+money(sum(sales,'neto'))+' · costos '+money(sum(costs,'neto'))+' · gastos '+money(sum(expenses,'neto'));
  target.append(disclosure(caption,bs,list=>table(['Unidades facturadas identificadas','Ajustes de cantidad a revisar','Ventas sin IVA','Otros ingresos','Costo registrado','Gastos registrados','Margen'],
   '<tr><td>'+qty(units)+'</td><td>'+review+'</td>'+num(sum(sales,'neto'))+num(sum(other,'neto'))+num(sum(costs,'neto'))+num(sum(expenses,'neto'))+'<td>No determinado</td></tr>')+lineTable(list)));
 }
 if(!target.children.length)target.innerHTML='<p class="empty">Sin renglones de artículo para la selección.</p>';
}
function renderDispatch(){
 const ids=new Set(current.filter(r=>r.estado_analisis==='despacho'&&r.estado_id===1114).map(r=>r.id));
 const target=$('dispatch-table');target.replaceChildren();
 for(const [label,bs] of groups(DATA.lineas.filter(b=>ids.has(b.registro_id)),b=>records.get(b.registro_id).empresa+' | '+b.articulo+' [ID '+b.articulo_id+'] | '+b.unidad)){
  target.append(disclosure(label+' · '+qty(sum(bs,'cantidad'))+' despachadas · NO suma ventas',bs,lineTable));
 }if(!ids.size)target.textContent='Sin remitos de salida en la selección.';
}
function renderControl(){
 const labels={incluido:'Incluidos una vez',cubierto:'Pagos/cobros vinculados (no duplican)',despacho:'Remitos (no ventas)',excluido:'Fuera de resultados',pendiente:'Pendientes de clasificación/devengamiento',relacionado:'Sin cuenta propia; relacionado con cuenta (solo cantidad)'};
 $('controls').innerHTML=table(['Tratamiento','Registros','Neto de cabeceras (no sumar al resultado)'],Object.entries(labels).map(([key,label])=>{const rs=current.filter(r=>r.estado_analisis===key);return '<tr><td>'+esc(label)+'</td><td>'+rs.length+'</td>'+num(sum(rs,'neto'))+'</tr>'}).join(''));
 const target=$('audit');target.replaceChildren();const q=$('buscar-control').value.trim().toLocaleLowerCase('es');
 const audit=current.filter(r=>r.estado_analisis!=='incluido'&&r.estado_analisis!=='relacionado'&&(!q||[r.id,r.referencia,r.cliente,r.motivo].join(' ').toLocaleLowerCase('es').includes(q)));
 for(const [reason,rs] of groups(audit,r=>r.motivo))target.append(disclosure(reason+' · '+rs.length+' registros · '+money(sum(rs,'neto')),rs,recordTable));
 const fiscal=included.filter(r=>r.fiscal_separado);if(fiscal.length)target.append(disclosure('IVA/percepciones en renglones separados del resultado · '+money(sum(fiscal,'fiscal_separado')),fiscal,recordTable));
 const statuses=current.filter(r=>r.estado_cab!==r.estado_id&&r.estado_analisis!=='relacionado');if(statuses.length)target.append(disclosure('Estado de cabecera distinto del flujo (se usa flujo) · '+statuses.length+' registros',statuses,recordTable));
}
function render(){
 const from=$('desde').value,to=$('hasta').value,company=$('empresa').value;
 const invalid=from&&to&&from>to;$('error').hidden=!invalid;$('error').textContent=invalid?'La fecha desde no puede ser posterior a la fecha hasta. Corregí el rango.':'';
 current=invalid?[]:DATA.registros.filter(r=>(!company||r.empresa===company)&&(!from||(r.fecha&&r.fecha>=from))&&(!to||(r.fecha&&r.fecha<=to)));
 included=current.filter(r=>r.estado_analisis==='incluido');
 articleRows=buildArticleRows();
 expenseRows=buildExpenseRows();
 const revenue=amount(included.filter(isIncome)),expenses=amount(included.filter(r=>!isIncome(r)));
 const salesUnits=unitsByUm(articleRows);
 $('kpis').innerHTML=[['Ingresos reconocidos',money(revenue)],['Costos y gastos registrados',money(expenses)],['Resultado parcial',money(revenue-expenses)],['Unidades de artículos vendidas',salesUnits],['Comprobantes reconocidos',qty(included.length)],['Pendientes',qty(current.filter(r=>r.estado_analisis==='pendiente').length)]].map(([l,v])=>'<div class="kpi"><small>'+esc(l)+'</small><b>'+v+'</b></div>').join('');
 $('range').textContent=(from||'Inicio disponible')+' → '+(to||'Fin disponible')+' · '+current.length+' registros';
 renderCompanies();renderArticles();renderExpenses();renderArticleDetails();renderDispatch();renderControl();
}
function csv(name,heads,rows){
 const cell=v=>'"'+String(v??'').replace(/^[=+@\t\r]/,"'$&").replace(/"/g,'""')+'"';
 const content='\ufeff'+[heads,...rows].map(r=>r.map(cell).join(';')).join('\r\n');
 const url=URL.createObjectURL(new Blob([content],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
['desde','hasta','empresa'].forEach(id=>$(id).addEventListener('change',render));
const rebuild=()=>{articleRows=buildArticleRows();expenseRows=buildExpenseRows();renderArticles();renderExpenses();renderArticleDetails()};
$('agrupar').addEventListener('change',rebuild);
$('articulo').addEventListener('input',()=>{renderArticles();renderExpenses();renderArticleDetails()});$('buscar-control').addEventListener('input',renderControl);
function attachDetail(id,rowsFn,linesFn){
 $(id).addEventListener('click',ev=>{
  const btn=ev.target.closest('button[data-i]');if(!btn)return;
  const tr=btn.closest('tr'),next=tr.nextElementSibling;
  if(next&&next.classList.contains('detalle')){next.remove();btn.textContent='Ver renglones';return}
  const e=rowsFn()[+btn.dataset.i];
  const dr=document.createElement('tr');dr.className='detalle';
  const td=document.createElement('td');td.colSpan=3;
  const ls=linesFn().get(e.key)||[];
  td.innerHTML=ls.length?lineTable(ls):'<p class="empty">Sin renglones de artículo: importe tomado de la cabecera del comprobante.</p>';
  dr.append(td);tr.after(dr);btn.textContent='Ocultar renglones';
 });
}
attachDetail('article-table',()=>articleVisible,()=>articleLines);
attachDetail('expense-table',()=>expenseVisible,()=>expenseLines);
$('limpiar').onclick=()=>{$('desde').value='';$('hasta').value='';$('empresa').value='';$('articulo').value='';$('buscar-control').value='';render()};
$('exportar').onclick=()=>csv('estado_resultados_registros.csv',['ID','Fecha','Empresa','Concepto','Cuenta','Referencia','Cliente','Flujo','Estado','Tratamiento','Motivo','Neto','Impuestos','Total','Fiscal separado','Importe resultado','Relaciones'],current.filter(r=>r.estado_analisis!=='relacionado').map(r=>[r.id,r.fecha,r.empresa,r.concepto,r.cuenta,r.referencia,r.cliente,r.flujo,r.estado,r.estado_analisis,r.motivo,r.neto==null?'':r.neto/100,r.impuestos==null?'':r.impuestos/100,r.total==null?'':r.total/100,r.fiscal_separado/100,r.importe_resultado/100,r.relacionados.join(', ')]));
$('exportar-articulos').onclick=()=>csv('estado_resultados_articulos.csv',['Empresa','Agrupación','Artículo','ID artículo','Unidad','Unidades facturadas','Ajustes de cantidad a revisar','Ventas netas sin IVA'],(articleVisible.length?articleVisible:articleRows).map(r=>[r.empresa,r.grupo,r.art,r.artId,r.um,r.unidades,r.revisar,r.ventas/100]));
$('exportar-gastos').onclick=()=>csv('estado_resultados_gastos.csv',['Empresa','Agrupación','Artículo','ID artículo','Cantidad','Renglones','Importe sin IVA'],(expenseVisible.length?expenseVisible:expenseRows).map(r=>[r.empresa,r.grupo,r.art,r.artId==null?'':r.artId,r.cantidad,r.renglones,r.importe/100]));
$('stamp').textContent='Datos consultados: '+DATA.generado.replace('T',' ')+' · '+DATA.controles.registros+' cabeceras verificadas';
render();
