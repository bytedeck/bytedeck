# syntax=docker/dockerfile:1

###############################################################################
# Build stage: compiles the packages that need a toolchain (uwsgi, psycopg2)
# into wheels, so the compilers and dev headers stay out of the runtime image.
###############################################################################
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# build-essential compiles uwsgi, and libpcre2-dev gives uwsgi its internal
# routing/regex support (built without it, uwsgi warns at startup and disables
# those features).
# https://stackoverflow.com/questions/21669354/rebuild-uwsgi-with-pcre-support
# libpq-dev is Postgres' client headers. The pinned psycopg2-binary ships its
# own libpq so nothing needs them today, but they keep the build working if the
# requirement is ever switched to source-built psycopg2, which is what the
# psycopg maintainers recommend for production.
# https://github.com/psycopg/psycopg2/issues/699
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpcre2-dev \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# The requirements files are copied on their own so the wheel build below stays
# cached until a dependency actually changes, rather than on every source edit.
# https://docs.docker.com/build/cache/
COPY requirements.txt requirements-production.txt ./

# uwsgi is built here rather than listed in requirements*.txt on purpose: only
# the container needs it (dev uses runserver, production runs uwsgi), and local
# venvs on Windows/macOS can't build it. Pinned for reproducible images: bump
# deliberately.
RUN pip wheel --wheel-dir /wheels -r requirements.txt uwsgi==2.0.31


###############################################################################
# Runtime stage: installs those wheels onto a clean base, so the image ships
# the app and its libraries without the build toolchain behind them.
###############################################################################
FROM python:3.12-slim

# uwsgi reads SIGTERM as "brutal reload" rather than "shut down", so a stopping
# container has to be signalled with SIGINT for the app to exit cleanly. The
# graceful stop also lets coverage flush its report and celery-beat remove its
# pid file.
# https://uwsgi-docs.readthedocs.io/en/latest/Management.html
STOPSIGNAL SIGINT

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    SHELL=/bin/bash

# libpcre2-8-0 is the runtime half of the uwsgi regex support built above, and
# libpq5 the runtime half of libpq-dev. procps supplies the pgrep that the
# celery-beat healthcheck in docker-compose.yml runs.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpcre2-8-0 \
        libpq5 \
        procps \
    && rm -rf /var/lib/apt/lists/*

# Created before the source is copied so COPY can assign ownership as it goes:
# a `chown -R` afterwards would write a second full copy of the tree into its
# own layer and roughly double the image's application size.
RUN useradd --create-home --shell /bin/bash app

WORKDIR /app

# --no-index keeps the install offline: every dependency has to come from the
# wheels the build stage resolved, so the runtime image can't silently pull a
# different version than the one that was built.
COPY requirements.txt requirements-production.txt ./
COPY --from=builder /wheels /wheels
RUN pip install --no-index --find-links=/wheels -r requirements.txt uwsgi==2.0.31 \
    && rm -rf /wheels

# Owned by `app` so the running container can write the few things it creates
# next to the source, such as celery-beat's pid file.
COPY --chown=app:app . /app/

# Run unprivileged by default so production gets a non-root container without
# depending on a compose-level override. Development and CI bind-mount the host
# checkout over /app and have to write into it (coverage output, makemigrations),
# so those containers run as root: see docker-compose.override.yml.
USER app
