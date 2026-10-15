# FALHAS

| data | o que quebrou | menor correção | prompt \| infra |
|---|---|---|---|
| 2026-10-15 | `prova_mutacao.sh` deu falso positivo (regra F6 de 14 dias sem teste próprio) e a suíte falhou por `.pyc` velho após restaurar a política | limpar `__pycache__` em `run.sh` e a cada troca do `prova_mutacao.sh`; teste de limite para cada constante | infra |
