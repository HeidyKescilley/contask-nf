#!/usr/bin/env bash
# Operação do dia a dia de um cliente:
#   bash cliente.sh lista
#   bash cliente.sh <cliente> parar | iniciar | logs | estado
#   bash cliente.sh <cliente> liberar        # fim do teste grátis: libera empresas e histórico
#   bash cliente.sh <cliente> limite 5000
#   bash cliente.sh <cliente> usuarios criar|redefinir|desativar|listar [email] ["nome"]
set -euo pipefail
source "$(dirname "$0")/comum.sh"
exigir_root

if [ "${1:-}" = "lista" ]; then
  printf "%-30s %-12s %s\n" CLIENTE ESTADO DADOS
  for d in "$CLIENTES"/*/; do
    [ -d "$d" ] || continue
    c=$(basename "$d")
    estado=$(docker inspect -f '{{.State.Status}}' "contask-$c" 2>/dev/null || echo "ausente")
    printf "%-30s %-12s %s\n" "$c" "$estado" "$(du -sh "$d/dados" 2>/dev/null | cut -f1)"
  done
  exit 0
fi

C="${1:-}"; ACAO="${2:-}"
validar_cliente "$C"
[ -d "$CLIENTES/$C" ] || erro "cliente $C não existe."
shift 2 || true

case "$ACAO" in
  parar)    docker stop "contask-$C" >/dev/null && echo "$C parado (o endereço mostra erro até reativar)." ;;
  iniciar)  subir_cliente "$C" && esperar_saude "$C" && echo "$C no ar." ;;
  logs)     docker logs --tail "${1:-100}" -f "contask-$C" ;;
  estado)   docker stats --no-stream "contask-$C" ;;
  limite)
    [[ "${1:-}" =~ ^[0-9]+$ ]] || erro "uso: cliente.sh $C limite <xmls_por_mes> (0 = sem limite)"
    sed -i "s/^CONTASK_LIMITE_XMLS_MES=.*/CONTASK_LIMITE_XMLS_MES=$1/" "$CLIENTES/$C/cliente.env"
    subir_cliente "$C" && esperar_saude "$C" && echo "Limite de $C: $1 XMLs por mês." ;;
  liberar)
    env="$CLIENTES/$C/cliente.env"
    if grep -q "^CONTASK_TESTE=" "$env"; then sed -i "s/^CONTASK_TESTE=.*/CONTASK_TESTE=false/" "$env"
    else echo "CONTASK_TESTE=false" >> "$env"; fi
    subir_cliente "$C" && esperar_saude "$C"
    echo "$C liberado: as buscas continuam de onde o teste parou, com todas as empresas e o histórico completo." ;;
  usuarios) usuarios "$C" "$@" ;;
  *) erro "ação desconhecida: $ACAO (parar, iniciar, logs, estado, liberar, limite, usuarios)" ;;
esac
