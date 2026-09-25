"""Respaldo por Imple Bot y reportes locales; solo lectura en PostgreSQL."""
import os
from pathlib import Path
import select
import shlex
import shutil
import socketserver
import subprocess
import sys
import threading
from datetime import datetime

import paramiko
import psycopg2

ROOT = Path(__file__).resolve().parents[1]


def main():
    config_path = Path(os.environ.get('AVANZIA_ENV_FILE', ROOT.parent / 'imple bot' / 'conexion-flows' / '.env'))
    config = {}
    for line in config_path.read_text(encoding='utf-8-sig').splitlines():
        if line.strip() and not line.lstrip().startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            config[key.strip()] = value.strip().strip('"')
    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    # La clave de host se conserva en memoria durante esta operacion.
    ssh.set_missing_host_key_policy(paramiko.WarningPolicy())
    ssh.connect(config['SSH_HOST'], port=int(config['SSH_PORT']),
                username=config['SSH_USER'], key_filename=config['SSH_PRIVATE_KEY_PATH'],
                timeout=30, banner_timeout=30, auth_timeout=30)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = ROOT / ('backavanzia_' + stamp + '.sql')
    partial = backup.with_suffix('.partial')
    try:
        command = ' '.join(shlex.quote(x) for x in [
            'env', 'PGPASSWORD=' + config['PG_PASSWORD'], 'PGOPTIONS=-c default_transaction_read_only=on',
            'pg_dump', '-h', config['SSH_REMOTE_HOST'], '-p', config['SSH_REMOTE_PORT'],
            '-U', config['PG_USER'], '-d', config['PG_DATABASE'], '-F', 'p'])
        _, stdout, stderr = ssh.exec_command(command, timeout=300)
        errors = []
        reader = threading.Thread(target=lambda: errors.append(stderr.read()), daemon=True)
        reader.start()
        with partial.open('wb') as output:
            shutil.copyfileobj(stdout, output)
        status = stdout.channel.recv_exit_status()
        reader.join()
        if status != 0:
            raise RuntimeError(b''.join(errors).decode('utf-8', errors='replace'))
        with partial.open('rb') as check:
            check.seek(max(0, partial.stat().st_size - 4096))
            if b'PostgreSQL database dump complete' not in check.read():
                raise RuntimeError('Respaldo sin marcador de finalizacion')
        partial.replace(backup)
        current = ROOT / 'backavanzia.sql'
        if current.exists():
            shutil.copy2(current, ROOT / ('backavanzia_anterior_' + stamp + '.sql'))
        shutil.copy2(backup, current)
        print('Respaldo completo:', backup.name, backup.stat().st_size, 'bytes', flush=True)

        transport = ssh.get_transport()

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                channel = transport.open_channel('direct-tcpip',
                    (config['SSH_REMOTE_HOST'], int(config['SSH_REMOTE_PORT'])), self.client_address)
                try:
                    while True:
                        ready, _, _ = select.select([self.request, channel], [], [], 30)
                        for source in ready:
                            data = source.recv(65536)
                            if not data:
                                return
                            (channel if source is self.request else self.request).sendall(data)
                finally:
                    channel.close()

        class Server(socketserver.ThreadingTCPServer):
            daemon_threads = True

        with Server(('127.0.0.1', 0), Handler) as server:
            threading.Thread(target=server.serve_forever, daemon=True).start()
            env = os.environ.copy()
            env.update(AVANZIA_DB_HOST='127.0.0.1', AVANZIA_DB_PORT=str(server.server_address[1]),
                       AVANZIA_DB_NAME=config['PG_DATABASE'], AVANZIA_DB_USER=config['PG_USER'],
                       AVANZIA_DB_PASSWORD=config['PG_PASSWORD'], PYTHONIOENCODING='utf-8',
                       PGOPTIONS='-c default_transaction_read_only=on', PGCONNECT_TIMEOUT='15')
            try:
                with psycopg2.connect(host='127.0.0.1', port=server.server_address[1],
                        dbname=config['PG_DATABASE'], user=config['PG_USER'], password=config['PG_PASSWORD'],
                        connect_timeout=15, options='-c default_transaction_read_only=on') as conn:
                    with conn.cursor() as cur:
                        cur.execute('SELECT current_database(), count(*) FROM test9000.registrocab')
                        print('Origen verificado:', cur.fetchone(), flush=True)
                for script in ['reporte_cuentas_contables.py', 'reporte_cuenta_corriente.py',
                                'reporte_investigacion.py', 'reporte_html.py', 'reporte_resultados.py']:
                    subprocess.run([sys.executable, str(ROOT / 'scripts' / script)],
                                   cwd=ROOT, env=env, check=True, timeout=600)
                print('Reportes completados. Conciliacion conserva fuentes historicas CSV/pickle.', flush=True)
            finally:
                server.shutdown()
    finally:
        ssh.close()


if __name__ == '__main__':
    main()
