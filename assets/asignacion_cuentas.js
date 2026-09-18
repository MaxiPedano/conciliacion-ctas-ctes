(function () {
    'use strict';

    var table = document.getElementById('detail-table');
    var select = document.getElementById('assign-account-select');
    if (!table || !select) return;

    var rows = Array.from(table.querySelectorAll('.detail-row'));
    var selectAll = document.getElementById('assign-select-all');
    var clearSelection = document.getElementById('assign-clear-selection');
    var addBatch = document.getElementById('assign-btn');
    var undoBatch = document.getElementById('assign-undo');
    var clearBatches = document.getElementById('clear-assign-btn');
    var copySql = document.getElementById('assign-copy');
    var downloadSql = document.getElementById('assign-download');
    var summary = document.getElementById('assign-summary');
    var feedback = document.getElementById('assign-feedback');
    var batchList = document.getElementById('batch-list');
    var sql = document.getElementById('sql-output');
    if (!addBatch || !summary || !feedback || !batchList || !sql) return;

    function canonicalAccountId(value) {
        if (value === null || value === undefined) return '';
        var text = String(value).trim();
        if (!text) return '';
        var number = Number(text);
        if (Number.isFinite(number) && Number.isInteger(number)) return String(number);
        return '';
    }

    function canonicalRecordId(value) {
        if (value === null || value === undefined) return '';
        var text = String(value).trim();
        return /^\d+$/.test(text) ? text : '';
    }

    function optionName(text) {
        return String(text || '').replace(/^\d+\s*-\s*/, '').trim();
    }

    var catalog = new Map();
    Array.from(select.options).forEach(function (option) {
        var id = canonicalAccountId(option.value);
        var name = optionName(option.textContent);
        if (id && name && !catalog.has(id)) catalog.set(id, name);
    });
    rows.forEach(function (row) {
        var id = canonicalAccountId(row.dataset.accountid);
        row.dataset.accountid = id;
        if (id && !catalog.has(id) && row.dataset.account) catalog.set(id, row.dataset.account);
    });

    select.replaceChildren(new Option('-- Elegir cuenta para este lote --', ''));
    Array.from(catalog.entries())
        .sort(function (a, b) { return a[1].localeCompare(b[1]); })
        .forEach(function (entry) {
            select.add(new Option(entry[0] + ' - ' + entry[1], entry[0]));
        });

    var originals = new Map(rows.map(function (row) {
        return [row, {
            accountid: row.dataset.accountid,
            account: row.dataset.account,
            status: row.dataset.status,
            cells: [5, 6, 7].map(function (index) { return row.cells[index].innerHTML; })
        }];
    }));
    var batches = [];
    var pending = new Set();
    var checked = new Set();

    function setFeedback(message, isError) {
        feedback.textContent = message;
        feedback.className = 'assignment-feedback' + (isError ? ' error' : '');
    }

    window.addEventListener('beforeunload', function (event) {
        if (batches.length) { event.preventDefault(); event.returnValue = ''; }
    });

    var heading = document.createElement('th');
    heading.textContent = 'Lote';
    heading.setAttribute('data-excel-ignore', 'true');
    heading.title = 'Selección usada solamente para armar lotes masivos; no forma parte de los datos.';
    table.tHead.rows[0].appendChild(heading);
    var noResultsCell = document.querySelector('#no-results td');
    if (noResultsCell) noResultsCell.colSpan = 11;

    var boxes = new Map();
    rows.forEach(function (row) {
        var cell = row.insertCell(-1);
        cell.setAttribute('data-excel-ignore', 'true');
        if (originals.get(row).accountid) {
            cell.textContent = '—';
            cell.title = 'Ya tiene cuenta contable.';
            return;
        }
        var box = document.createElement('input');
        box.type = 'checkbox';
        box.setAttribute('aria-label', 'Seleccionar registro ' + row.cells[0].textContent.trim() + ' para el lote actual');
        cell.appendChild(box);
        boxes.set(row, box);
        box.addEventListener('change', function () {
            if (box.checked) checked.add(row); else checked.delete(row);
            refreshSelection();
        });
    });

    function visiblePendingRows() {
        return rows.filter(function (row) {
            return !row.hidden && !row.dataset.accountid;
        });
    }

    function refreshSelection() {
        var available = 0;
        boxes.forEach(function (box, row) {
            var eligible = !row.hidden && !row.dataset.accountid;
            if (!eligible) checked.delete(row);
            box.disabled = !eligible;
            box.checked = checked.has(row);
            if (eligible) available += 1;
        });
        var selected = checked.size;
        summary.textContent = available.toLocaleString('es-AR') + ' pendientes visibles · ' +
            selected.toLocaleString('es-AR') + ' seleccionados para el lote actual · ' +
            batches.length.toLocaleString('es-AR') + ' lotes preparados';
        addBatch.disabled = !selected || !select.value;
        select.disabled = false;
        if (selectAll) selectAll.disabled = !available;
        if (clearSelection) clearSelection.disabled = !selected;
        if (undoBatch) undoBatch.disabled = !batches.length;
        if (clearBatches) clearBatches.disabled = !batches.length;
        if (copySql) copySql.disabled = !batches.length;
        if (downloadSql) downloadSql.disabled = !batches.length;
    }

    function renderBatches() {
        batchList.replaceChildren();
        if (!batches.length) {
            var empty = document.createElement('p');
            empty.className = 'batch-empty';
            empty.textContent = 'Sin lotes preparados.';
            batchList.appendChild(empty);
            sql.textContent = '-- Todavía no hay lotes preparados. Seleccione registros y agregue el primer lote.';
        } else {
            var statements = ['-- Asignaciones masivas pendientes', 'BEGIN;'];
            batches.forEach(function (batch, index) {
                var card = document.createElement('div');
                card.className = 'batch-card';
                var num = document.createElement('span');
                num.className = 'batch-num';
                num.textContent = index + 1;
                var info = document.createElement('span');
                info.className = 'batch-info';
                info.innerHTML = '<strong>' + batch.id + ' - ' + batch.name + '</strong><br><span class="batch-count">' +
                    batch.rows.length.toLocaleString('es-AR') + ' registros</span>';
                card.appendChild(num);
                card.appendChild(info);
                batchList.appendChild(card);
                var ids = batch.rows
                    .map(function (row) { return canonicalRecordId(row.cells[0].textContent); })
                    .sort(function (a, b) { return Number(a) - Number(b); });
                statements.push(
                    '-- Lote ' + (index + 1) + ': ' + ids.length + ' registros → ' + batch.id + ' - ' + batch.name,
                    'UPDATE test9000.registrocab SET cuentacontableid = ' + batch.id,
                    'WHERE id IN (' + ids.join(', ') + ') AND cuentacontableid IS NULL;'
                );
            });
            statements.push('COMMIT;');
            sql.textContent = statements.join('\n\n');
        }
        if (typeof window.refreshAccountReport === 'function') window.refreshAccountReport();
        refreshSelection();
    }

    if (selectAll) selectAll.addEventListener('click', function () {
        visiblePendingRows().forEach(function (row) { checked.add(row); });
        setFeedback('');
        refreshSelection();
    });
    if (clearSelection) clearSelection.addEventListener('click', function () {
        checked.clear();
        setFeedback('');
        refreshSelection();
    });
    select.addEventListener('change', function () {
        setFeedback('');
        refreshSelection();
    });

    addBatch.addEventListener('click', function () {
        refreshSelection();
        var id = canonicalAccountId(select.value);
        var selected = Array.from(checked);
        if (!id || !catalog.has(id)) {
            setFeedback('Elegí una cuenta contable válida antes de agregar el lote.', true);
            return;
        }
        if (!selected.length) {
            setFeedback('Seleccioná al menos un registro pendiente visible.', true);
            return;
        }
        if (selected.some(function (row) { return !canonicalRecordId(row.cells[0].textContent); })) {
            setFeedback('El lote contiene un identificador de registro inválido.', true);
            return;
        }
        var name = catalog.get(id);
        batches.push({ id: id, name: name, rows: selected });
        selected.forEach(function (row) {
            pending.add(row);
            row.dataset.accountid = id;
            row.dataset.account = name;
            row.dataset.status = 'Con cuenta contable';
            row.cells[5].textContent = id;
            row.cells[6].textContent = name;
            row.cells[7].innerHTML = '<span class="badge badge-pending">Asignación pendiente · lote ' + batches.length + '</span>';
        });
        checked.clear();
        setFeedback('Lote ' + batches.length + ' agregado con ' + selected.length.toLocaleString('es-AR') + ' registros.');
        renderBatches();
    });

    function restore(batch) {
        batch.rows.forEach(function (row) {
            var original = originals.get(row);
            pending.delete(row);
            row.dataset.accountid = original.accountid;
            row.dataset.account = original.account;
            row.dataset.status = original.status;
            row.cells[5].innerHTML = original.cells[0];
            row.cells[6].innerHTML = original.cells[1];
            row.cells[7].innerHTML = original.cells[2];
        });
    }

    if (undoBatch) undoBatch.addEventListener('click', function () {
        var batch = batches.pop();
        if (!batch) return;
        restore(batch);
        setFeedback('Se deshizo el último lote.');
        renderBatches();
    });
    if (clearBatches) clearBatches.addEventListener('click', function () {
        if (!batches.length) return;
        if (!window.confirm('¿Deshacer todos los lotes preparados en esta sesión?')) return;
        batches.splice(0).forEach(restore);
        setFeedback('Se deshicieron todos los lotes.');
        renderBatches();
    });

    function fallbackCopy(text) {
        var area = document.createElement('textarea');
        area.value = text;
        area.setAttribute('readonly', 'true');
        area.style.position = 'fixed';
        area.style.opacity = '0';
        document.body.appendChild(area);
        area.select();
        var done = false;
        try { done = document.execCommand('copy'); } catch (error) { done = false; }
        area.remove();
        return done;
    }

    if (copySql) copySql.addEventListener('click', function () {
        if (!batches.length) return;
        var text = sql.textContent;
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).then(function () {
                setFeedback('SQL copiado al portapapeles.');
            }, function () {
                setFeedback(fallbackCopy(text)
                    ? 'SQL copiado al portapapeles.'
                    : 'No se pudo copiar; copiá el texto del recuadro SQL.');
            });
        } else {
            setFeedback(fallbackCopy(text)
                ? 'SQL copiado al portapapeles.'
                : 'No se pudo copiar; copiá el texto del recuadro SQL.');
        }
    });
    if (downloadSql) downloadSql.addEventListener('click', function () {
        if (!batches.length) return;
        var url = URL.createObjectURL(new Blob([sql.textContent], { type: 'text/plain;charset=utf-8' }));
        var link = document.createElement('a');
        link.href = url;
        link.download = 'asignaciones_cuentas_contables.sql';
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
        setFeedback('Archivo SQL descargado.');
    });

    var observer = new MutationObserver(refreshSelection);
    if (table.tBodies[0]) {
        observer.observe(table.tBodies[0], { subtree: true, attributes: true, attributeFilter: ['hidden'] });
    }
    renderBatches();
}());
