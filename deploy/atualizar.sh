#!/usr/bin/env bash
# Publica uma nova versão: baixa o código, faz backup, gera a imagem e reinicia o sistema.
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

echo "==> Reiniciando (alguns segundos fora do ar)"
subir_app
esperar_saude
docker image prune -f >/dev/null

# O site de vendas é lido direto da pasta site/; só o Caddyfile precisa ser recopiado
cp "$CODIGO/deploy/Caddyfile" "$BASE/caddy/Caddyfile" && recarregar_caddy
echo "Atualização concluída: $(git -C "$CODIGO" log --oneline -1)"
