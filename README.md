<div align="center">

<img src="docs/icon.png" width="120" alt="TaxIQ App Icon" />

![TaxIQ Banner](docs/banner.png)

# TaxIQ — Indian Income Tax AI Assistant

**A RAG-powered, agentic AI tool for Chartered Accountants and tax professionals to query, compare, and understand the Indian Income Tax Act — both the legacy 1961 Act and the new 2025 Code.**

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18%2B-61DAFB?style=for-the-badge&logo=react&logoColor=black)](https://react.dev)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2%2B-FF6B35?style=for-the-badge)](https://langchain-ai.github.io/langgraph/)
[![Qdrant](https://img.shields.io/badge/Qdrant-Docker-DC143C?style=for-the-badge)](https://qdrant.tech)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://docs.docker.com/compose/)
[![CI](https://github.com/vijay-2155/Tax-Law-Ai/actions/workflows/ci.yml/badge.svg)](https://github.com/vijay-2155/Tax-Law-Ai/actions)
[![License](https://img.shields.io/badge/License-MIT-gold?style=for-the-badge)](LICENSE)

</div>

---

## 🔍 What is TaxIQ?

TaxIQ is a **production-grade, agentic Retrieval-Augmented Generation (RAG) application** purpose-built for Indian tax professionals. It ingests the full text of both the **Income Tax Act 1961** and the **Income Tax Code 2025**, stores them in a vector database, and exposes a chat interface backed by any major LLM.

### Key Capabilities

| Feature | Description |
|---|---|
| 💬 **Conversational AI** | Ask tax questions in plain English and get cited, section-backed answers |
| ⚖️ **Act Comparison** | Side-by-side comparison of equivalent provisions across 1961 Act vs 2025 Code |
| 🔎 **Exact Section Lookup** | Query by section number (e.g. "Section 80C") for instant pinpoint retrieval |
| 🌐 **Live Web Search** | Supplements law text with live CBDT circulars & Income Tax India updates |
| 🧠 **Agentic Pipeline** | LangGraph-powered graph: route → retrieve → grade → (rewrite?) → generate |
| 🔧 **Multi-LLM** | Plug in Ollama, OpenAI, Anthropic, Gemini, Groq, or OpenRouter |
| 📦 **Standalone App** | Ships as a PyInstaller Windows `.exe` — no Python installation needed |

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────┐
│                    React Frontend                     │
│   (Vite + TypeScript — Chat UI, Section Browser,      │
│    Comparison Tables, Settings Panel)                 │
└──────────────┬───────────────────────────────────────┘
               │ HTTP / SSE
┌──────────────▼───────────────────────────────────────┐
│                   FastAPI Backend                     │
│  /api/chat  /api/search  /api/section  /api/settings  │
└──────────────┬───────────────────────────────────────┘
               │
┌──────────────▼───────────────────────────────────────┐
│           LangGraph Agentic RAG Pipeline              │
│                                                       │
│  route_question                                       │
│      │  (exact / semantic / cross_act)                │
│      ▼                                                │
│  retrieve  ──────────► Qdrant Vector DB               │
│      │                 (1961 collection + 2025 collection)
│      ▼                                                │
│  grade_documents  ──── LLM relevance check            │
│      │                                                │
│      �## 🚀 Quick Start

### ⚡ Option A: Docker (Recommended — One Command)

> **Prerequisites:** [Docker Desktop](https://www.docker.com/products/docker-desktop) (no Python, no Node.js needed)

```bash
git clone https://github.com/vijay-2155/Tax-Law-Ai.git
cd Tax-Law-Ai

# Linux / Mac
./start.sh

# Windows
start.bat
```

That's it. The browser opens automatically at **http://localhost:8000**.

On **first run**, TaxIQ auto-loads the Income Tax Acts into the local database (~2 min). After that, starts in ~30 seconds. Configure your LLM in the **Settings** panel (Ollama Cloud sign-in, API key, or local Ollama).

```bash
# Stop
docker compose down

# Full reset (clears all data)
docker compose down -v
```

---

### 🔧 Option B: Manual Setup (for development)

See [CONTRIBUTING.md](CONTRIBUTING.md) for full dev setup instructions.

**Prerequisites:** Python 3.11+, Node.js 18+, Docker (for local Qdrant)

```bash
git clone https://github.com/vijay-2155/Tax-Law-Ai.git
cd Tax-Law-Ai
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # edit your LLM config
docker run -d -p 6333:6333 qdrant/qdrant
python scripts/load_to_qdrant.py
./run.sh
```

---`dotenv
# Required — Qdrant Cloud (https://cloud.qdrant.io)
QDRANT_URL=https://your-cluster.qdrant.io
QDRANT_API_KEY=your_qdrant_api_key

# Embedding model (Ollama — local)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_EMBED_MODEL=qwen3-embedding
OLLAMA_CHAT_MODEL=qwen2.5:7b

# Default LLM provider (can be changed in the Settings UI at runtime)
LLM_PROVIDER=ollama
LLM_MODEL=qwen2.5:7b
```

### 3. Pull Ollama models

```bash
ollama pull qwen3-embedding     # embedding model
ollama pull qwen2.5:7b          # chat model (or any model you prefer)
```

### 4. Index the Income Tax Acts

Place your PDF files in the `pdfs/` directory:
- `pdfs/income_tax_act_1961.pdf`
- `pdfs/income_tax_code_2025.pdf`

Then run the indexing pipeline:

```bash
python -m scripts.index_pdfs
```

> This parses the PDFs, chunks them by section structure, generates embeddings, and uploads them to Qdrant.

### 5. Start the application

```bash
# Dev mode — Vite HMR on :5173, FastAPI on :8000
./run.sh

# Production mode — builds frontend and serves everything from FastAPI on :8000
./run.sh --prod
```

Open **http://localhost:5173** in your browser.

---

## 🤖 Supported LLM Providers

TaxIQ supports hot-swapping providers from the Settings UI without a restart:

| Provider | Models |
|---|---|
| **Ollama** (local) | Any model pulled locally — Qwen, Llama, Mistral, DeepSeek, etc. |
| **Ollama Cloud** | Hosted Ollama models via API key |
| **OpenAI** | GPT-4o, GPT-4o-mini, o1, o3-mini, etc. |
| **Anthropic** | Claude 3.5 Sonnet, Claude 3 Opus, etc. |
| **Google Gemini** | Gemini 1.5 Pro/Flash, Gemini 2.0, etc. |
| **Groq** | Llama 3, Mixtral, Gemma models (ultra-fast inference) |
| **OpenRouter** | Any model via unified API |

---

## 📁 Project Structure

```
taxiq/
├── backend/
│   ├── api/                   # FastAPI route handlers
│   │   ├── routes_chat.py     # Chat (SSE streaming)
│   │   ├── routes_search.py   # Semantic / section search
│   │   ├── routes_section.py  # Full section detail view
│   │   ├── routes_heads.py    # Income heads (Salary, Capital Gains, etc.)
│   │   └── routes_settings.py # Runtime LLM config
│   ├── indexing/
│   │   ├── qdrant_store.py    # Qdrant client wrapper + collection ops
│   │   └── embedder.py        # Ollama embedding calls
│   ├── rag/
│   │   ├── graph.py           # LangGraph agentic pipeline (main brain)
│   │   ├── retriever.py       # Semantic & exact retrieval logic
│   │   ├── prompt_builder.py  # System prompts + context formatting
│   │   ├── llm_provider.py    # Unified multi-provider LLM client
│   │   └── web_search.py      # Live CBDT / Income Tax India web search
│   ├── parsing/               # PDF parsing & chunking pipeline
│   ├── enrichment/            # Metadata enrichment for indexed chunks
│   ├── config.py              # Central config (reads .env)
│   └── main.py                # FastAPI app setup & lifespan
├── frontend/
│   └── src/
│       ├── pages/             # Chat, Section Browser, Comparison pages
│       ├── components/        # UI components (ChatWindow, SourceCard, etc.)
│       └── lib/               # API client, history management, utils
├── scripts/                   # PDF indexing scripts
├── tests/                     # Test suite
├── pdfs/                      # Place your Income Tax Act PDFs here
├── docs/                      # Banner and documentation assets
├── app_entry.py               # PyInstaller entry point (Windows .exe)
├── build.bat                  # One-click Windows build script
├── run.sh                     # Unix dev/prod startup script
├── requirements.txt
└── .env.example
```

---

## 🧠 How the RAG Pipeline Works

Every chat query goes through a **5-node LangGraph state machine**:

```
START
  │
  ▼
route_question   ← Pattern matching (no LLM cost)
  │                "Section 80C" → exact
  │                "compare 1961 vs 2025" → cross_act
  │                everything else → semantic
  │
  ▼
retrieve         ← Vector search / exact section lookup from Qdrant
  │                + optional income-head filter (Salary, PGBP, CG…)
  │
  ▼
grade_documents  ← LLM asks: "Are these chunks relevant?"
  │
  ├─ YES → generate   ← LLM streams answer with cited sections
  │                   ← Web search appended (CBDT circulars, live news)
  │
  └─ NO  → rewrite_query  ← Rephrases using Indian tax law terminology
               │
               └─────────► retrieve  (max 2 retries, then generate anyway)
```

**Chat history condensation** — Multi-turn conversations are kept coherent by a pre-step that rewrites the follow-up question as a fully self-contained query, resolving pronouns ("it", "the section") against previous turns.

---

## 🖥️ Windows Desktop App

TaxIQ can be packaged as a **self-contained Windows executable** using PyInstaller:

```bat
# On Windows — builds taxiq.exe into dist/
build.bat
```

The `.exe`:
- Bundles the FastAPI backend + React frontend in a single file
- Stores user data (crash logs, settings) in `%APPDATA%\TaxIQ`
- Opens a native webview window (pywebview) or falls back to the default browser
- No Python installation required on the target machine

---

## ⚙️ Environment Variables Reference

| Variable | Default | Description |
|---|---|---|
| `QDRANT_URL` | *(required)* | Qdrant Cloud cluster URL |
| `QDRANT_API_KEY` | *(required)* | Qdrant API key |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_EMBED_MODEL` | `qwen3-embedding` | Embedding model name |
| `OLLAMA_CHAT_MODEL` | `qwen2.5:7b` | Default Ollama chat model |
| `LLM_PROVIDER` | `ollama` | Default provider: `ollama`, `openai`, `anthropic`, `gemini`, `groq`, `openrouter` |
| `LLM_MODEL` | `qwen2.5:7b` | Default model |
| `LLM_API_KEY` | *(optional)* | API key for cloud providers |
| `APP_HOST` | `127.0.0.1` | FastAPI bind address |
| `APP_PORT` | `8000` | FastAPI port |

---

## 🛠️ Development

### Run tests

```bash
pytest tests/ -v
```

### API documentation

When the backend is running, open **http://localhost:8000/docs** for the interactive Swagger UI.

### Adding a new LLM provider

1. Add a new class in `backend/rag/llm_provider.py` implementing `chat()` and `chat_stream()`
2. Register it in `get_provider()` dispatch
3. Add the API key env-var to `backend/main.py` lifespan and `.env.example`

---

## 🤝 Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for:
- Dev setup (Docker or manual)
- How to add a new LLM provider
- How to re-index PDFs
- PR and commit guidelines

Please follow our [Code of Conduct](CODE_OF_CONDUCT.md) and report vulnerabilities privately via [SECURITY.md](SECURITY.md).

---

## 🤝 Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for:
- Dev setup (Docker or manual)
- How to add a new LLM provider
- How to re-index PDFs
- PR and commit guidelines

Please follow our [Code of Conduct](CODE_OF_CONDUCT.md) and report vulnerabilities privately per [SECURITY.md](SECURITY.md).

---

## 📄 License

MIT — see [LICENSE](LICENSE) for details.

---

<div align="center">

**Built with ❤️ for Indian tax professionals**

*TaxIQ is not a substitute for professional legal advice. Always consult a qualified CA or tax advisor.*

</div>
