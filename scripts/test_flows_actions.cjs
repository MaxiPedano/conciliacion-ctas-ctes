const { test } = require('node:test');
const assert = require('node:assert/strict');
const { createClient } = require('../assets/flows_actions.js');

function fixture(responses, options = {}) {
    const calls = [];
    const client = createClient('owner/repo', 'test-token', {
        attempts: 2,
        sleep: async () => {},
        fetch: async (url, init) => {
            calls.push({ url, ...init });
            const item = responses.shift();
            if (item instanceof Error) throw item;
            assert.ok(item, 'Unexpected request: ' + url);
            return { ok: !item.status || item.status < 400, status: item.status || 200, json: async () => item.body };
        }, ...options
    });
    return { client, calls };
}

function job() {
    return { id: '12345678-1234-1234-1234-123456789abc', operation: 'save',
        branch: 'master', since: '2026-09-18T00:00:00Z', payload: '{}', run: null };
}
function run(j) {
    return { id: 42, display_title: 'flows-save-' + j.id, head_branch: 'master',
        head_sha: 'abc123', status: 'completed', conclusion: 'success' };
}
function check(j, result = {}) {
    return { name: 'flows-result-' + j.id, external_id: '42', status: 'completed', app: { slug: 'github-actions' },
        output: { text: JSON.stringify({ ok: true, request_id: j.id, operation: j.operation, saved: true, ...result }) } };
}

test('dispatch uses default branch and only sends token to GitHub', async () => {
    const { client, calls } = fixture([{ body: { default_branch: 'master' } }, { status: 204 }]);
    const j = await client.prepare('verify', { batches: [] });
    await client.dispatch(j);
    assert.equal(j.branch, 'master');
    assert.match(j.id, /^[a-f0-9-]{36}$/);
    assert.equal(JSON.parse(calls[1].body).inputs.operation, 'verify');
    assert.equal(calls[1].headers.Authorization, 'Bearer test-token');
    assert.equal(calls[1].credentials, 'omit');
    assert.ok(calls.every(call => call.url.startsWith('https://api.github.com/repos/owner/repo')));
});

test('matches exact run and ignores unrelated check results', async () => {
    const j = job();
    const unrelated = { ...check(j), external_id: '99' };
    const { client } = fixture([
        { body: { workflow_runs: [{ ...run(j), display_title: 'another-run' }, run(j)] } },
        { body: { check_runs: [unrelated, check(j)] } }
    ]);
    assert.equal((await client.wait(j)).saved, true);
});

test('server conflicts do not confirm save', async () => {
    const j = job();
    const { client } = fixture([
        { body: { workflow_runs: [run(j)] } },
        { body: { check_runs: [check(j, { ok: false, error: 'Los registros cambiaron' })] } }
    ]);
    await assert.rejects(client.wait(j), error => error.definitive && /cambiaron/.test(error.message));
});

test('ambiguous network error preserves job for polling rather than redispatch', async () => {
    const j = job();
    const { client, calls } = fixture([
        new Error('Network lost'), { body: { workflow_runs: [run(j)] } },
        { body: { check_runs: [check(j)] } }
    ]);
    await assert.rejects(client.dispatch(j), error => !error.definitive);
    assert.equal((await client.wait(j)).saved, true);
    assert.equal(calls.filter(call => call.method === 'POST').length, 1);
});

test('dispatch rejection is definitive', async () => {
    const { client } = fixture([{ status: 403 }]);
    await assert.rejects(client.dispatch(job()), error => error.definitive === true);
});

test('polling timeout can resume the same run', async () => {
    const j = job();
    const { client } = fixture([
        { body: { workflow_runs: [{ ...run(j), status: 'in_progress' }] } },
        { body: { ...run(j), status: 'in_progress' } },
        { body: run(j) }, { body: { check_runs: [check(j)] } }
    ]);
    await assert.rejects(client.wait(j), error => !error.definitive);
    assert.equal(j.run.id, 42);
    assert.equal((await client.wait(j)).saved, true);
});

test('successful workflow without database confirmation is not a saved result', async () => {
    const j = job();
    const { client } = fixture([
        { body: { workflow_runs: [run(j)] } }, { body: { check_runs: [] } }
    ]);
    await assert.rejects(client.wait(j), /sin un resultado confirmado/);
});

test('mismatched operation result is rejected', async () => {
    const j = job();
    const { client } = fixture([
        { body: { workflow_runs: [run(j)] } },
        { body: { check_runs: [check(j, { operation: 'verify' })] } }
    ]);
    await assert.rejects(client.wait(j), /no corresponde/);
});

test('invalid repository and oversized requests rejected before dispatch', async () => {
    assert.throws(() => createClient('https://evil.example', 'token'));
    const { client, calls } = fixture([]);
    await assert.rejects(client.prepare('verify', { data: 'x'.repeat(48000) }), /demasiado grande/);
    assert.equal(calls.length, 0);
});
