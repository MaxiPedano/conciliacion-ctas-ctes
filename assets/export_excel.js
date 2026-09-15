(function () {
    "use strict";

    function cleanFileName(value) {
        return String(value || "reporte")
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "")
            .replace(/[^a-zA-Z0-9_-]+/g, "-")
            .replace(/^-+|-+$/g, "")
            .toLowerCase() || "reporte";
    }

    function removeRowsFromClone(clone, includeAll) {
        clone.querySelectorAll("tbody tr").forEach(function (row) {
            if (row.classList.contains("empty-row") || row.id === "no-results") {
                row.remove();
                return;
            }
            if (!includeAll && (row.hidden || row.hasAttribute("hidden") || row.style.display === "none")) {
                row.remove();
                return;
            }
            row.removeAttribute("hidden");
            row.style.removeProperty("display");
        });
        clone.removeAttribute("hidden");
        clone.removeAttribute("style");
    }

    function downloadTable(table, includeAll) {
        const sourceId = includeAll ? table.dataset.excelAllSource : "";
        const source = sourceId ? document.getElementById(sourceId) || table : table;
        const clone = source.cloneNode(true);
        removeRowsFromClone(clone, includeAll);

        const workbook = '<!DOCTYPE html><html><head><meta charset="UTF-8">'
            + '<style>table{border-collapse:collapse}th,td{border:1px solid #999;padding:5px}th{font-weight:bold;background:#dbeaf0}</style>'
            + '</head><body>' + clone.outerHTML + '</body></html>';
        const blob = new Blob(["\ufeff", workbook], { type: "application/vnd.ms-excel;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        const title = table.dataset.excelTitle || "reporte";
        link.href = url;
        link.download = cleanFileName(title) + (includeAll ? "-todo" : "-filtrado") + ".xls";
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
    }

    function addToolbar(table) {
        if (table.dataset.excelAttached === "true") return;
        table.dataset.excelAttached = "true";
        const toolbar = document.createElement("div");
        toolbar.className = "excel-toolbar";
        toolbar.innerHTML = '<span>Descargar:</span>'
            + '<button type="button" class="excel-button">Excel visibles</button>'
            + '<button type="button" class="excel-button excel-button-secondary">Excel todo</button>';
        const buttons = toolbar.querySelectorAll("button");
        buttons[0].addEventListener("click", function () { downloadTable(table, false); });
        buttons[1].addEventListener("click", function () { downloadTable(table, true); });
        const wrapper = table.closest(".table-wrap");
        if (wrapper && wrapper.parentNode) {
            wrapper.parentNode.insertBefore(toolbar, wrapper);
        } else if (table.parentNode) {
            table.parentNode.insertBefore(toolbar, table);
        }
    }

    function scan(root) {
        const tables = root.querySelectorAll
            ? root.querySelectorAll("table[data-excel-table]")
            : [];
        tables.forEach(addToolbar);
    }

    function init() {
        const style = document.createElement("style");
        style.textContent = ".excel-toolbar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:10px 0;color:#425760;font-size:.82rem;font-weight:600}.excel-button{padding:7px 11px;border:1px solid #267d8b;border-radius:5px;color:#fff;background:#267d8b;cursor:pointer;font:inherit}.excel-button:hover{background:#1c626d}.excel-button-secondary{border-color:#5c4b83;background:#5c4b83}.excel-button-secondary:hover{background:#463967}";
        document.head.appendChild(style);
        scan(document);
        const observer = new MutationObserver(function (mutations) {
            mutations.forEach(function (mutation) {
                mutation.addedNodes.forEach(function (node) {
                    if (node.nodeType === 1) scan(node);
                });
            });
        });
        observer.observe(document.body, { childList: true, subtree: true });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
}());
