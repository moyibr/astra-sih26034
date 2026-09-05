# The API and the vision pipeline share one image.
#
# They are logically separate services and the compose file runs them as such,
# but they share heavy dependencies -- OpenCV, ONNX Runtime, the OCR models --
# and building that layer twice would double both the build time and the image
# footprint for no benefit at this scale.

FROM python:3.12-slim AS base

# OMP_NUM_THREADS and OPENBLAS_NUM_THREADS are pinned to one because ONNX
# Runtime and OpenCV each spawn a thread pool per core by default, which on a
# 512 MB instance costs far more memory than the parallelism is worth. A scan
# takes a few seconds either way.
#
# The comment sits above the instruction, not inside it: a `#` within a
# backslash continuation comments out the whole remainder of the joined line,
# which here would have quietly dropped both of those variables.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
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

# RapidOCR depends on opencv-python, the desktop build, which is compiled
# against X11 and drags in libraries a server image has no reason to carry.
# Both variants install the same `cv2` module into the same directory, so
# whichever lands second wins -- and when that is the desktop build, every
# import fails for want of libxcb. Keeping only the headless build is both the
# fix and 74 MB smaller. Nothing here uses a GUI function, and cv2.aruco has
# lived in base OpenCV since 4.7, so marker detection is unaffected.
#
# Every comment about this sits *above* the instruction rather than inside it.
# A backslash joins the following line onto this one, so a `#` indented within
# a continuation does not comment out one line -- it comments out the entire
# remainder of the joined command. That is what silently deleted the two pip
# calls below on the previous attempt, leaving the desktop build in place.
RUN pip install --upgrade pip \
    && pip install -e packages/schema -e packages/rulepacks -e "apps/vision[ocr]" -e apps/api \
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

# The demo inspections, generated once by scripts/build_demo_dataset.py and
# committed, rather than produced here. Running OCR during a build put OpenCV,
# ONNX Runtime and a minute of computation on the critical path of every
# deployment, and it had to be redone on every restart of a host with no
# persistent disk. Copying a file does not.
COPY data/demo/ data/demo/

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://localhost:${PORT:-8000}/health || exit 1

# Shell form so ${PORT} is expanded. Hosting platforms assign the port at run
# time and expect the process to bind to it.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --app-dir apps/api
