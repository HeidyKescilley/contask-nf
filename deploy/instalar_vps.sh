#!/usr/bin/env bash
# Prepara uma VPS Ubuntu 24.04 limpa para o Contask NF. Rode uma vez, como root:
#   bash /opt/contask/codigo/deploy/instalar_vps.sh contasknf.com.br voce@email.com
set -euo pipefail
source "$(dirname "$0")/comum.sh"
exigir_root

DOMINIO_BASE="${1:-}"
ACME_EMAIL="${2:-}"
[ -n "$DOMINIO_BASE" ] && [ -n "$ACME_EMAIL" ] || erro "uso: instalar_vps.sh <dominio-base> <email-para-o-certificado-https>"

echo "==> Pacotes do sistema"
apt-get update -q
DEBIAN_FRONTEND=noninteractive apt-get install -y -q docker.io git ufw sqlite3 rclone unattended-upgrades
systemctl enable --now docker

echo "==> Firewall: só SSH, HTTP e HTTPS"
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp
ufw --force enable

echo "==> Memória de reserva (swap de 2 GB)"
if ! swapon --show | grep -q /swapfile; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  grep -q /swapfile /etc/fstab || echo "/swapfile none swap sw 0 0" >> /etc/fstab
fi

echo "==> Pastas"
mkdir -p "$CLIENTES" "$BACKUPS" "$BASE/caddy/sites" "$BASE/caddy/data" "$BASE/caddy/config"
chmod 700 "$CLIENTES" "$BACKUPS"
cp "$CODIGO/deploy/Caddyfile" "$BASE/caddy/Caddyfile"
cat > "$CONF" <<EOF
# Configuração da VPS do Contask NF
DOMINIO_BASE=$DOMINIO_BASE
ACME_EMAIL=$ACME_EMAIL
LIMITE_PADRAO=3000
# Destino do rclone para cópia dos backups fora da VPS (ex.: r2:contask-backups). Vazio = só local.
RCLONE_DESTINO=
EOF
chmod 600 "$CONF"

echo "==> Imagem do sistema"
docker network inspect "$REDE" >/dev/null 2>&1 || docker network create "$REDE"
docker build -t "$IMAGEM" "$CODIGO"

echo "==> Caddy (HTTPS)"
docker rm -f contask-caddy >/dev/null 2>&1 || true
docker run -d --name contask-caddy --restart unless-stopped --network "$REDE" \
  -p 80:80 -p 443:443 -p 443:443/udp -e ACME_EMAIL="$ACME_EMAIL" -e DOMINIO_BASE="$DOMINIO_BASE" \
  -v "$CODIGO/site:/srv/site:ro" \
  -v "$BASE/caddy/Caddyfile:/etc/caddy/Caddyfile:ro" -v "$BASE/caddy/sites:/etc/caddy/sites:ro" \
  -v "$BASE/caddy/data:/data" -v "$BASE/caddy/config:/config" \
  --log-opt max-size=10m --log-opt max-file=3 \
  caddy:2.10 >/dev/null

echo "==> Backup diário às 03:30"
cat > /etc/cron.d/contask-backup <<EOF
30 3 * * * root $CODIGO/deploy/backup.sh >> /var/log/contask-backup.log 2>&1
EOF

echo
echo "Pronto. Próximo passo: bash $CODIGO/deploy/novo_cliente.sh <cliente> <email> \"<nome>\""
