# Trans-EnV Demo (GitHub Pages + ngrok)

Interactive demo of [Trans-EnV](https://github.com/jiyounglee-0523/TransEnV)
([paper](https://arxiv.org/abs/2505.20875), NeurIPS 2025 Datasets and Benchmarks Track):
transform Standard American English into one of 18 English dialects or ESL
learner English by running the guideline pipeline rule by rule with your own
OpenAI / Gemini / Anthropic API key.

The demo is split in two parts:

| Part | Where it runs | Folder |
| --- | --- | --- |
| Web UI (static HTML + JS) | GitHub Pages | `docs/` |
| Pipeline API (FastAPI) | backend server, reached through a proxy + ngrok | `backend/` |

```
GitHub Pages (docs/) ──> ngrok url ──> proxy.py (frontend host :10078) ──> ssh tunnel :10077 ══> backend main.py (:10078)
```

The **Examples gallery** tab (pre-transformed GSM8K questions) is fully static
and works without a backend.

## 1. Run the backend

On the backend host (inside the GPU image, or any Python env with
`docker/requirements.txt`):

```bash
# docker-compose (runs ./run_backend.sh 0.0.0.0 10078 --foreground)
cd docker && docker build -t jylee_transenv . && cd ..
docker compose -f docker/docker-compose-backend.yml up -d

# or manually (background, logs in logs/backend.out)
./run_backend.sh 0.0.0.0 10078
```

Environment variables: `CORS_ORIGINS` (comma-separated, default `*`).

## 2. Run the proxy and ngrok

On the frontend host the proxy forwards ngrok traffic through an ssh tunnel to
the backend and streams the NDJSON responses back unbuffered.

```bash
# docker-compose (runs edlab_frontend_server.sh: autossh tunnel + proxy in the foreground)
cd docker && docker build -f Dockerfile.frontend -t jylee_transenv_frontend_proxy_img . && cd ..
docker compose -f docker/docker-compose-frontend.yml up -d

# or manually
./run_proxy_server.sh 0.0.0.0 10078 http://127.0.0.1:10077

# expose the proxy port with ngrok (logs in logs/ngrok.out)
./run_ngrok.sh 10078 <ngrok_config.yml>
```

The UI sends the `ngrok-skip-browser-warning` header, so visitors never see
ngrok's interstitial page.

## 3. Publish the UI on GitHub Pages

1. Push this repository to GitHub.
2. Settings → Pages → Build and deployment → Source: **Deploy from a branch**,
   Branch: `main`, Folder: **`/docs`**.
3. Open `https://<user>.github.io/<repo>/`.

The page finds the backend in this order:

1. `?api=https://xxxx.ngrok-free.dev` in the page URL.
2. `window.TRANSENV_API_BASE`, if set before the script runs.
3. The default in `API_BASE` at the top of the script in `docs/index.html`.
   Set it to your ngrok domain; update it whenever the ngrok URL changes.

While the backend is unreachable the Live transform tab shows a notice and the
examples gallery keeps working.

## API

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/health` | liveness check |
| GET | `/api/meta` | dialects (with rule counts), L1 languages, CEFR levels, providers, example sentences |
| POST | `/api/transform` | NDJSON stream: `start` → one `rule` event per guideline (`applied` / `nochange` / `rejected` / `error`) → `done` or `error` |

`POST /api/transform` body:

```json
{
  "text": "Janet's ducks lay 16 eggs per day.",
  "variety_type": "dialect",          // or "esl"
  "dialect": "Scottish English",
  "l1": "Japanese",                   // esl only
  "cefr": "A (beginner)",             // esl only: "A (beginner)" | "B (intermediate)" | "None (L1 errors only)"
  "provider": "OpenAI",               // "OpenAI" | "Google Gemini" | "Anthropic Claude"
  "model": "gpt-4o-mini",
  "api_key": "sk-...",
  "shuffle_rules": true,
  "use_judge": true
}
```

API keys are forwarded to the chosen provider for that request only and are
never stored or logged.

## Layout

```
├── docs/
│   ├── index.html             # GitHub Pages UI
│   └── gallery_examples.json  # static examples gallery data
├── backend/
│   ├── main.py                # FastAPI backend + pipeline (port of TransEnV/demo)
│   ├── proxy.py               # aiohttp reverse proxy (ngrok -> ssh tunnel -> backend)
│   ├── assets/                # guidelines, eWAVE features, CEFR feature lists
│   └── src/                   # registry (prompts, L1 error lists) and guideline utils
├── docker/                    # backend (GPU) and frontend proxy images + compose files
├── run_backend.sh             # uvicorn main:app [--foreground]
├── run_proxy_server.sh        # proxy.py [--foreground]
├── run_ngrok.sh               # ngrok http <port> --config <file>
└── edlab_frontend_server.sh   # autossh tunnel + proxy (frontend container entrypoint)
```

## Citation

```bibtex
@article{lee2026trans,
  title={Trans-env: A framework for evaluating the linguistic robustness of llms against english varieties},
  author={Lee, Jiyoung and Kim, Seungho and Han, Jieun and Lee, Jun-Min and Kim, Kitaek and Oh, Alice and Choi, Edward},
  journal={Advances in Neural Information Processing Systems},
  volume={38},
  year={2026}
}
```

MIT License.
