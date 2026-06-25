FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONPATH=/workspace
ENV PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    iproute2 \
    libpcap-dev \
    python-is-python3 \
    python3 \
    python3-dev \
    python3-pip \
    python3-tk \
    tk \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --no-cache-dir --break-system-packages pysoem

WORKDIR /workspace

CMD ["python3", "-B", "axis_server/server.py", "enp1s0", "--backend", "pysoem", "--axis-count", "1"]
