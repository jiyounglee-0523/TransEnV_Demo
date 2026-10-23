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
| Pipeline API (FastAPI) | your machine, exposed with ngrok | `server/` |

The page on GitHub Pages talks to the API through the ngrok tunnel URL. The
**Examples gallery** tab (pre-transformed GSM8K questions) is fully static and
works without a backend.

## 1. Run the backend

```bash
python -m venv .venv
.venv/bin/pip install -r server/requirements.txt
.venv/bin/python server/app.py            # http://localhost:8000
```

`http://localhost:8000/` serves the same UI as GitHub Pages, so you can test
everything locally before publishing.

## 2. Expose it with ngrok

Sign up at https://ngrok.com, get an authtoken, then either

```bash
# a) pyngrok (no CLI install needed)
export NGROK_AUTHTOKEN=<your token>
.venv/bin/python server/app.py --ngrok
```

or

```bash
# b) ngrok CLI
ngrok config add-authtoken <your token>
server/run.sh
```

Both print a public URL such as `https://xxxx.ngrok-free.app`. Options:

- `--ngrok-domain my-demo.ngrok-free.app` (or `NGROK_DOMAIN=...`): use a
  reserved domain so the URL stays the same across restarts. Free ngrok
  accounts get one static domain.
- `--pages-url https://<user>.github.io/<repo>/` (or `PAGES_URL=...`): print a
  ready-to-share link that pre-fills the backend URL.

The UI sends the `ngrok-skip-browser-warning` header, so visitors never see
ngrok's interstitial page.

## 3. Publish the UI on GitHub Pages

1. Push this repository to GitHub.
2. Settings → Pages → Build and deployment → Source: **Deploy from a branch**,
   Branch: `main`, Folder: **`/docs`**.
3. Open `https://<user>.github.io/<repo>/`.

Visitors enter the ngrok URL in the **Backend URL** box (it is remembered in
the browser), or you share a link that fills it in:

```
https://<user>.github.io/<repo>/?api=https://xxxx.ngrok-free.app
```

If you have a reserved ngrok domain, set `DEFAULT_API_URL` at the top of the
script in `docs/index.html` so the page connects automatically.

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
└── server/
    ├── app.py                 # FastAPI backend + pipeline (port of TransEnV/demo)
    ├── run.sh                 # start server + ngrok CLI
    ├── requirements.txt
    ├── assets/                # guidelines, eWAVE features, CEFR feature lists
    └── src/                   # registry (prompts, L1 error lists) and guideline utils
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
