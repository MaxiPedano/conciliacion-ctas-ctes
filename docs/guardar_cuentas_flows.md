# GitHub Pages → GitHub Actions → SSH → Flows

El reporte permite **asignar → verificar → guardar** sin alojar una API ni
mantener un servidor adicional. Cada botón inicia un ejecutor temporal de
GitHub Actions, abre el túnel SSH, consulta/actualiza PostgreSQL y lo cierra.
La respuesta se publica en GitHub Checks y Pages la consulta con la API de GitHub.

## 1. Publicar la implementación

Publicar en la rama predeterminada del repositorio ejecutor (actualmente
`master` en `MaxiPedano/conciliacion-ctas-ctes`):

- `.github/workflows/flows-cuentas.yml`
- `scripts/flows_accounts.py`, `scripts/flows_actions.py`, `scripts/requirements-flows.txt`

Publicar en GitHub Pages el reporte actualizado y ambos archivos
`assets/flows_actions.js` y `assets/asignacion_cuentas.js`.
Habilitar GitHub Actions en el repositorio. El workflow sólo ejecuta la rama
predeterminada, tiene `contents: read` y `checks: write`, y no hace commits.

El repositorio actual es **público**: los resultados de Checks contienen IDs,
cuentas y un comprobante firmado, visibles a quienes puedan leer el repositorio.
Para que las operaciones sean privadas, colocar el workflow y los tres archivos
Python/dependencias en un repositorio **privado**, configurar sus Secrets e
ingresar ese `propietario/repositorio` en el reporte de Pages. El comprobante no
contiene credenciales y está ligado al usuario de GitHub que verificó.

## 2. Cargar GitHub Secrets

En el **repositorio ejecutor**: Settings → Secrets and variables → Actions →
New repository secret. No subir `.env` ni la clave privada al repositorio.

| Secret | Valor |
|---|---|
| `FLOWS_SSH_HOST` | Host del servidor SSH existente |
| `FLOWS_SSH_PORT` | Puerto SSH; por defecto `1990` |
| `FLOWS_SSH_USER` | Usuario SSH de la conexión existente |
| `FLOWS_SSH_PRIVATE_KEY` | Contenido completo de la clave OpenSSH, no su ruta ni el `.ppk` |
| `FLOWS_SSH_KNOWN_HOSTS` | Línea `known_hosts` del host y puerto, con huella validada |
| `FLOWS_DB_NAME` | `va9000-avanzia` |
| `FLOWS_DB_USER` | Usuario PostgreSQL autorizado |
| `FLOWS_DB_PASSWORD` | Contraseña PostgreSQL |
| `FLOWS_SIGNING_KEY` | Secreto aleatorio de al menos 32 caracteres para firmar verificaciones |

Generar el último valor localmente:

```text
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

La conexión existente está documentada en
`imple bot/conexion-flows/.env.example` y
`imple bot/docs/02-conexion-y-conocimiento-va9000-avanzia.md`.
El ejecutor hace `127.0.0.1:5434 → SSH → 127.0.0.1:5432`.
La clave debe funcionar sin contraseña interactiva. El servidor SSH debe admitir
conexiones desde los ejecutores de GitHub y reenvío de puertos.

Obtener la entrada candidata de host con `ssh-keyscan -p PUERTO HOST` y cotejar
su huella con el administrador antes de cargarla. Se usa
`StrictHostKeyChecking=yes`; no se acepta automáticamente un host desconocido.

El usuario PostgreSQL necesita `USAGE` sobre `test9000`, `SELECT` sobre
`categorias` y `registrocab`, y `UPDATE(cuentacontableid)` sobre `registrocab`.
Los bloqueos `FOR SHARE` del catálogo requieren `UPDATE` sobre al menos una
columna de `categorias` (por ejemplo `UPDATE(name)`). El proceso no modifica
el catálogo.

## 3. Token para los botones de Pages

Crear un **fine-grained personal access token** en GitHub → Settings → Developer
settings → Personal access tokens, limitado al repositorio ejecutor:

- **Actions: Read and write**: iniciar workflows y consultar sus ejecuciones.
- **Checks: Read-only**: recuperar el resultado de verificación/guardado.
- **Metadata: Read-only**: incluido por GitHub.

El usuario debe tener acceso de escritura al repositorio. Si una organización
requiere aprobar el token, completar esa aprobación. Ingresarlo en el campo
**Token de GitHub** del reporte; no colocarlo en el HTML ni en los Secrets de
Flows. El token se mantiene sólo en memoria mientras la página está abierta.
Sólo el nombre del repositorio se recuerda en `localStorage`.

## 4. Uso

1. Filtrar **Sin cuenta contable**, seleccionar registros y agregar lotes con
   las cuentas elegidas. Máximo 1000 registros y 100 lotes por operación.
2. Indicar el repositorio ejecutor y el token de GitHub.
3. Pulsar **Verificar en Flows**. Actions abre SSH, valida las cuentas contra el
   catálogo y comprueba que los registros aún no tengan cuenta. Pages muestra
   el resultado y las cuentas leídas de la base.
4. Revisar y pulsar **Guardar en Flows** dentro de los 30 minutos siguientes.
   Actions valida el comprobante firmado, usuario y repositorio, bloquea las
   filas y comprueba que no hayan cambiado. Guarda todo en una transacción.
5. El reporte marca **Guardado en Flows** sólo tras recibir la confirmación de
   la base. Un fallo/conflicto revierte todos los lotes de esa operación.

Cada ejecución puede tardar varios minutos en arrancar. El enlace **Ver ejecución
en GitHub** permite seguirla. Si se corta Internet, **Consultar ejecución**
recupera la misma solicitud sin volver a enviarla. Mientras siga pendiente,
los lotes quedan bloqueados para conservar la correspondencia con la operación.
Mantener abierta la pestaña: el token, los lotes y el comprobante no se persisten.

Si Actions terminó sin confirmación (por ejemplo, falló la publicación del
resultado después del commit), **Guardar** puede reintentarse con la misma
verificación: si todos los registros ya tienen las cuentas solicitadas,
confirma el estado sin escribir de nuevo. Una verificación vencida exige volver
a verificar; si los registros ya tienen cuenta, regenerar el reporte para ver
el estado actual. La acción puede seguir ejecutándose aunque se cierre Pages.

Este circuito asigna cuentas sólo a registros pendientes de los cinco flujos
del reporte; no reemplaza cuentas ya asignadas. Modifica exclusivamente
`test9000.registrocab.cuentacontableid`. Los totales/resúmenes del HTML publicado
son una instantánea: regenerar y publicar el reporte para actualizarlos para
todos los usuarios. El generador admite `AVANZIA_DB_PORT=5434` para usar el túnel.

## 5. Verificación de la implementación

```text
python -m pip install -r scripts/requirements-flows.txt
python -m unittest scripts.test_flows_accounts -v
node --test scripts/test_flows_actions.cjs
node --check assets/asignacion_cuentas.js
```

Las pruebas no escriben en Flows: usan conexiones y respuestas GitHub simuladas.
Después de publicar y configurar Secrets, verificar un lote pequeño desde
Pages y confirmar su guardado en Flows. No es necesario instalar servicios,
Flask, Waitress ni un servidor HTTPS adicional.
