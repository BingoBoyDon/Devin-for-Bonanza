FROM python:3.12-slim

WORKDIR /app

COPY ./inventory_demo/pyproject.toml ./
COPY ./inventory_demo/inventory_demo ./inventory_demo

RUN pip install poetry && \
    poetry config virtualenvs.create false && \
    poetry install --no-dev

CMD ["python", "-m", "uvicorn", "inventory_demo.app.main:app", "--host", "0.0.0.0", "--port", "8080"]
