# Deploying SessionIQ

SessionIQ ships as a **single container** that serves the dashboard, the API and uploaded files from
one origin. There is no separate web server to configure and no cross-origin setup to get wrong.

The image also contains a pre-generated demo library. Audio analysis is the expensive part of this
app and librosa is imported lazily, so generating the demo content at build time means a container
serves a populated dashboard within seconds of starting rather than analyzing files on first
request.

## Try it locally first

```bash
docker build -t sessioniq .
docker run --rm -p 8080:8000 sessioniq
```

Open <http://localhost:8080>. The demo library, the assistant, search and the player all work with
no configuration and no API keys.

## Deploy to Render

[Render](https://render.com) is the only major host still offering an ongoing free tier, and this
repository carries a blueprint for it.

1. Create a Render account and connect your GitHub.
2. **New → Blueprint**, pick this repository, and apply. `render.yaml` configures the rest.
3. Render builds the image and gives you a `https://<name>.onrender.com` URL.

To do it without the blueprint: **New → Web Service**, pick the repository, set the runtime to
**Docker**, and set the health check path to `/api/health`. The `Dockerfile` is detected
automatically.

## What to know before you host it

**A free instance sleeps after 15 minutes idle**, and the next request takes 30–60 seconds to wake
it. That is the host's cold start, not the app's — the app itself is ready in about four seconds.
If you are sending this link to someone, open it yourself first so it is warm.

**There is no authentication.** SessionIQ is designed as a single-user local app: `main` reads and
writes one library, and nothing separates one visitor from another. Anyone with the URL can read,
upload, and delete. Do not put anything private on a public instance.

**Free tiers have no persistent disk.** Uploads and edits live in the container and disappear when
it restarts; the baked-in demo library is what you get back. That is usually what you want for a
demo — it always resets to a clean, populated state.

**The image is large** (roughly a gigabyte, mostly librosa, scipy, numba and their friends), so the
first build takes several minutes and cold pulls are not instant. This is inherent to doing real
audio analysis rather than a symptom of anything misconfigured.

**Uploads are the expensive path on a small instance.** Analysis runs at 22.05 kHz mono to keep it
light, but a free tier has a fraction of a CPU, so a visitor uploading several files will wait.
Browsing, searching and asking questions stay responsive — none of them load librosa.

## Other hosts

The image is a plain Docker image with a health endpoint, so anything that runs containers will take
it. Worth knowing about the others:

- **Google Cloud Run** — scale-to-zero with a generous free request allowance, and a better fit than
  Render if you want it to stay genuinely free under load. More setup: a Google Cloud project and
  the `gcloud` CLI.
- **Railway** — the best developer experience of the group and it supports volumes, but the free
  tier became a one-time trial credit, so it means paying.
- **Fly.io** — cheap for a small always-on machine with a volume, but no meaningful free tier for
  new accounts.

Set `SESSIONIQ_SEED_DEMO=1` on any host where you attach a persistent volume, so the demo content is
generated the first time the volume is empty. Leave it unset otherwise; the baked library is already
there.

## Configuration

| variable | default | what it does |
| --- | --- | --- |
| `SESSIONIQ_HOST` | `127.0.0.1` (`0.0.0.0` in the image) | bind address |
| `SESSIONIQ_PORT` | `8000` | bind port; `PORT` is used when this is unset |
| `SESSIONIQ_STATIC_DIR` | `/app/web/dist` in the image | built dashboard to serve |
| `SESSIONIQ_UPLOAD_ROOT` | `.sessioniq-data/uploads` | where the library lives |
| `SESSIONIQ_CORS_ORIGINS` | the two Vite dev origins | comma-separated extra origins |
| `SESSIONIQ_SEED_DEMO` | unset | generate demo content when the library is empty |
| `SESSIONIQ_DISABLE_VECTOR` | unset | force lexical retrieval, skipping the embedding model |
| `SESSIONIQ_LUFS_TARGET` | `-14` | loudness target for the delivery check |
| `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `SESSIONIQ_MODEL` | unset | see `.env.example` |

Without a model configured the assistant answers from the deterministic offline engine, which is
what the hosted demo does. Pointing `OPENAI_BASE_URL` at a local Ollama works the same way it does
locally, but a hosted instance cannot reach a model on your machine.

## Bringing your own audio

The hosted demo only knows the generated library. To run it against real files, run SessionIQ
locally — either with the local toolchain or with a volume attached:

```bash
docker build -t sessioniq .
docker run --rm -p 8080:8000 -v sessioniq-data:/app/.sessioniq-data -e SESSIONIQ_SEED_DEMO=1 sessioniq
```

The first boot on an empty volume regenerates the demo content, which takes about a minute because
it runs the analyzers for real. After that the volume keeps whatever you upload.
