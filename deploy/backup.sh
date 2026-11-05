#!/usr/bin/env bash
# Backup diário de todos os escritórios (cron às 03:30, instalado pelo instalar_vps.sh).
# - Cópia consistente do banco + XMLs + certificados cifrados de cada cliente.
# - Mantém 7 dias na VPS e, se RCLONE_DESTINO estiver definido, copia para fora da VPS.
# - As chaves (segredos/chave.key) NÃO entram: backup vazado não abre os certificados.
set -euo pipefail
source "$(dirname "$0")/comum.sh"
exigir_root
carregar_conf

falhas=0
for d in "$CLIENTES"/*/; do
  [ -d "$d" ] || continue
  c=$(basename "$d")
  if [ "$(docker inspect -f '{{.State.Running}}' "contask-$c" 2>/dev/null || echo false)" != "true" ]; then
    echo "$(date '+%F %T') $c: parado, sem backup hoje"
    continue
  fi
  if docker exec -w /app/backend "contask-$c" python -m app.tools.backup --destino /backups; then
    echo "$(date '+%F %T') $c: ok"
  else
    echo "$(date '+%F %T') $c: FALHOU" >&2
    falhas=$((falhas + 1))
  fi
done

find "$BACKUPS" -name 'contask_backup_*.zip' -mtime +7 -delete

if [ -n "${RCLONE_DESTINO:-}" ]; then
  rclone copy "$BACKUPS" "$RCLONE_DESTINO" --max-age 26h --transfers 2 && echo "$(date '+%F %T') cópia externa: ok"
fi

[ "$falhas" -eq 0 ] || exit 1
