# Dedicated ARM64 runtime; never modifies existing images or host packages.
FROM nvidia/cuda:13.0.0-devel-ubuntu24.04
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-venv python3-dev git ca-certificates ffmpeg \
    build-essential pkg-config libavformat-dev libavcodec-dev libavdevice-dev \
    libavutil-dev libavfilter-dev libswscale-dev libswresample-dev libsndfile1 \
    && apt-get clean
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}" PIP_NO_CACHE_DIR=1 PYTHONDONTWRITEBYTECODE=1
RUN pip install torch==2.10.0 torchvision==0.25.0 torchaudio==2.10.0 \
    --index-url https://download.pytorch.org/whl/cu130
RUN git init /opt/dreamx && cd /opt/dreamx \
    && git remote add origin https://github.com/AMAP-ML/DreamX-Creator.git \
    && git fetch --depth 1 origin 215d4cd7fbed7e161ab508ae1f85a8fee0536f62 \
    && git checkout --detach FETCH_HEAD
RUN pip install -r /opt/dreamx/audio_video_generation/requirements.txt && pip check
COPY probe.py /opt/probe.py
WORKDIR /opt/dreamx/audio_video_generation
ENV PYTHONPATH=/opt/dreamx/audio_video_generation \
    USER=dreamx HOME=/tmp TORCHINDUCTOR_CACHE_DIR=/tmp/dreamx-inductor \
    LD_LIBRARY_PATH=/opt/venv/lib/python3.12/site-packages/nvidia/cu13/lib:/usr/local/nvidia/lib:/usr/local/nvidia/lib64
CMD ["python", "/opt/probe.py"]
