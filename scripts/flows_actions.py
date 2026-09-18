"""Runner efímero: evento GitHub → túnel SSH → PostgreSQL → resultado Checks API."""
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import tempfile
import time
from contextlib import contextmanager
from urllib.request import Request, urlopen

from flows_accounts import Conflict, execute


@contextmanager
def tunnel():
    for name in ('SSH_HOST', 'SSH_USER', 'SSH_PRIVATE_KEY', 'SSH_KNOWN_HOSTS',
                 'PG_DATABASE', 'PG_USER', 'PG_PASSWORD', 'FLOWS_SIGNING_KEY'):
        if not os.environ.get(name):
            raise ValueError('Falta configurar el Secret correspondiente a ' + name + '.')
    host, user = os.environ['SSH_HOST'], os.environ['SSH_USER']
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]*', host) or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_-]*', user):
        raise ValueError('Host o usuario SSH inválido.')
    port = int(os.getenv('SSH_PORT') or '1990')
    if not 1 <= port <= 65535:
        raise ValueError('Puerto SSH inválido.')
    with tempfile.TemporaryDirectory() as directory:
        key = Path(directory) / 'key'
        hosts = Path(directory) / 'known_hosts'
        key.write_text(os.environ['SSH_PRIVATE_KEY'].replace('\r\n', '\n').strip() + '\n')
        hosts.write_text(os.environ['SSH_KNOWN_HOSTS'].strip() + '\n')
        key.chmod(0o600)
        # Sin shell, sin interpolar payload ni secretos dentro de comandos de shell.
        process = subprocess.Popen([
            'ssh', '-N', '-T', '-i', str(key), '-p', str(port),
            '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes',
            '-o', 'StrictHostKeyChecking=yes', '-o', 'UserKnownHostsFile=' + str(hosts),
            '-o', 'ExitOnForwardFailure=yes', '-o', 'ConnectTimeout=15',
            '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=2',
            '-L', '127.0.0.1:5434:127.0.0.1:5432', user + '@' + host],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(40):
                if process.poll() is not None:
                    raise RuntimeError('No se pudo abrir el túnel SSH. Revise host, clave y known_hosts.')
                try:
                    with socket.create_connection(('127.0.0.1', 5434), timeout=1):
                        break
                except OSError:
                    time.sleep(0.5)
            else:
                raise RuntimeError('El túnel SSH no respondió a tiempo.')
            yield
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def publish(request_id, result):
    text = json.dumps(result, ensure_ascii=True, separators=(',', ':'))
    if len(text.encode()) > 60000:
        raise ValueError('Resultado demasiado grande; reduzca el tamaño de los lotes.')
    payload = {
        'name': 'flows-result-' + request_id,
        'head_sha': os.environ['GITHUB_SHA'],
        'external_id': os.environ['GITHUB_RUN_ID'],
        'status': 'completed',
        'conclusion': 'success' if result['ok'] else 'failure',
        'output': {'title': 'Resultado de cuentas contables',
                   'summary': 'Operación finalizada. Resultado para el reporte de Pages.', 'text': text}}
    request = Request('https://api.github.com/repos/' + os.environ['GITHUB_REPOSITORY'] + '/check-runs',
                      data=json.dumps(payload).encode(), method='POST', headers={
                          'Authorization': 'Bearer ' + os.environ['GH_TOKEN'],
                          'Accept': 'application/vnd.github+json',
                          'Content-Type': 'application/json', 'X-GitHub-Api-Version': '2022-11-28'})
    with urlopen(request, timeout=30) as response:
        response.read()


def main():
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    inputs = event.get('inputs', {})
    request_id = inputs.get('request_id', '')
    if not re.fullmatch(r'[a-f0-9-]{36}', request_id):
        raise ValueError('Identificador de solicitud inválido.')
    operation = inputs.get('operation')
    try:
        raw = inputs.get('payload', '')
        if len(raw.encode()) > 48000:
            raise ValueError('Solicitud demasiado grande; divida los lotes.')
        payload = json.loads(raw)
        with tunnel():
            result = execute(operation, payload, os.environ['FLOWS_SIGNING_KEY'],
                             os.environ['GITHUB_REPOSITORY'], os.environ['GITHUB_ACTOR'])
        result.update(ok=True, request_id=request_id, operation=operation)
    except (ValueError, Conflict) as exc:
        result = dict(ok=False, error=str(exc), request_id=request_id, operation=operation)
    except Exception:
        # No imprimir DSN, contraseñas ni excepciones del driver en logs públicos.
        result = dict(ok=False, error='No se pudo confirmar la operación. Revise los Secrets, SSH y PostgreSQL; si estaba guardando, reintente con la misma verificación.',
                      request_id=request_id, operation=operation)
    publish(request_id, result)
    print('Resultado enviado a GitHub Checks. No se imprimen credenciales ni lotes.')
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
