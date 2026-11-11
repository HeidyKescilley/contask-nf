#!/usr/bin/env bash
# Prepara uma VPS Ubuntu 24.04 limpa e sobe o Contask NF. Rode uma vez, como root:
#   bash /opt/contask/codigo/deploy/instalar_vps.sh contasknf.com.br voce@email.com [subdominio-do-sistema]
# Resultado: site de vendas em https://contasknf.com.br e sistema em https://app.contasknf.com.br
set -euo pipefail
source "$(dirname "$0")/comum.sh"
exigir_root

DOMINIO_BASE="${1:-}"
ACME_EMAIL="${2:-}"
SUBDOMINIO="${3:-app}"
[ -n "$DOMINIO_BASE" ] && [ -n "$ACME_EMAIL" ] || erro "uso: instalar_vps.sh <dominio> <email-para-o-https> [subdominio-do-sistema]"
[[ "$SUBDOMINIO" =~ ^[a-z0-9-]+$ ]] || erro "subdomínio inválido: $SUBDOMINIO"

echo "==> Pacotes do sistema"
apt-get update -q
DEBIAN_FRONTEND=noninteractive apt-get install -y -q docker.io git ufw sqlite3 rclone unattended-upgrades fail2ban
systemctl enable --now docker fail2ban

echo "==> Firewall: só SSH, HTTP e HTTPS"
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp
ufw --force enable

echo "==> SSH só com chave (se já houver chave cadastrada)"
if [ -s /root/.ssh/authorized_keys ]; then
  cat > /etc/ssh/sshd_config.d/10-contask.conf <<EOF
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
EOF
  systemctl reload ssh || systemctl reload sshd || true
  echo "    Senha desligada: só entra quem tem a chave em /root/.ssh/authorized_keys."
else
  echo "    AVISO: nenhuma chave em /root/.ssh/authorized_keys. Cadastre as chaves e rode de novo para desligar a senha."
fi

echo "==> Memória de reserva (swap de 2 GB)"
if ! swapon --show | grep -q /swapfile; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  grep -q /swapfile /etc/fstab || echo "/swapfile none swap sw 0 0" >> /etc/fstab
fi

echo "==> Pastas"
mkdir -p "$DADOS" "$BACKUPS" "$SEGREDOS" "$BASE/caddy/data" "$BASE/caddy/config"
chown 1000:1000 "$DADOS" "$BACKUPS"
chmod 700 "$DADOS" "$BACKUPS" "$SEGREDOS"
cp "$CODIGO/deploy/Caddyfile" "$BASE/caddy/Caddyfile"
if [ ! -f "$CONF" ]; then
  cat > "$CONF" <<EOF
# Configuração do servidor do Contask NF (sem segredos)
DOMINIO_BASE=$DOMINIO_BASE
SUBDOMINIO=$SUBDOMINIO
ACME_EMAIL=$ACME_EMAIL
# Cadastro pela tela: fechado (contas só pelo contask.sh) | convite | aberto
CADASTRO=fechado
# Emissão de NFS-e em produção: false = todos na homologação. Só ligue com liberação expressa.
EMISSOR_PRODUCAO=false
# XMLs novos por mês (0 = sem limite)
LIMITE_XMLS_MES=0
# Cópia dos backups fora da VPS (ex.: r2:contask-backups). Vazio = só local.
RCLONE_DESTINO=
EOF
  chmod 644 "$CONF"
fi

echo "==> Chave-mestra dos certificados"
NOVA_CHAVE=0
if [ ! -f "$SEGREDOS/chave.env" ]; then
  CHAVE=$(python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())")
  umask 077
  echo "CONTASK_CHAVE_MESTRA=$CHAVE" > "$SEGREDOS/chave.env"
  unset CHAVE
  NOVA_CHAVE=1
fi
chmod 600 "$SEGREDOS/chave.env"

echo "==> Imagem do sistema (alguns minutos)"
docker network inspect "$REDE" >/dev/null 2>&1 || docker network create "$REDE"
docker build -t "$IMAGEM" "$CODIGO"

echo "==> Sistema"
subir_app
esperar_saude

echo "==> Caddy (HTTPS)"
docker rm -f contask-caddy >/dev/null 2>&1 || true
docker run -d --name contask-caddy --restart unless-stopped --network "$REDE" \
  -p 80:80 -p 443:443 -p 443:443/udp \
  -e ACME_EMAIL="$ACME_EMAIL" -e DOMINIO_BASE="$DOMINIO_BASE" -e SUBDOMINIO="$SUBDOMINIO" \
  -v "$CODIGO/site:/srv/site:ro" -v "$BASE/caddy/Caddyfile:/etc/caddy/Caddyfile:ro" \
  -v "$BASE/caddy/data:/data" -v "$BASE/caddy/config:/config" \
  --log-opt max-size=10m --log-opt max-file=3 \
  caddy:2.10 >/dev/null

echo "==> Backup diário às 03:30"
cat > /etc/cron.d/contask-backup <<EOF
30 3 * * * root $CODIGO/deploy/backup.sh >> /var/log/contask-backup.log 2>&1
EOF

cat <<EOF

Pronto.
  Site:    https://$DOMINIO_BASE   (o www redireciona para ele)
  Sistema: https://$SUBDOMINIO.$DOMINIO_BASE   (o HTTPS sai em até 1 minuto depois do DNS apontar)

Próximo passo, criar o primeiro escritório:
  bash $CODIGO/deploy/contask.sh escritorio novo "Nome do escritório" email@dele.com "Nome da pessoa"
EOF
if [ "$NOVA_CHAVE" = 1 ]; then
  cat <<EOF

IMPORTANTE: a chave-mestra foi criada em $SEGREDOS/chave.env.
Guarde uma cópia no gerenciador de senhas (veja com: cat $SEGREDOS/chave.env).
Ela NÃO vai no backup, de propósito. Sem ela, os certificados salvos não abrem.
EOF
fi
