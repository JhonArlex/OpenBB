# Local DCF/WACC overlay (odp-markets) is not installed here.
# From the OpenBB repo root, build and run with the extension:
#   docker compose up --build
# Image tag: openbb-platform:odp  (do not use this vanilla image for valuation routes)
FROM python:3.10-slim-bookworm

WORKDIR /app

RUN pip install "openbb[all]"
RUN pip install openbb-platform-api

EXPOSE 6900

ENTRYPOINT ["openbb-api", "--host", "0.0.0.0"]
