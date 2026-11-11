#!/usr/bin/env bash
# Backup diário (cron às 03:30, instalado pelo instalar_vps.sh) e antes de cada atualização.
# - Cópia consistente do banco + XMLs + certificados cifrados de todos os escritórios.
# - Mantém 14 dias na VPS e, se RCLONE_DESTINO estiver definido, copia para fora dela.
# - A chave-mestra (segredos/chave.env) NÃO entra: um backup vazado não abre os certificados.
set -euo pipefail
source "$(dirname "$0")/comum.sh"
exigir_root
carregar_conf

if [ "$(docker inspect -f '{{.State.Running}}' "$CONTEINER" 2>/dev/null || echo false)" != "true" ]; then
  erro "$(date '+%F %T') o sistema está parado: sem backup."
fi
docker exec -w /app/backend "$CONTEINER" python -m app.tools.backup --destino /backups
echo "$(date '+%F %T') backup: ok"

find "$BACKUPS" -name 'contask_backup_*.zip' -mtime +14 -delete

if [ -n "${RCLONE_DESTINO:-}" ]; then
  rclone copy "$BACKUPS" "$RCLONE_DESTINO" --max-age 26h --transfers 2 && echo "$(date '+%F %T') cópia externa: ok"
fi
