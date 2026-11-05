#!/usr/bin/env bash
# Publica uma nova versão: baixa o código, gera a imagem e reinicia cada escritório.
# As migrações do banco rodam sozinhas na abertura; as buscas continuam do NSU salvo.
set -euo pipefail
source "$(dirname "$0")/comum.sh"
exigir_root

echo "==> Código"
git -C "$CODIGO" pull --ff-only

echo "==> Backup antes de atualizar"
bash "$CODIGO/deploy/backup.sh"

echo "==> Imagem"
docker build -t "$IMAGEM" "$CODIGO"

for d in "$CLIENTES"/*/; do
  [ -d "$d" ] || continue
  c=$(basename "$d")
  if [ "$(docker inspect -f '{{.State.Status}}' "contask-$c" 2>/dev/null || true)" = "exited" ]; then
    echo "--> $c está parado: mantido parado"
    continue
  fi
  echo "--> $c"
  subir_cliente "$c"
  esperar_saude "$c"
done
docker image prune -f >/dev/null
# O site de vendas é lido direto da pasta site/ do git; só o Caddyfile precisa ser recopiado
cp "$CODIGO/deploy/Caddyfile" "$BASE/caddy/Caddyfile" && recarregar_caddy
echo "Atualização concluída."
