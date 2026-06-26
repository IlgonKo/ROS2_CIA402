FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONPATH=/workspace
ENV PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    python-is-python3 \
    python3 \
    python3-tk \
    tk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

CMD ["python3", "-B", "axis_server/control_panel.py"]
