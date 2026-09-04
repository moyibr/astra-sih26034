# Deploying ASTRA

Two services, two hosts, because they want different things:

| | Host | Why |
| --- | --- | --- |
| **Frontend** (Next.js) | Vercel | Built for it, and free. |
| **API** (FastAPI + OCR) | Render | Needs a real container. Its dependencies come to 272 MB, over Vercel's 250 MB serverless limit, and a scan takes seconds rather than milliseconds. |

---

## 1. The API, on Render

Everything is already configured in [`render.yaml`](render.yaml). Render reads
it and needs nothing set by hand.

1. Go to **[render.com](https://render.com)** and **Sign in with GitHub**.
2. **New +** → **Blueprint**.
3. Pick the **`astra-sih26034`** repository.
4. **Apply**.

The first build takes roughly 10–15 minutes. Most of that is installing OpenCV
and ONNX Runtime and then generating the demo dataset, which is baked into the
image so the dashboard has something to show the moment it starts.

When it finishes you get:

```
https://astra-sih26034-api.onrender.com
```

Check it by opening `/health` in a browser. It should answer:

```json
{ "status": "ok", "rulepack": "lmpc-2011@2026.07.01", "rules": 22 }
```

### Two things to know about the free tier

**It sleeps after 15 minutes of inactivity.** The next request wakes it, which
takes 40–60 seconds. Before showing anyone, open `/health` once and wait for it
to answer — then everything is instant.

**It gets 512 MB of memory**, which is enough for the OCR models but not
generously so. If a scan ever fails with the container restarting, that is
memory, and the fix is Render's paid tier or a smaller detection model.

---

## 2. The frontend, on Vercel

1. Go to **[vercel.com/new](https://vercel.com/new)** and **Continue with GitHub**.
2. **Import** the `astra-sih26034` repository.
3. Set **Root Directory** to `apps/web`. This is the only setting that matters —
   the repository is a monorepo and Vercel defaults to the top level, where there
   is no Next.js app.
4. **Deploy**.

The build takes about two minutes. You get `https://astra-sih26034.vercel.app`,
and every later `git push` redeploys it automatically.

It is already built against the Render URL above — `apps/web/.env.production`
carries it — so it starts working the moment the API is awake.

If the API ends up on a different hostname, because the service name was taken,
change it in `apps/web/.env.production`, commit and push. It is inlined at build
time rather than read at run time, so a redeploy is required for it to take
effect.

---

## 3. Running it locally

Still the fastest way to develop, and the way to demo with no network at all.

```bash
make install
make seed
```

Then two terminals:

```bash
make api
```

```bash
make web
```

Open `http://localhost:3000`. **Both must be running** — the frontend on its own
will report that it cannot reach the API, which is exactly what that message
means.

---

## 4. Running it offline, in containers

For a venue where the wifi cannot be relied on. Needs Docker Desktop installed.

```bash
docker compose up --build
```

Brings up Postgres, MinIO, the API and the frontend with no dependency on
anything outside the repository. Worth rehearsing at least once before the
finale, on a machine with its wifi switched off.

---

## What is deliberately not persistent

The hosted demo keeps its database and its evidence images on the container's
own filesystem, and both are rebuilt when the container restarts. That is a
choice, not an oversight: on a tier with no persistent disk, a database that
outlived its images would leave every finding pointing at a photograph that no
longer existed. Keeping them together means the demo is always internally
consistent — scans made during a session sit on top of a known-good baseline,
and it returns to that baseline on restart.

A pilot deployment swaps `DATABASE_URL` for managed Postgres and points the
storage variables at S3. Nothing in the code changes.
