#!/usr/bin/env bash
# Prova do pilar 6: mudar um número da política quebra pelo menos um teste.
# Altera um valor por vez, roda a suíte, restaura o arquivo (mesmo se der erro).
set -uo pipefail
cd "$(dirname "$0")/.."
ARQ=agentic_app/policies/ferias.py
BAK=$(mktemp)
cp "$ARQ" "$BAK"
trap 'cp "$BAK" "$ARQ"; rm -f "$BAK"' EXIT
falhou=0
for troca in 's/^BONUS_5_ANOS = 2/BONUS_5_ANOS = 3/' \
             's/"gestante": 180/"gestante": 120/' \
             's/^ANTECEDENCIA_MINIMA_DIAS = 30/ANTECEDENCIA_MINIMA_DIAS = 20/' \
             's/^MIN_PERIODO_PRINCIPAL = 14/MIN_PERIODO_PRINCIPAL = 10/'; do
  cp "$BAK" "$ARQ"; sed -i "$troca" "$ARQ"
  if python3 tests/rodar.py >/dev/null 2>&1; then
    echo "NENHUM teste quebrou com: $troca"; falhou=1
  else
    echo "quebrou (bom): $troca"
  fi
done
cp "$BAK" "$ARQ"
[ $falhou -eq 0 ] && echo OK || { echo FALHOU; exit 1; }
