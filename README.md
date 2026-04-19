# LangChat — SQL Agent com IA

Converse com qualquer banco de dados em linguagem natural. Faça perguntas por texto ou voz e receba respostas com insights de negócio, narradas em voz natural.

## Funcionalidades

- Consulta SQL gerada automaticamente a partir de linguagem natural
- Suporte a SQLite, PostgreSQL, MySQL e SQL Server
- Cache semântico — perguntas similares respondem instantaneamente
- Narração das respostas via ElevenLabs
- Entrada por voz (microfone no browser)
- Banco demo populado com 2 anos de dados para testes

## Pré-requisitos

- Python 3.11+
- Chave da API Anthropic (Claude) — obrigatória
- Chave da API ElevenLabs — opcional (narração de voz)

## Instalação

```bash
# 1. Clone o repositório
git clone <url-do-repo>
cd lang_chat

# 2. Crie e ative o ambiente virtual
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Instale as dependências
pip install -r requirements.txt

# 4. Configure as variáveis de ambiente
cp .env.example .env
# Edite .env e preencha suas chaves de API

# 5. Inicie o servidor
uvicorn app.main:app --reload --port 8000
```

Acesse `http://localhost:8000`

## Configuração

Edite o arquivo `.env` (criado a partir de `.env.example`):

| Variável | Descrição | Obrigatória |
|---|---|---|
| `ANTHROPIC_API_KEY` | Chave da API Claude (console.anthropic.com) | ✅ Sim |
| `ELEVENLABS_API_KEY` | Chave para narração de voz (elevenlabs.io) | Não |
| `DATABASE_URL` | URL do banco de dados (padrão: SQLite local) | Não |

## Conectando seu próprio banco

Na interface, cole a URL de conexão no campo **Database URL**:

```
# PostgreSQL
postgresql://user:senha@host:5432/banco

# MySQL
mysql+pymysql://user:senha@host:3306/banco

# SQLite local
sqlite:///caminho/para/banco.db
```

## Stack

- **Backend**: FastAPI + LangChain + Claude (Anthropic)
- **Cache**: ChromaDB (semântico, sem necessidade de Ollama)
- **Frontend**: Vanilla JS + Web Speech API
- **Voz**: ElevenLabs (`eleven_multilingual_v2`)
- **Banco demo**: SQLite gerado com Faker (60 clientes, 20 produtos, ~2100 pedidos)

---

## Roadmap — SquadChat

> Evolução planejada do LangChat para um orquestrador visual de agentes de IA.

### Visão

Hoje o LangChat tem um único agente SQL. A próxima versão — **SquadChat** — permitirá conversar com múltiplos agentes especializados através de uma interface visual, com cada agente visível e ativo em tempo real.

```
┌─────────────────────────────────────────────────────┐
│  Interface Visual (Pixi.js)                          │
│                                                      │
│   [Agente SQL] [Agente Docs] [Agente Web] [...]      │
│        ↑              ↑            ↑                 │
│        └──────────────┴────────────┘                 │
│                   Orquestrador                       │
│                       ↑                              │
│         [ Chat com voz — LangChat ]                  │
└─────────────────────────────────────────────────────┘
```

### O que muda

| LangChat (hoje) | SquadChat (futuro) |
|---|---|
| 1 agente SQL fixo | N agentes especializados dinâmicos |
| Cache semântico simples | VectorDB com memória de longo prazo |
| Sem estado entre perguntas | Contexto persistente por sessão |
| 1 ferramenta (SQL) | SQL + docs + web search + APIs externas |
| Resposta única | Respostas orquestradas entre agentes |
| Interface de chat | Interface visual com agentes animados |

### Stack planejado

- **LangGraph** — orquestração de agentes com estado (substitui `create_sql_agent`)
- **Qdrant ou Pinecone** — VectorDB dedicado para memória de longo prazo
- **Pixi.js** — dashboard visual mostrando agentes "pensando" em tempo real (base: Opensquad)
- **WebSocket bidirecional** — streaming de mensagens entre usuário e agentes
- **MCP (Model Context Protocol)** — padrão para conectar ferramentas externas

### Base para construir

Este projeto será combinado com o [Opensquad](https://github.com/opensquad) — framework de orquestração de squads que já possui o dashboard visual em Pixi.js e definição de agentes em YAML. O LangChat entra com a camada de chat, voz e cache semântico.
