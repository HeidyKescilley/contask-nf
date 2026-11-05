#!/usr/bin/env bash
# Cria a instância de um escritório: pasta, contêiner, endereço HTTPS e primeiro usuário.
#   bash novo_cliente.sh contabil-silva ana@contabilsilva.com.br "Ana Silva" [limite_xmls_mes]
# Endereço criado: https://contabil-silva.<DOMINIO_BASE>
set -euo pipefail
source "$(dirname "$0")/comum.sh"
exigir_root
carregar_conf

C="${1:-}"; EMAIL="${2:-}"; NOME="${3:-}"; LIMITE="${4:-$LIMITE_PADRAO}"
validar_cliente "$C"
[ -n "$EMAIL" ] || erro "uso: novo_cliente.sh <cliente> <email> \"<nome>\" [limite_xmls_mes]"
[[ "$LIMITE" =~ ^[0-9]+$ ]] || erro "limite inválido: $LIMITE"
DIR="$CLIENTES/$C"
[ ! -e "$DIR" ] || erro "o cliente $C já existe ($DIR)."
DOMINIO="$C.$DOMINIO_BASE"

echo "==> Pastas de $C"
mkdir -p "$DIR/dados" "$DIR/segredos" "$BACKUPS/$C"
cat > "$DIR/cliente.env" <<EOF
CONTASK_DOMINIO=$DOMINIO
CONTASK_LIMITE_XMLS_MES=$LIMITE
EOF
chown -R 1000:1000 "$DIR/dados" "$DIR/segredos" "$BACKUPS/$C"
chmod 700 "$DIR/segredos"

echo "==> Contêiner"
subir_cliente "$C"
esperar_saude "$C"

echo "==> Endereço HTTPS"
cat > "$BASE/caddy/sites/$C.caddy" <<EOF
$DOMINIO {
	encode zstd gzip
	reverse_proxy contask-$C:8765
}
EOF
recarregar_caddy

echo "==> Primeiro usuário"
usuarios "$C" criar "$EMAIL" "$NOME"

cat <<EOF

Cliente $C criado: https://$DOMINIO
Limite: $LIMITE XMLs novos por mês.
Envie o endereço, o e-mail e a senha inicial acima ao cliente por um canal privado.
A chave dos certificados deste cliente está em $DIR/segredos/chave.key: guarde uma cópia
no seu gerenciador de senhas (ela não vai no backup, de propósito).
EOF
