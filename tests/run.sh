#!/usr/bin/env bash
# Suíte completa do agentic-app: sem rede, sem chave, só biblioteca padrão.
# Última linha impressa = OK quando tudo passa.
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONDONTWRITEBYTECODE=1
unset AGENTIC_LLM || true
python3 tests/rodar.py
echo OK
