#!/usr/bin/env bash
# Funções e caminhos usados pelos scripts da VPS. Não execute direto.
set -euo pipefail

BASE=/opt/contask
CODIGO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLIENTES="$BASE/clientes"
BACKUPS="$BASE/backups"
CONF="$BASE/contask.conf"
IMAGEM=contask-nf
REDE=contask
MEMORIA_CLIENTE=600m

erro() { echo "ERRO: $*" >&2; exit 1; }

exigir_root() { [ "$(id -u)" -eq 0 ] || erro "rode como root (sudo)."; }

carregar_conf() {
  [ -f "$CONF" ] || erro "$CONF não existe. Rode primeiro o instalar_vps.sh."
  # shellcheck disable=SC1090
  source "$CONF"
}

validar_cliente() {
  [[ "${1:-}" =~ ^[a-z0-9][a-z0-9-]{1,29}$ ]] || erro "nome do cliente inválido: use 2 a 30 letras minúsculas, números ou hífen (ex.: contabil-silva)."
}

subir_cliente() {
  local c="$1" dir="$CLIENTES/$1"
  [ -f "$dir/cliente.env" ] || erro "cliente $c não existe."
  docker rm -f "contask-$c" >/dev/null 2>&1 || true
  docker run -d --name "contask-$c" --restart unless-stopped --network "$REDE" \
    --memory "$MEMORIA_CLIENTE" --env-file "$dir/cliente.env" \
    -v "$dir/dados:/app/dados" -v "$dir/segredos:/segredos" -v "$BACKUPS/$c:/backups" \
    --log-opt max-size=10m --log-opt max-file=3 \
    "$IMAGEM" >/dev/null
}

esperar_saude() {
  local c="$1"
  for _ in $(seq 1 60); do
    if docker exec "contask-$c" python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/ping', timeout=2)" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  docker logs --tail 40 "contask-$c" >&2 || true
  erro "o contêiner contask-$c não respondeu."
}

usuarios() {
  local c="$1"; shift
  docker exec -w /app/backend "contask-$c" python -m app.tools.usuarios "$@"
}

recarregar_caddy() {
  docker exec contask-caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
}
