"""Operaciones transaccionales ejecutadas por GitHub Actions a través de SSH."""
import os
import re

import psycopg2
from itsdangerous import BadData, URLSafeTimedSerializer

FLOW_IDS = [10150, 10303, 11344, 11433, 11332]


class Conflict(Exception):
    pass


def normalize(payload):
    batches = payload.get('batches') if isinstance(payload, dict) else None
    if not isinstance(batches, list) or not 1 <= len(batches) <= 100:
        raise ValueError('Se requieren entre 1 y 100 lotes.')
    result, seen = [], set()
    def identifier(value):
        if not re.fullmatch(r'[1-9][0-9]{0,17}', str(value)):
            raise ValueError('Identificador inválido.')
        return int(value)
    for batch in batches:
        if not isinstance(batch, dict) or not isinstance(batch.get('record_ids'), list) or not batch['record_ids']:
            raise ValueError('Cada lote debe incluir registros.')
        account = identifier(batch.get('account_id'))
        ids = sorted(identifier(value) for value in batch['record_ids'])
        for record in ids:
            if record in seen:
                raise ValueError('Hay registros repetidos entre los lotes.')
            seen.add(record)
        result.append({'account_id': account, 'record_ids': ids})
    if len(seen) > 1000:
        raise ValueError('El máximo es 1000 registros por operación.')
    return result


def connect():
    return psycopg2.connect(
        host=os.getenv('PG_HOST', '127.0.0.1'), port=os.getenv('PG_PORT', '5434'),
        dbname=os.environ['PG_DATABASE'], user=os.environ['PG_USER'],
        password=os.environ['PG_PASSWORD'], connect_timeout=10,
        application_name='conciliacion_github_actions')


def inspect(cursor, batches, lock=False):
    accounts = sorted({batch['account_id'] for batch in batches})
    cursor.execute("""SELECT c.id, c.name FROM test9000.categorias c
        JOIN test9000.categorias pa ON pa.id = c.parentid
        WHERE c.id = ANY(%s) AND c.grupo = 'cuentacontable'
        AND pa.parentid IS NOT NULL FOR SHARE OF c, pa""", (accounts,))
    names = dict(cursor.fetchall())
    if set(names) != set(accounts):
        raise Conflict('Una cuenta no existe o no pertenece al catálogo contable permitido.')
    ids = sorted(record for batch in batches for record in batch['record_ids'])
    cursor.execute("""SELECT id, cuentacontableid, xmin::text FROM test9000.registrocab
        WHERE id = ANY(%s) AND flowid = ANY(%s) ORDER BY id""" +
        (' FOR UPDATE' if lock else ''), (ids, FLOW_IDS))
    records = {str(row[0]): {'account': row[1], 'version': row[2]} for row in cursor.fetchall()}
    if set(records) != {str(value) for value in ids}:
        raise Conflict('Hay registros inexistentes o fuera de los flujos permitidos.')
    return names, records


def execute(operation, payload, key, repository, actor, connection_factory=connect):
    if len(key) < 32:
        raise ValueError('Configure FLOWS_SIGNING_KEY con al menos 32 caracteres aleatorios.')
    signer = URLSafeTimedSerializer(key, salt='flows-actions-v1')
    verified = None
    if operation == 'verify':
        batches = normalize(payload)
    elif operation == 'save':
        if not isinstance(payload, dict) or not isinstance(payload.get('verification_token'), str):
            raise ValueError('Primero verifique las asignaciones.')
        try:
            verified = signer.loads(payload['verification_token'], max_age=1800)
        except BadData:
            raise Conflict('La verificación venció o no es válida. Vuelva a verificar.')
        if verified.get('repository') != repository or verified.get('actor') != actor:
            raise Conflict('La verificación pertenece a otro repositorio o usuario de GitHub.')
        batches = normalize(verified)
    else:
        raise ValueError('Operación inválida.')
    connection = connection_factory()
    try:
        with connection, connection.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout = '15s'")
            cursor.execute("SET LOCAL lock_timeout = '5s'")
            names, records = inspect(cursor, batches, lock=operation == 'save')
            if operation == 'verify':
                if any(row['account'] is not None for row in records.values()):
                    raise Conflict('Hay registros que ya tienen cuenta en Flows. Actualice el reporte antes de continuar.')
                token = signer.dumps({'batches': batches, 'records': records,
                                      'repository': repository, 'actor': actor})
                result = dict(verification_token=token, count=len(records), expires_in=1800,
                              batches=[dict(batch, account_name=names[batch['account_id']]) for batch in batches])
            else:
                # Permite recuperar un guardado confirmado en BD cuya respuesta se perdió.
                already_saved = all(records[str(record)]['account'] == batch['account_id']
                                    for batch in batches for record in batch['record_ids'])
                if not already_saved:
                    if records != verified['records']:
                        raise Conflict('Los registros cambiaron después de verificar. No se guardó ningún lote; vuelva a verificar.')
                    for batch in batches:
                        cursor.execute("""UPDATE test9000.registrocab SET cuentacontableid = %s
                            WHERE id = ANY(%s) AND cuentacontableid IS NULL RETURNING id""",
                                       (batch['account_id'], batch['record_ids']))
                        if len(cursor.fetchall()) != len(batch['record_ids']):
                            raise Conflict('No se pudo guardar el lote completo. Se revirtió toda la operación.')
                result = dict(saved=True, count=len(records), already_saved=already_saved)
        return result  # El commit ya terminó antes de confirmar el éxito.
    finally:
        connection.close()
