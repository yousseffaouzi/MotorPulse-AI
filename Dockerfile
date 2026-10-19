FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY motorpulse /app/motorpulse

# Numeric non-root identity avoids adding OS packages or mutating the base image.
USER 65532:65532

HEALTHCHECK --interval=10s --timeout=3s --start-period=3s --retries=3 \
  CMD ["python", "-c", "import json, urllib.request; d=json.load(urllib.request.urlopen('http://127.0.0.1:8765/api/health', timeout=2)); assert d.get('status') == 'ok' and d.get('source') == 'simulation'"]

ENTRYPOINT ["python", "-m", "motorpulse"]
CMD ["--port", "8765"]
