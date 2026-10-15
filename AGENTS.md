# AGENTS.md — agentic-app

Framework (Python 3, só biblioteca padrão) para apps em torno de um resultado de negócio: LLM dentro de workflow
determinístico, humano aprova ações, política em código testado, audit por execução.

## Regras para quem mexe aqui

- Nada de dependência externa obrigatória. Nada de chamada de rede nos testes (`tests/rodar.py` bloqueia socket).
- `FakeLLM` é o padrão. `OllamaLLM` só com `AGENTIC_LLM=ollama`, e só `localhost`. Nenhuma API externa, nenhuma chave.
- Número de política mora em `agentic_app/policies/` como constante + teste de limite. Nunca no prompt.
- Workflow nunca executa ação externa: usa `propor_acao`. Executor só roda em `FilaAprovacao.aprovar`.
- Mudou workflow ou política: rode `bash tests/run.sh` (última linha `OK`) e `bash tests/prova_mutacao.sh`.
- Texto em pt-BR; README e guia em PT/EN/ES. Exemplo é fictício e sem marca de terceiros.
- Versão em `VERSION` (semver `X.YY.ZZ`, só zera os de baixo quando o major muda) + `CHANGELOG.md`.
- Commits com autor `inematds <inematds@gmail.com>`.

## Mapa rápido

`agentic_app/workflow.py` motor · `llm.py` adaptadores · `acoes.py` aprovação · `seguranca.py` RBAC/identidade/audit ·
`gatilhos.py` manual/agendado/evento · `relatorio.py` HTML/PDF · `apps/coaching/` app de referência ·
`templates/` para a empresa adaptar · `docs/` passo a passo e arquitetura · `guia/` página PT/EN/ES.

## Self-learning

Quando o usuário corrigir você, ou você notar um erro seu: antes de continuar, acrescente a lição como regra de
uma linha no TOPO da seção Lessons abaixo.

## Lessons

- (vazio)
