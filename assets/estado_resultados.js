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
let current = [], included = [], articleRows = [];

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
function renderArticles(){
 const query=$('articulo').value.trim().toLocaleLowerCase('es');
 const includedIds=new Set(included.map(r=>r.id));
 const selected=DATA.lineas.filter(b=>includedIds.has(b.registro_id)&&!b.fiscal);
 const grouped=groups(selected,b=>{const r=records.get(b.registro_id);return r.empresa+' | '+(b.generico?'Sin imputación a producto':b.articulo+' [ID '+b.articulo_id+']')+' | '+(b.generico?'':b.unidad)});
 articleRows=[];
 const target=$('article-table');target.replaceChildren();
 for(const [label,bs] of grouped){if(query&&!label.toLocaleLowerCase('es').includes(query))continue;
  const sales=bs.filter(b=>records.get(b.registro_id).concepto==='Ventas netas facturadas');
  const costs=bs.filter(b=>records.get(b.registro_id).concepto==='Costo de ventas registrado');
  const expenses=bs.filter(b=>!isIncome(records.get(b.registro_id))&&records.get(b.registro_id).concepto!=='Costo de ventas registrado');
  const other=bs.filter(b=>isIncome(records.get(b.registro_id))&&records.get(b.registro_id).concepto!=='Ventas netas facturadas');
  const units=sales.filter(b=>!b.generico&&!b.servicio&&b.cantidad_venta!==null).reduce((s,b)=>s+b.cantidad_venta,0);
  const review=sales.filter(b=>!b.generico&&!b.servicio&&b.cantidad_venta===null).length;
  const row={etiqueta:label,cantidad:units,revisar:review,ventas:sum(sales,'neto'),otros:sum(other,'neto'),costos:sum(costs,'neto'),gastos:sum(expenses,'neto')};articleRows.push(row);
  const caption=label+' · unidades identificadas '+qty(units)+(review?' · '+review+' ajustes de cantidad a revisar':'')+' · ventas '+money(row.ventas)+' · costos '+money(row.costos)+' · gastos '+money(row.gastos);
  target.append(disclosure(caption,bs,list=>table(['Unidades facturadas identificadas','Ajustes de cantidad a revisar','Ventas sin IVA','Otros ingresos','Costo registrado','Gastos registrados','Margen'],
   '<tr><td>'+qty(units)+'</td><td>'+review+'</td>'+num(row.ventas)+num(row.otros)+num(row.costos)+num(row.gastos)+'<td>No determinado</td></tr>')+lineTable(list)));
 }
 // Importes sin renglones y ajustes de redondeo mantienen conciliación con la vista empresa.
 const allocated=sum(selected,'neto');const residual=amount(included)-allocated;
 const p=document.createElement('p');p.textContent=articleRows.length+' agrupaciones visibles. Total neto de renglones reconocidos (antes de búsqueda): '+money(allocated)+'. Cabeceras sin detalle / redondeos no imputados a artículos: '+money(residual)+'. Servicios y renglones financieros no se cuentan como unidades de bienes.';target.prepend(p);
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
 const revenue=amount(included.filter(isIncome)),expenses=amount(included.filter(r=>!isIncome(r)));
 $('kpis').innerHTML=[['Ingresos reconocidos',money(revenue)],['Costos y gastos registrados',money(expenses)],['Resultado parcial',money(revenue-expenses)],['Comprobantes reconocidos',qty(included.length)],['Pendientes',qty(current.filter(r=>r.estado_analisis==='pendiente').length)]].map(([l,v])=>'<div class="kpi"><small>'+esc(l)+'</small><b>'+esc(v)+'</b></div>').join('');
 $('range').textContent=(from||'Inicio disponible')+' → '+(to||'Fin disponible')+' · '+current.length+' registros';
 renderCompanies();renderArticles();renderDispatch();renderControl();
}
function csv(name,heads,rows){
 const cell=v=>'"'+String(v??'').replace(/^[=+@\t\r]/,"'$&").replace(/"/g,'""')+'"';
 const content='\ufeff'+[heads,...rows].map(r=>r.map(cell).join(';')).join('\r\n');
 const url=URL.createObjectURL(new Blob([content],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
['desde','hasta','empresa'].forEach(id=>$(id).addEventListener('change',render));
$('articulo').addEventListener('input',renderArticles);$('buscar-control').addEventListener('input',renderControl);
$('limpiar').onclick=()=>{$('desde').value='';$('hasta').value='';$('empresa').value='';$('articulo').value='';$('buscar-control').value='';render()};
$('exportar').onclick=()=>csv('estado_resultados_registros.csv',['ID','Fecha','Empresa','Concepto','Cuenta','Referencia','Cliente','Flujo','Estado','Tratamiento','Motivo','Neto','Impuestos','Total','Fiscal separado','Importe resultado','Relaciones'],current.filter(r=>r.estado_analisis!=='relacionado').map(r=>[r.id,r.fecha,r.empresa,r.concepto,r.cuenta,r.referencia,r.cliente,r.flujo,r.estado,r.estado_analisis,r.motivo,r.neto==null?'':r.neto/100,r.impuestos==null?'':r.impuestos/100,r.total==null?'':r.total/100,r.fiscal_separado/100,r.importe_resultado/100,r.relacionados.join(', ')]));
$('exportar-articulos').onclick=()=>csv('estado_resultados_articulos.csv',['Empresa / Artículo / Unidad','Unidades facturadas identificadas','Ajustes de cantidad a revisar','Ventas netas','Otros ingresos','Costos registrados','Gastos registrados','Margen'],articleRows.map(r=>[r.etiqueta,r.cantidad,r.revisar,r.ventas/100,r.otros/100,r.costos/100,r.gastos/100,'No determinado']));
$('stamp').textContent='Datos consultados: '+DATA.generado.replace('T',' ')+' · '+DATA.controles.registros+' cabeceras verificadas';
render();
