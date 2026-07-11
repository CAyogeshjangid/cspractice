FROM python:3.12-slim

WORKDIR /srv
COPY pyproject.toml ./
RUN pip install --no-cache-dir .
COPY . .
# VERSION is mounted/copied from repo root by compose build context in prod;
# for local builds, compose mounts the repo. Fail loudly if absent at runtime.

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
