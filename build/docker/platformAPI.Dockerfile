# Standalone OpenBB Platform API (Dokploy / local).
# Valuation overlay lives in aifinance-frontend, not in this image.
FROM python:3.10-slim-bookworm

WORKDIR /app

RUN pip install "openbb[all]==4.7.2"
RUN pip install openbb-platform-api==1.3.6

COPY build/docker/merge_provider_credentials.py /app/merge_provider_credentials.py

EXPOSE 6900

ENTRYPOINT ["python", "/app/merge_provider_credentials.py"]
