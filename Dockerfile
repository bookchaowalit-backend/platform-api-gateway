# Standard library only: no dependency install step (SPEC-001 R8).
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src GATEWAY_HOST=0.0.0.0
WORKDIR /app
COPY src ./src
COPY routes.json ./routes.json
RUN useradd --system --uid 10001 gateway
# Image hardening: take Debian security fixes newer than the base tag, then drop the base
# image's pip (the app runs from its installed environment; pip's vendored urllib3/msgpack/
# setuptools copies are what the Trivy image scan flags).
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/* \
    && /usr/local/bin/python3 -m pip uninstall -y --disable-pip-version-check pip
USER gateway
CMD ["python", "-c", "from book_api_gateway.server import main; raise SystemExit(main())"]
