# Moving the public API to Cloud Run

The problem this solves: a Render free instance sleeps after fifteen minutes,
and waking it on a tenth of a CPU took between fifty seconds and eight minutes.
For that whole time a visitor sees a page that will not load — not a server
starting, just a project that appears broken.

Cloud Run also scales to zero, so it stays free. The difference is what waking
costs: pulling an 85 MB image and starting a process, which is seconds.

Free allowance is 2 million requests, 180,000 vCPU-seconds and 360,000
GB-seconds a month. This demo serves a few hundred requests. There is no
realistic path to a bill, and `--max-instances=3` caps it anyway.

---

## Once, to set up

**1. A Google Cloud account.** [console.cloud.google.com](https://console.cloud.google.com)
— sign in, create a project, and note its ID.

Billing has to be enabled and a card attached even to use the free tier. **The
card is for identity, not payment**: the always-free allowance is not a trial
that expires into charges, and nothing here approaches its limits. If you would
rather not attach a card at all, the GitHub Actions ping in
`.github/workflows/keep-awake.yml` keeps the Render deployment usable and costs
nothing.

**2. Install the CLI.** [cloud.google.com/sdk/docs/install](https://cloud.google.com/sdk/docs/install)

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
```

**3. Turn on the three services this needs.**

```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
```

**4. Make somewhere for the image to live.**

```bash
gcloud artifacts repositories create astra --repository-format=docker --location=asia-south1
```

`asia-south1` is Mumbai. The round trip is the one latency worth choosing, and
the audience is in India.

---

## Deploy

From the repository root:

```bash
gcloud builds submit --config cloudbuild.yaml --substitutions=_SECRET_KEY=$(openssl rand -hex 32)
```

Cloud Build does the building, so Docker does not need to be installed locally.
About three minutes the first time, under two after that.

It prints a URL ending in `.run.app`. Check it:

```bash
curl https://YOUR-SERVICE-URL/health
```

Expect `{"status":"ok", ..., "scanning": false, "writes": false}` — both false
are correct. The public deployment is a browse-only showcase and declines
decisions by construction.

---

## Point the frontend at it

Two edits, then push:

**`apps/web/.env.production`** — replace the Render hostname with the
`.run.app` one. It is inlined at build time, so this needs a redeploy rather
than a restart.

**CORS** — the service has to allow the Vercel origin. Redeploy with your
frontend hostname:

```bash
gcloud builds submit --config cloudbuild.yaml \
  --substitutions=_SECRET_KEY=$(openssl rand -hex 32),_CORS_REGEX='^https://astra-sih26034\.vercel\.app$'
```

Confirm it before trusting it — a CORS mistake shows up as an empty dashboard
with an error only in the browser console:

```bash
curl -s -D - -o /dev/null -H "Origin: https://astra-sih26034.vercel.app" \
  https://YOUR-SERVICE-URL/health | grep -i access-control-allow-origin
```

---

## Afterwards

Delete the Render service, or leave it — it costs nothing either way. Once
Cloud Run is live, `.github/workflows/keep-awake.yml` is pinging a service
nothing points at, so delete that file too.

Keep an eye on the first month's billing page. Not because this will cost
anything, but because "it is free" is a claim worth checking once against the
actual number rather than trusting a document.
