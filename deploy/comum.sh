#!/usr/bin/env bash
# Caminhos e funções dos scripts do servidor. Não execute direto.
# Uma instância só atende todos os escritórios (cada um enxerga apenas os próprios dados).
set -euo pipefail

BASE=/opt/contask
CODIGO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DADOS="$BASE/dados"
BACKUPS="$BASE/backups"
SEGREDOS="$BASE/segredos"
CONF="$BASE/contask.conf"
IMAGEM=contask-nf
REDE=contask
CONTEINER=contask-app
MEMORIA=1g
# Gerador oficial do DANFSe (Receita Federal), só na rede interna: sem porta aberta para fora
DANFSE_IMAGEM=contask-danfse
DANFSE_CONTEINER=contask-danfse

erro() { echo "ERRO: $*" >&2; exit 1; }

exigir_root() { [ "$(id -u)" -eq 0 ] || erro "rode como root (sudo)."; }

carregar_conf() {
  [ -f "$CONF" ] || erro "$CONF não existe. Rode primeiro o instalar_vps.sh."
  # shellcheck disable=SC1090
  source "$CONF"
}

# Variáveis do sistema: as de contask.conf (públicas) + a chave-mestra (segredos/chave.env, só root lê)
subir_app() {
  carregar_conf
  [ -f "$SEGREDOS/chave.env" ] || erro "$SEGREDOS/chave.env não existe."
  docker rm -f "$CONTEINER" >/dev/null 2>&1 || true
  docker run -d --name "$CONTEINER" --restart unless-stopped --network "$REDE" --memory "$MEMORIA" \
    --env-file "$SEGREDOS/chave.env" \
    -e CONTASK_HOSTS="$SUBDOMINIO.$DOMINIO_BASE" \
    -e CONTASK_CADASTRO="${CADASTRO:-fechado}" \
    -e CONTASK_EMISSOR_PRODUCAO="${EMISSOR_PRODUCAO:-false}"     -e CONTASK_LEIAUTE_PRODUCAO="${LEIAUTE_PRODUCAO:-nt004}" \
    -e CONTASK_LIMITE_XMLS_MES="${LIMITE_XMLS_MES:-0}"     -e CONTASK_DANFSE_URL="http://$DANFSE_CONTEINER:8080" \
    -v "$DADOS:/app/dados" -v "$BACKUPS:/backups" \
    --log-opt max-size=10m --log-opt max-file=5 \
    "$IMAGEM" >/dev/null
}

# Se o gerador da Receita cair, o sistema usa o gerador próprio (mesma NT 008) e segue no ar.
construir_danfse() {
  docker build -q -t "$DANFSE_IMAGEM" "$CODIGO/deploy/danfse" >/dev/null
}

subir_danfse() {
  docker rm -f "$DANFSE_CONTEINER" >/dev/null 2>&1 || true
  docker run -d --name "$DANFSE_CONTEINER" --restart unless-stopped --network "$REDE" --memory 256m     --read-only --cap-drop ALL --security-opt no-new-privileges     -e LOG_LEVEL=warn --log-opt max-size=10m --log-opt max-file=3     "$DANFSE_IMAGEM" >/dev/null
}

esperar_saude() {
  for _ in $(seq 1 90); do
    if docker exec "$CONTEINER" python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/ping', timeout=2)" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  docker logs --tail 40 "$CONTEINER" >&2 || true
  erro "o sistema não respondeu depois de 90 segundos."
}

contas() {
  docker exec -w /app/backend "$CONTEINER" python -m app.tools.usuarios "$@"
}

recarregar_caddy() {
  docker exec contask-caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
}
