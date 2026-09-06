#!/usr/bin/env bash
# One command to put the public API on Cloud Run.
#
#   bash scripts/deploy-cloudrun.sh
#
# Does the whole sequence -- enable the services, create the image repository,
# generate a signing key, build and deploy -- and checks the result. Safe to run
# again: every step is idempotent, so a failure halfway through is fixed by
# running it once more rather than by unpicking what it did.
#
# The only prerequisites are gcloud installed and `gcloud auth login` done.
# Docker is not needed; Cloud Build does the building.

set -euo pipefail

SERVICE="astra-api"
REGION="asia-south1"   # Mumbai
REPO="astra"

bold() { printf "\n\033[1m%s\033[0m\n" "$1"; }
ok()   { printf "  \033[32mOK\033[0m   %s\n" "$1"; }
die()  { printf "  \033[31mSTOP\033[0m %s\n" "$1" >&2; exit 1; }

# -- prerequisites -----------------------------------------------------------

bold "Checking prerequisites"

command -v gcloud >/dev/null 2>&1 \
  || die "gcloud is not installed. https://cloud.google.com/sdk/docs/install"
ok "gcloud installed"

ACCOUNT=$(gcloud config get-value account 2>/dev/null || true)
[ -n "$ACCOUNT" ] && [ "$ACCOUNT" != "(unset)" ] \
  || die "Not signed in. Run: gcloud auth login"
ok "signed in as $ACCOUNT"

PROJECT=$(gcloud config get-value project 2>/dev/null || true)
[ -n "$PROJECT" ] && [ "$PROJECT" != "(unset)" ] \
  || die "No project set. Run: gcloud config set project YOUR_PROJECT_ID"
ok "project $PROJECT"

# A new project is not linked to a billing account on creation, and Cloud Run
# will not run anything without one. Unchecked, that arrives several steps
# later as a permission error that never mentions billing.
BILLING=$(gcloud billing projects describe "$PROJECT" \
  --format="value(billingEnabled)" 2>/dev/null || echo unknown)
case "$BILLING" in
  True)
    ok "billing linked" ;;
  False)
    die "Billing is not linked to $PROJECT.

       Link it here:
       https://console.cloud.google.com/billing/linkedaccount?project=$PROJECT

       Nothing here costs money -- Cloud Run's free allowance covers this many
       times over -- but Google will not run anything at all until a billing
       account is attached." ;;
  *)
    printf "  \033[33mWARN\033[0m could not confirm billing; continuing anyway\n" ;;
esac

[ -f cloudbuild.yaml ] \
  || die "Run this from the repository root; cloudbuild.yaml is not here."
[ -f data/demo/astra.db ] \
  || die "The demo bundle is missing. Run: make demo-bundle"
ok "demo bundle present ($(ls data/demo/uploads | wc -l) evidence images)"

# -- one-time setup, safe to repeat ------------------------------------------

bold "Enabling services (a minute the first time, instant after)"
gcloud services enable \
  run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  --quiet
ok "run, cloudbuild, artifactregistry enabled"

bold "Making sure the image repository exists"
if gcloud artifacts repositories describe "$REPO" --location="$REGION" >/dev/null 2>&1; then
  ok "$REPO already exists in $REGION"
else
  gcloud artifacts repositories create "$REPO" \
    --repository-format=docker --location="$REGION" \
    --description="ASTRA container images" --quiet
  ok "created $REPO in $REGION"
fi

# -- the signing key ---------------------------------------------------------
#
# Reused across deployments if one is already set, because rotating it would
# invalidate the signature on every notice signed before now.

bold "Signing key"
EXISTING=$(gcloud run services describe "$SERVICE" --region="$REGION" \
  --format="value(spec.template.spec.containers[0].env.filter(\"name:ASTRA_SECRET_KEY\").extract(\"value\"))" \
  2>/dev/null || true)

if [ -n "${EXISTING:-}" ] && [ "$EXISTING" != "change-me-in-production" ]; then
  SECRET="$EXISTING"
  ok "reusing the existing key (rotating it would invalidate signed notices)"
else
  SECRET=$(python -c "import secrets; print(secrets.token_hex(32))")
  ok "generated a new key"
fi

# -- build and deploy --------------------------------------------------------

bold "Building and deploying (about three minutes the first time)"
gcloud builds submit --config cloudbuild.yaml \
  --substitutions="_SECRET_KEY=${SECRET}" \
  .

URL=$(gcloud run services describe "$SERVICE" --region="$REGION" --format="value(status.url)")

# -- check it actually works -------------------------------------------------

bold "Checking the deployment"
HEALTH=$(curl -fsS -m 60 "$URL/health") || die "The service did not answer at $URL/health"
echo "  $HEALTH"

echo "$HEALTH" | grep -q '"writes":false' \
  && ok "read-only, as a public showcase should be" \
  || printf "  \033[33mWARN\033[0m writes are enabled on a public deployment\n"

printf "\n  Cold start check (this is the whole point of moving here):\n"
curl -s -o /dev/null -w "    warm request: %{time_total}s\n" "$URL/health"

bold "Done"
cat <<EOF
  API:  $URL

  Next, point the frontend at it:

    1. Edit apps/web/.env.production
         NEXT_PUBLIC_API_BASE_URL=$URL
    2. Commit and push. Vercel redeploys itself.
    3. Re-run this script with your frontend hostname so CORS allows it:

       gcloud builds submit --config cloudbuild.yaml \
         --substitutions=_SECRET_KEY=$SECRET,_CORS_REGEX='^https://astra-sih26034\.vercel\.app\$'

  Once this is live, delete .github/workflows/keep-awake.yml -- it would be
  pinging a service nothing points at any more.
EOF
