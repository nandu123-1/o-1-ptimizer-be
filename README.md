# O(1)ptimizer

**AI-powered C++ complexity reduction — paste brute-force code, get an optimized rewrite, Big-O comparison, and a Recharts-ready complexity curve in one click.**

- Frontend: Next.js 16 + Monaco editor + Recharts (deployed on Netlify)
- Backend: FastAPI + Gemini (`google-genai`) + optional CrewAI multi-agent pipeline (deployed on Render)
- LLM: Google Gemini (flash family), with automatic key + model failover on 429 / 503
- Live demo: [o1ptimizer.netlify.app](https://o1ptimizer.netlify.app)

---

## What it does

1. You submit C++ source — via paste, `.cpp` upload, or a **photo of handwritten code** (Gemini vision OCRs it).
2. The backend runs it through either:
   - **Single-shot path** (default): one Gemini call that emits a strict JSON `SwarmOptimizationResult`. Fast (~15-25 s) and cheap on free-tier quota.
   - **CrewAI path** (opt-in via `DSA_TUTOR_USE_CREW=1`): four specialist agents — Complexity Analyzer → Algorithm Researcher → Code Optimizer (with live `g++` compile/run loop) → Visualization Expert.
3. Returns: optimized C++, time + space complexity before/after, estimated speed-up, algorithm choices, correctness notes, compile attempts, and a line-chart payload for input-size vs operation count.

## Architecture

```
Browser (Next.js)
    └── direct fetch → Render (FastAPI)
                           ├── /v1/optimize-code          (crew or single-shot)
                           ├── /v1/extract-cpp-from-image (Gemini vision)
                           └── /healthz
```

The frontend calls the backend directly from the browser using `NEXT_PUBLIC_BACKEND_API_BASE_URL`, bypassing Netlify's serverless-function timeout so Render's free-tier cold starts (~30-60 s) don't get cut off.

## Resilience features

- **Key pool**: comma-separated `GEMINI_API_KEYS` rotates on `429 RESOURCE_EXHAUSTED` within a model.
- **Model pool**: when both keys are exhausted for a model, auto-advances through `gemini-flash-latest → gemini-flash-lite-latest → gemini-2.5-flash-lite → gemini-2.5-flash → gemini-3-flash-preview → gemini-3.1-flash-lite-preview`.
- **Transient-error retry**: 503 / UNAVAILABLE / "overloaded" get up to 3 attempts with exponential backoff.
- **Crew fallback**: any crew kickoff failure falls through to the single-shot path so one flaky LLM call doesn't kill the request.
- **Strict validation**: every response is parsed with Pydantic against `SwarmOptimizationResult` before returning.
- **Self-diagnosing frontend**: non-JSON responses surface the HTTP status and a 200-char preview instead of a cryptic parse error.

---

## Local development

### Prerequisites

- Python 3.11 (or `>=3.10,<3.14`)
- Node.js 20+
- A Gemini API key — get one at [aistudio.google.com/apikey](https://aistudio.google.com/apikey)

### Backend

```bash
pip install uv
uv sync
cp .env.example .env
# edit .env and paste your Gemini key(s)
uv run uvicorn dsa_tutor_code_optimizer.api:app --reload --port 8000
```

Health check: http://127.0.0.1:8000/healthz → `{"status":"ok"}`

### Frontend

```bash
cd frontend
npm install        # postinstall copies Monaco into public/monaco-vs
npm run dev
```

Open http://127.0.0.1:3000 and hit Optimize.

## Environment variables

Copy `.env.example` to `.env` and fill in:

| Key | Purpose |
|---|---|
| `GEMINI_API_KEY` | Active Gemini key (required). |
| `GEMINI_API_KEYS` | Comma-separated key pool for failover (optional). |
| `DSA_TUTOR_GEMINI_MODEL` | Override the starting model (optional, default: `gemini/gemini-flash-latest`). |
| `DSA_TUTOR_USE_CREW` | Set to `1` to make CrewAI the primary path. |
| `DSA_TUTOR_CORS_ORIGINS` | Comma-separated allowed origins. Default: `localhost:3000`, `127.0.0.1:3000`. In production, set to your Netlify URL. |
| `DSA_TUTOR_API_PORT` | Port for the dev server. |
| `DSA_TUTOR_LOG_LEVEL` | Defaults to `INFO`. |
| `SERPER_API_KEY` | Optional — only used by the CrewAI web-research agent. |

Frontend (inlined at build time by Next.js):

| Key | Purpose |
|---|---|
| `NEXT_PUBLIC_BACKEND_API_BASE_URL` | Full URL of the deployed FastAPI backend (e.g. `https://o-1-ptimizer-be.onrender.com`). Leave unset to use the Netlify `/api/*` proxy. |

---

## Deploying

### Backend → Render

- **Build Command**: `pip install uv && uv sync`
- **Start Command**: `uvicorn dsa_tutor_code_optimizer.api:app --host 0.0.0.0 --port $PORT`
- **Env vars**: `GEMINI_API_KEY`, `GEMINI_API_KEYS`, `DSA_TUTOR_CORS_ORIGINS=https://<your-netlify-site>`, `PYTHONUNBUFFERED=1`

Note: free tier sleeps after 15 min idle; first request after sleep takes ~30-60 s to wake.

### Frontend → Netlify

- **Base directory**: repo root (if using the `o-1-ptimizer-fe` split repo) or `frontend/` (if deploying from the monorepo)
- **Build Command**: `npm ci && npm run build`
- **Publish directory**: `.next`
- **Env vars**: `NEXT_PUBLIC_BACKEND_API_BASE_URL` (scope: **Builds**), `NODE_VERSION=20`
- Requires the `@netlify/plugin-nextjs` plugin (auto-detected on Next.js projects).

---

## Project layout

```
.
├── src/dsa_tutor_code_optimizer/
│   ├── api.py              # FastAPI endpoints + key/model failover + single-shot path
│   ├── crew.py             # CrewAI swarm (four agents)
│   ├── schemas.py          # Pydantic contracts returned to the frontend
│   ├── tools/custom_tool.py  # g++ compiler tool, complexity-curve generator
│   ├── config/agents.yaml  # Agent role / goal / backstory definitions
│   ├── config/tasks.yaml   # Task descriptions, expected_output, context chaining
│   └── main.py             # CLI entry points (run / train / replay / test)
└── frontend/
    ├── src/components/OptimizerWorkbench.tsx  # UI: editor, file/image upload, results
    └── src/app/api/                           # Server-route proxies (fallback path)
```

## CLI entry points (backend)

```bash
uv run dsa_tutor_code_optimizer      # run the crew once with the bundled Two Sum sample
uv run run_api                       # start FastAPI dev server
```

---

## License

MIT — see [LICENSE](LICENSE) if present, otherwise this project is open to use and modification.

## Acknowledgements

- [CrewAI](https://crewai.com) — multi-agent framework.
- [Google Gemini](https://ai.google.dev) — LLM backbone.
- [Monaco Editor](https://microsoft.github.io/monaco-editor/) — in-browser C++ editor.
- [Recharts](https://recharts.org) — complexity curve visualization.
