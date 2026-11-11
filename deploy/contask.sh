#!/usr/bin/env bash
# Administração do Contask NF no servidor. Só roda como root, por SSH (acesso só com chave).
#
# Escritórios e usuários (não existe cadastro pela tela enquanto CADASTRO=fechado):
#   bash contask.sh escritorio novo "Contábil Silva" ana@silva.com "Ana Silva"
#   bash contask.sh escritorio lista
#   bash contask.sh usuario novo bia@silva.com "Bia" <id do escritório>
#   bash contask.sh usuario lista
#   bash contask.sh usuario senha ana@silva.com          # nova senha inicial (esqueceu a senha)
#   bash contask.sh usuario desativar ana@silva.com | reativar ana@silva.com
#   bash contask.sh usuario admin voce@email.com         # libera o painel de administração (admin-remover tira)
#
# Sistema:
#   bash contask.sh estado | logs [linhas] | reiniciar | parar | iniciar
set -euo pipefail
source "$(dirname "$0")/comum.sh"
exigir_root

GRUPO="${1:-}"; ACAO="${2:-}"
shift 2 2>/dev/null || shift $# || true

case "$GRUPO $ACAO" in
  "escritorio novo")
    [ $# -ge 2 ] || erro "uso: contask.sh escritorio novo \"<nome do escritório>\" <email> \"<nome da pessoa>\""
    contas novo-escritorio "$1" "$2" "${3:-}"
    echo "Envie o endereço, o e-mail e a senha inicial por um canal privado. A troca é obrigatória no primeiro acesso." ;;
  "escritorio lista") contas escritorios ;;
  "usuario novo")
    [ $# -ge 3 ] || erro "uso: contask.sh usuario novo <email> \"<nome>\" <id do escritório>"
    contas criar "$1" "$2" --escritorio "$3" ;;
  "usuario lista") contas listar ;;
  "usuario senha") contas redefinir "${1:?informe o e-mail}" ;;
  "usuario desativar") contas desativar "${1:?informe o e-mail}" ;;
  "usuario reativar") contas reativar "${1:?informe o e-mail}" ;;
  "usuario admin") contas admin "${1:?informe o e-mail}" ;;
  "usuario admin-remover") contas admin "${1:?informe o e-mail}" --remover ;;
  "estado "*) docker ps --filter "name=contask" --format "table {{.Names}}\t{{.Status}}"; docker stats --no-stream "$CONTEINER"; du -sh "$DADOS" "$BACKUPS" ;;
  "logs "*) docker logs --tail "${ACAO:-100}" "$CONTEINER" ;;
  "reiniciar "* | "iniciar "*) subir_app && esperar_saude && echo "Sistema no ar." ;;
  "parar "*) docker stop "$CONTEINER" >/dev/null && echo "Sistema parado." ;;
  *) sed -n '2,17p' "$0"; exit 1 ;;
esac
