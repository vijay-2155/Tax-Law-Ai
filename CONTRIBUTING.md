# Contributing to TaxIQ

Thank you for your interest in contributing! TaxIQ is a RAG-powered AI tool for Indian Income Tax professionals. All contributions — bug fixes, new features, docs, and tests — are welcome.

---

## Table of Contents

- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [Running Tests](#running-tests)
- [Submitting Changes](#submitting-changes)
- [Adding an LLM Provider](#adding-an-llm-provider)
- [Re-indexing PDFs](#re-indexing-pdfs)

---

## Getting Started

### Prerequisites

| Tool | Version | Required for |
|------|---------|--------------|
| Python | 3.11+ | Backend |
| Node.js | 18+ | Frontend |
| Docker | Latest | Easiest setup (local Qdrant) |
| Ollama | Latest | Local LLM (optional) |

---

## Development Setup

### Option A: Docker (recommended)

```bash
git clone https://github.com/vijay-2155/Tax-Law-Ai.git
cd Tax-Law-Ai
cp .env.example .env        # edit LLM settings if needed
docker compose up
```

App available at http://localhost:8000. API docs at http://localhost:8000/docs.

### Option B: Manual (backend + Vite HMR)

```bash
git clone https://github.com/vijay-2155/Tax-Law-Ai.git
cd Tax-Law-Ai

# Python env
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Configure
cp .env.example .env         # edit as needed

# Load vectors into local Qdrant (requires Docker for Qdrant)
docker run -d -p 6333:6333 qdrant/qdrant
python scripts/load_to_qdrant.py

# Start backend + frontend dev servers
./run.sh
```

Frontend: http://localhost:5173 | API: http://localhost:8000/docs

---

## Project Structure

```
backend/
  api/           FastAPI route handlers
  indexing/      Qdrant client, embedder
  rag/           LangGraph pipeline, retriever, LLM providers
  parsing/       PDF parsing + chunking pipeline
  enrichment/    Metadata enrichment
  config.py      Central config (reads .env)
  main.py        FastAPI app entry point

frontend/src/
  pages/         Chat, Section Browser, Comparison pages
  components/    Reusable UI components
  lib/           API client, utils

scripts/
  load_to_qdrant.py     Fast pre-computed data loader (run once)
  embed_and_upload.py   Re-embed + upload (if you change the embedding model)
  extract_and_index.py  Full pipeline: PDF → chunks → vectors → Qdrant
```

---

## Running Tests

```bash
# All tests
pytest tests/ -v

# Specific test file
pytest tests/test_retriever.py -v

# Frontend lint
cd frontend && npm run lint
```

---

## Submitting Changes

1. **Fork** the repo and create a branch: `git checkout -b feat/your-feature`
2. **Write code** following existing patterns
3. **Add tests** for new functionality where possible
4. **Run the test suite** — make sure nothing breaks
5. **Open a PR** against `main` — fill in the PR template

### Commit style

```
feat: add Groq provider support
fix: handle empty Qdrant collection gracefully
docs: update Docker setup instructions
chore: bump sentence-transformers to 3.1
```

---

## Adding an LLM Provider

1. Open `backend/rag/llm_provider.py`
2. Add a new class implementing `chat()` and `chat_stream()` methods
3. Register it in the `get_provider()` dispatch dict
4. Add the API key env-var to `backend/main.py` lifespan and `.env.example`
5. Add it to the Settings UI in `frontend/src/pages/SettingsPage.tsx`

---

## Re-indexing PDFs

If you want to index new or updated PDFs:

```bash
# 1. Place PDFs in pdfs/
#    pdfs/income_tax_act_1961.pdf
#    pdfs/income_tax_code_2025.pdf

# 2. Full pipeline: parse → chunk → embed → upload
python scripts/extract_and_index.py

# 3. Or if you only changed the Qdrant upload (chunks already exist):
python scripts/embed_and_upload.py

# 4. Or just reload pre-computed vectors into a fresh Qdrant:
python scripts/load_to_qdrant.py --force
```

---

## Questions?

Open a [GitHub Discussion](https://github.com/vijay-2155/Tax-Law-Ai/discussions) or file an [Issue](https://github.com/vijay-2155/Tax-Law-Ai/issues).
