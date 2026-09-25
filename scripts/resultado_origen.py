"""Consultas JSON de solo lectura para el estado de resultados."""
import json
import shlex
from pathlib import Path
import paramiko

ROOT = Path(__file__).resolve().parents[1]

class Origen:
    def __enter__(self):
        config = {}
        for line in (ROOT.parent / 'imple bot/conexion-flows/.env').read_text(encoding='utf-8-sig').splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                k, v = line.split('=', 1)
                config[k.strip()] = v.strip().strip('"')
        self.ssh = paramiko.SSHClient()
        self.ssh.load_system_host_keys()
        self.ssh.set_missing_host_key_policy(paramiko.WarningPolicy())
        self.ssh.connect(config['SSH_HOST'], port=int(config['SSH_PORT']), username=config['SSH_USER'],
                         key_filename=config['SSH_PRIVATE_KEY_PATH'], timeout=30)
        self.command = ' '.join(map(shlex.quote, ['env', 'PGPASSWORD=' + config['PG_PASSWORD'],
            'PGCLIENTENCODING=UTF8', 'PGOPTIONS=-c default_transaction_read_only=on -c statement_timeout=120000',
            'psql', '-X', '-h', config['SSH_REMOTE_HOST'], '-p', config['SSH_REMOTE_PORT'],
            '-U', config['PG_USER'], '-d', config['PG_DATABASE'], '-A', '-t', '-v', 'ON_ERROR_STOP=1']))
        return self

    def query(self, sql):
        stdin, stdout, stderr = self.ssh.exec_command(self.command, timeout=240)
        stdin.write('SELECT COALESCE(json_agg(q),\'[]\'::json) FROM (' + sql.rstrip(';') + ') q;')
        stdin.channel.shutdown_write()
        raw = stdout.read().decode('utf-8')
        err = stderr.read().decode('utf-8')
        if stdout.channel.recv_exit_status():
            raise RuntimeError(err)
        return json.loads(raw)

    def __exit__(self, *args):
        self.ssh.close()

if __name__ == '__main__':
    import sys
    with Origen() as origen:
        print(json.dumps(origen.query(sys.argv[1]), ensure_ascii=True, indent=2))
