# Changelog

## 1.0.0 — 2026-10-15

Primeira versão.

- Motor de workflow em JSON com 5 tipos de nó: `contexto`, `codigo`, `condicao`, `llm`, `formatacao`
  (+ `proximo`/`$fim`, `para_cada`, validação de esquema na entrada e na saída).
- Adaptador de LLM: `FakeLLM` determinístico (padrão) e `OllamaLLM` local opcional (`AGENTIC_LLM=ollama`);
  modelo escolhido pela tarefa (`classificacao`, `redacao`, `resumo`, `agente`).
- Humano no comando: `FilaAprovacao` com edição de campos permitidos, aprovar/rejeitar por papel, caixa de saída simulada.
- Segurança: papéis por workflow, identidades com escopo, audit log JSONL com hash encadeado.
- Gatilhos: manual (componente da tela), agendado (dia + hora, relógio injetável), evento.
- Política codificada: `policies/ferias.py` (manual fictício de RH, regras F1–F6 e P1–P4, 3 funções com entrada estrita).
- App de referência Coaching de gestor: 12 liderados fictícios, 5 workflows, painel web (`python3 -m agentic_app.serve`),
  demo no terminal (`python3 -m agentic_app.demo`), relatório HTML + PDF sem dependência.
- `templates/`: canvas de resultado, modelo de workflow, modelo de política + teste, matriz de permissões.
- Testes: `tests/run.sh` com 48 checks sem rede; `tests/prova_mutacao.sh` prova que mudar 9 números da política quebra testes.
- Docs: README PT/EN/ES, `docs/PASSO-A-PASSO.md` (10 passos + checklist), `docs/ARQUITETURA.md`, guia PT/EN/ES.
