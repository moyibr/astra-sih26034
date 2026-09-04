# The API and the vision pipeline share one image.
#
# They are logically separate services and the compose file runs them as such,
# but they share heavy dependencies -- OpenCV, ONNX Runtime, the OCR models --
# and building that layer twice would double both the build time and the image
# footprint for no benefit at this scale.

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    # ONNX Runtime and OpenCV each spawn a thread pool per core by default,
    # which on a small instance costs far more memory than the parallelism is
    # worth. A scan is a few seconds either way.
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1

# OpenCV needs these even in its headless build.
RUN apt-get update && apt-get install --no-install-recommends -y \
        libglib2.0-0 \
        libgomp1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy only the package manifests first so a source edit does not invalidate
# the dependency layer.
COPY packages/schema/pyproject.toml packages/schema/
COPY packages/rulepacks/pyproject.toml packages/rulepacks/
COPY apps/vision/pyproject.toml apps/vision/
COPY apps/api/pyproject.toml apps/api/

COPY packages/ packages/
COPY apps/vision/ apps/vision/
COPY apps/api/ apps/api/
COPY ml/ ml/
COPY scripts/ scripts/

RUN pip install --upgrade pip \
    && pip install -e packages/schema -e packages/rulepacks -e apps/vision -e apps/api \
    # RapidOCR depends on opencv-python, the desktop build, which is compiled
    # against X11 and drags in libraries a server image has no reason to carry.
    # Both variants install the same `cv2` module into the same directory, so
    # whichever lands second wins -- and when that is the desktop build, every
    # import fails for want of libxcb. Keeping only the headless build is both
    # the fix and 74 MB smaller. Nothing here uses a GUI function.
    && pip uninstall -y opencv-python opencv-python-headless \
    && pip install opencv-python-headless

# Fail the build here, loudly, if OpenCV cannot load.
#
# This check exists because its absence cost a deployment. The model prefetch
# below is allowed to fail, since a download is a network problem rather than a
# broken image -- but that tolerance also swallowed a genuine ImportError and
# let the build continue to a far more confusing failure several steps later.
# A tolerant step must never be the first thing to touch a fragile import.
RUN python -c "import cv2; print('opencv', cv2.__version__)" \
    && python -c "import zxingcpp, numpy; print('vision deps ok')"

# Bake the OCR models into the image. Downloading them on first request would
# mean the container needs the internet to answer its first scan, and the whole
# point of the offline path is that it does not.
RUN python -c "from rapidocr import RapidOCR; RapidOCR()" || \
    echo "model prefetch skipped; they will download on first use"

# Bake a demo dataset in at build time rather than seeding on boot.
#
# Seeding takes a couple of minutes, which a platform health check will not wait
# for, and a hosting tier with an ephemeral filesystem would make the container
# redo it on every wake. Building it into the image means the dashboard has
# something to show the instant it starts, and that scans a visitor creates
# during a session sit on top of a known-good baseline.
ARG SEED_COUNT=45
RUN python scripts/seed_demo.py --count ${SEED_COUNT} \
    && python -c "import pathlib; print('seeded', len(list(pathlib.Path('data/uploads').glob('*'))), 'images')"

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://localhost:${PORT:-8000}/health || exit 1

# Shell form so ${PORT} is expanded. Hosting platforms assign the port at run
# time and expect the process to bind to it.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --app-dir apps/api
