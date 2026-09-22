---
name: actualizar-avanzia
description: Usar cuando se solicite actualizar el backup de Avanzia mediante Imple Bot, regenerar reportes de conciliacion o repetir ese proceso y publicar en GitHub.
---

# Actualizar Avanzia

## Alcance
Obtener datos actuales por la conexion SSH de Imple Bot, generar respaldo y reportes, verificar y publicar cuando se solicite. Los SQL compartidos como referencia de actualizaciones ya realizadas NO se ejecutan. El origen se consulta solo en lectura.

## Procedimiento
1. Desde el repositorio `Conciliacion de ctas ctes`, revisar `git status --short`, `git diff` y `git log --oneline -10`. Conservar cambios ajenos.
2. Usar `../imple bot/conexion-flows/.env` (o `AVANZIA_ENV_FILE`) como configuracion privada. No imprimir ni publicar credenciales o claves.
3. Ejecutar `python -u scripts/actualizar_avanzia.py` desde el repositorio. Requiere `requirements.txt` y `paramiko` instalados localmente.
4. El script obtiene un dump completo por SSH, verifica el codigo de salida y marcador final, conserva el respaldo anterior y actualiza `backavanzia.sql`. Crea un tunel local temporal y ejecuta los cuatro generadores localmente, con PostgreSQL en modo solo lectura. No instala dependencias en el servidor.
5. Revisar resultados: cuentas contables (total, asignados, pendientes), cuenta corriente e investigacion usan la base actual. `reporte_conciliacion.html` usa los CSV/pickle historicos locales: declarar esta diferencia; regenerarlo no actualiza sus fuentes desde PostgreSQL.
6. Validar HTML no vacio, referencias a assets, conteos y `git diff --check`. Un error detiene la publicacion. No declarar exito basandose solo en un mensaje del script.
7. Si se pidio push, agregar explicitamente solo reportes y mejoras del procedimiento. No agregar backups ignorados, credenciales, scripts de diagnostico ni borrados ajenos. Revisar diff staged, hacer commit descriptivo en el estilo del repositorio y push normal a la rama configurada. Verificar el hash remoto con `git ls-remote` y el estado local.
8. Informar respaldo generado, conteos, limitaciones de fuentes historicas y enlace al commit. No presentar IDs altos o fechas de comprobantes como fecha de ultima modificacion contable.

## Ejemplo
"Actualiza Avanzia, backup y reportes y pushea; estas queries ya las ejecute" activa este procedimiento sin ejecutar las queries.
