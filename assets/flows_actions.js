(function (root) {
    'use strict';
    var workflow = 'flows-cuentas.yml';

    function definitive(message) {
        var error = new Error(message);
        error.definitive = true;
        return error;
    }

    function createClient(repository, token, options) {
        options = options || {};
        if (!/^[\w.-]+\/[\w.-]+$/.test(repository)) throw definitive('Ingrese el repositorio como propietario/nombre.');
        if (!token) throw definitive('Ingrese un token de GitHub con Actions: lectura/escritura y Checks: lectura.');
        var fetcher = options.fetch || root.fetch.bind(root);
        var sleep = options.sleep || function (ms) { return new Promise(function (resolve) { setTimeout(resolve, ms); }); };
        var base = 'https://api.github.com/repos/' + repository;

        async function request(path, method, body) {
            var controller = new AbortController();
            var timeout = setTimeout(function () { controller.abort(); }, 30000);
            try {
                var response = await fetcher(base + path, {
                    method: method || 'GET', credentials: 'omit', cache: 'no-store', signal: controller.signal,
                    headers: { 'Accept': 'application/vnd.github+json', 'Authorization': 'Bearer ' + token,
                        'Content-Type': 'application/json', 'X-GitHub-Api-Version': '2022-11-28' },
                    body: body ? JSON.stringify(body) : undefined
                });
                if (!response.ok) {
                    var message = response.status === 404 ? 'No se encuentra el repositorio o workflow. Publique flows-cuentas.yml en la rama predeterminada y revise los permisos del token.' :
                        response.status === 401 || response.status === 403 ? 'GitHub rechazó el acceso. Revise el token, sus permisos y el límite de solicitudes.' :
                        'GitHub devolvió HTTP ' + response.status + '.';
                    var error = new Error(message);
                    // Sólo un rechazo explícito del dispatch permite asegurar que no se inició.
                    error.definitive = method === 'POST' && response.status >= 400 && response.status < 500;
                    throw error;
                }
                return response.status === 204 ? null : await response.json();
            } finally { clearTimeout(timeout); }
        }

        return {
            prepare: async function (operation, payload) {
                if (operation !== 'verify' && operation !== 'save') throw definitive('Operación inválida.');
                var text = JSON.stringify(payload);
                if (new TextEncoder().encode(text).length > 48000) throw definitive('Solicitud demasiado grande. Divida los lotes en grupos más pequeños.');
                var repo = await request('');
                return { id: root.crypto.randomUUID(), operation: operation, payload: text,
                    branch: repo.default_branch, since: new Date(Date.now() - 60000).toISOString(), run: null };
            },
            dispatch: function (job) {
                return request('/actions/workflows/' + workflow + '/dispatches', 'POST', {
                    ref: job.branch, inputs: { operation: job.operation, request_id: job.id, payload: job.payload }
                });
            },
            wait: async function (job, progress) {
                var attempts = options.attempts || 90;
                for (var i = 0; i < attempts; i += 1) {
                    if (!job.run) {
                        var runs = await request('/actions/workflows/' + workflow + '/runs?event=workflow_dispatch&per_page=100&created=' + encodeURIComponent('>=' + job.since));
                        job.run = runs.workflow_runs.find(function (run) {
                            return run.display_title === 'flows-' + job.operation + '-' + job.id && run.head_branch === job.branch;
                        }) || null;
                    } else {
                        job.run = await request('/actions/runs/' + job.run.id);
                    }
                    if (progress) progress(job.run);
                    if (job.run && job.run.status === 'completed') {
                        var checks = await request('/commits/' + job.run.head_sha + '/check-runs?per_page=100&check_name=' + encodeURIComponent('flows-result-' + job.id));
                        var check = checks.check_runs.find(function (entry) {
                            return entry.name === 'flows-result-' + job.id && entry.external_id === String(job.run.id) &&
                                entry.status === 'completed' && entry.app && entry.app.slug === 'github-actions';
                        });
                        if (!check || !check.output || !check.output.text) {
                            throw definitive('Actions terminó sin un resultado confirmado (' + job.run.conclusion + '). Revise la ejecución en GitHub; si estaba guardando, reintente con la misma verificación.');
                        }
                        var result = JSON.parse(check.output.text);
                        if (result.request_id !== job.id || result.operation !== job.operation) throw definitive('El resultado no corresponde a esta solicitud.');
                        if (!result.ok) throw definitive(result.error || 'Flows rechazó la operación.');
                        return result;
                    }
                    await sleep(10000);
                }
                throw new Error('La ejecución sigue pendiente o no se pudo localizar. Pulse Consultar ejecución para continuar sin enviar otra operación.');
            }
        };
    }

    root.FlowsActions = { createClient: createClient };
    if (typeof module !== 'undefined' && module.exports) module.exports = root.FlowsActions;
}(typeof window !== 'undefined' ? window : globalThis));
