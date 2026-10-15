# agentic-app

**🇧🇷 [Português](README.md) · 🇺🇸 [English](README.en.md) · 🇪🇸 [Español](README.es.md)**

[![Agentic App](guia/assets/banner.jpg)](https://inematds.github.io/agentic-app/guia/)

## O que é

O agentic-app é um framework em Python para empresas construírem apps de IA a partir de um resultado de negócio, e não a partir do agente. Ele serve para quem precisa colocar IA dentro de um processo real (RH, gestão de pessoas, atendimento) com controle: o LLM roda dentro de um workflow fixo, toda ação externa espera aprovação humana, regras com número viram código testado e cada execução fica registrada. Vem com um app completo de exemplo (coaching de gestor) e roda só com o Python 3 instalado, sem chave e sem internet.

## 📖 Guia de uso

Guia completo (landing + passo a passo): **https://inematds.github.io/agentic-app/guia/**

## Em 2 minutos

```bash
git clone https://github.com/inematds/agentic-app
cd agentic-app
bash tests/run.sh                 # 47 checks, sem rede -> última linha OK
python3 -m agentic_app.demo       # roda os 5 workflows e gera saida/relatorio.html
python3 -m agentic_app.serve      # painel em http://127.0.0.1:8765
```

Nada para instalar além do Python 3.10+. O LLM padrão é o `FakeLLM` (determinístico). Para usar um modelo local:
`AGENTIC_LLM=ollama python3 -m agentic_app.demo` (Ollama em `localhost:11434`).

## Os 9 pilares (e onde cada um está no código)

| # | Pilar | Onde |
|---|---|---|
| 1 | **Resultado de negócio primeiro** — quem usa, que decisão, qual métrica | `templates/canvas-resultado.md`, campo `resultado_de_negocio` de cada workflow |
| 2 | **LLM dentro de workflow determinístico** — 5 tipos de nó: contexto → código → condição → LLM → formatação; modelo escolhido pela tarefa | `agentic_app/workflow.py`, `agentic_app/config.py` |
| 3 | **Componente de UI chama workflow** — resultado volta para a própria tela (rascunho editável) | `agentic_app/painel.html`, `agentic_app/serve.py` |
| 4 | **Humano no comando** — workflow só PROPÕE; enviar exige revisar, editar e aprovar | `agentic_app/acoes.py` |
| 5 | **Agentes de fundo** — observam os dados e sugerem próximos passos com botão de executar | workflow `proximos_passos` |
| 6 | **Política vira código testado, não RAG** — o documento vira funções com entrada estrita; RAG só para pergunta aberta | `agentic_app/policies/ferias.py`, `tests/test_politica_ferias.py` |
| 7 | **Segurança por workflow** — quem executa (papéis), com qual identidade age, audit log encadeado | `agentic_app/seguranca.py` |
| 8 | **Gatilhos além do clique** — manual, agendado, evento | `agentic_app/gatilhos.py` |
| 9 | **Saída visual** — relatório HTML + PDF em vez de parede de texto | `agentic_app/relatorio.py` |

## O app de referência: Coaching de gestor

Ana é gestora de 12 pessoas (dados fictícios). O painel tem cinco componentes, cada um ligado a um workflow:

| Componente | Workflow | O que faz |
|---|---|---|
| Painel de engajamento | (leitura direta) | metas, engajamento e dias desde o último 1:1, sem LLM |
| Follow-up de metas | `followup_metas` | rascunho de e-mail para quem não bateu a meta; Ana edita e aprova |
| Próximos passos | `proximos_passos` | agente de fundo (segunda 08:00) sugere com quem falar; executar gera rascunho para revisão |
| Assistente de RH | `assistente_rh` | classifica a pergunta, carrega só a política certa, dá ao agente só as ferramentas dela |
| Relatório | `relatorio_equipe` | HTML + PDF da equipe |

Um quinto workflow, `convite_1a1`, é chamado pelas sugestões do agente de fundo.

## Mapa do repositório

| Caminho | O que é |
|---|---|
| `agentic_app/workflow.py` | motor: carrega a spec JSON, executa os nós, valida, audita |
| `agentic_app/llm.py` | `FakeLLM` (padrão) e `OllamaLLM` (opcional, local) |
| `agentic_app/esquema.py` | validador de JSON da saída (subconjunto de JSON Schema) |
| `agentic_app/acoes.py` | fila de aprovação e caixa de saída simulada |
| `agentic_app/seguranca.py` | usuários, papéis, identidades com escopo, audit log com hash |
| `agentic_app/gatilhos.py` | manual, agendado, evento |
| `agentic_app/policies/` | políticas codificadas (manual fictício de RH) |
| `agentic_app/apps/coaching/` | app de referência: dados, workflows JSON, funções |
| `templates/` | canvas, modelo de workflow, modelo de política + teste, matriz de permissões |
| `docs/PASSO-A-PASSO.md` | do zero à implantação numa empresa (10 passos + checklist) |
| `docs/ARQUITETURA.md` | como as peças se encaixam |
| `tests/` | `run.sh` (47 checks sem rede) e `prova_mutacao.sh` |

## Onde ele se encaixa

O agentic-app é a camada **app + workflows de negócio**. Ele não substitui os outros dois kits INEMA, se apoia neles:

- **[agentic-starter](https://github.com/inematds/agentic-starter)** ([guia](https://inematds.github.io/agentic-starter/guia/)) — o agente da empresa em arquivos: identidade, skills, regras e medição. Responde "**quem** é o agente e como ele trabalha aqui".
- **[inema-agent-runtime](https://github.com/inematds/inema-agent-runtime)** ([guia](https://inematds.github.io/inema-agent-runtime/guia/)) — como os agentes descobrem, conectam e usam as ferramentas que você já tem. Responde "**por onde** o agente chega nas ferramentas".
- **agentic-app** (este) — a aplicação que a pessoa de negócio usa: tela, workflow fixo, política em código, aprovação e auditoria. Responde "**que resultado** a empresa ganha e como isso roda todo dia".

## Licença

MIT. Dados, pessoas e manual de RH do exemplo são fictícios.

INEMA.CLUB · https://inema.club
