FROM mcr.microsoft.com/devcontainers/python:3.13

RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get install -y --no-install-recommends \
    libportaudio2 \
    pulseaudio \
    pulseaudio-utils \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUTF8=1 \
    PYTHONDONTWRITEBYTECODE=1