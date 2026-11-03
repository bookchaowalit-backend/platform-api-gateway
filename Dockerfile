# Standard library only: no dependency install step (SPEC-001 R8).
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src GATEWAY_HOST=0.0.0.0
WORKDIR /app
COPY src ./src
COPY routes.json ./routes.json
RUN useradd --system --uid 10001 gateway
USER gateway
CMD ["python", "-c", "from book_api_gateway.server import main; raise SystemExit(main())"]
