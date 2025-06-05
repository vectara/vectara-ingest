# Stage 1: Build stage
FROM python:3.11-slim AS builder

ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY

ENV http_proxy=$HTTP_PROXY
ENV https_proxy=$HTTPS_PROXY
ENV no_proxy=$NO_PROXY

ENV DEBIAN_FRONTEND=noninteractive \
    HOME=/home/vectara \
    XDG_RUNTIME_DIR=/tmp \
    RAY_DEDUP_LOGS="0" \
    CUDA_VISIBLE_DEVICES="" \
    UV_SYSTEM_PYTHON=1

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libopenblas-dev \
    wget \
    git \
    curl \
    python3-dev \
    && rm -rf /var/lib/apt/lists/* /tmp/*

# Install Python packages
WORKDIR ${HOME}
COPY requirements.txt requirements-extra.txt $HOME/

RUN pip install --no-cache-dir uv==0.6.14
RUN uv pip install --no-cache-dir torch==2.4.1 torchvision==0.19.1 --index-url https://download.pytorch.org/whl/cpu \
    && uv pip install --no-cache-dir -r requirements.txt

ARG INSTALL_EXTRA=false
RUN if [ "$INSTALL_EXTRA" = "true" ]; then \
        uv pip install --no-cache-dir -r requirements-extra.txt && \
        python3 -m spacy download en_core_web_lg; \
    fi
    
# Clean up unnecessary files
RUN find /usr/local -type d \( -name test -o -name tests \) -exec rm -rf '{}' + \
    && find /usr/local -type f \( -name '*.pyc' -o -name '*.pyo' \) -exec rm -rf '{}' + \
    && find /usr/local -type d -name '__pycache__' -exec rm -rf '{}' + \
    && rm -rf /root/.cache/* /tmp/*

# Clean up unnecessary filesin site-packages
RUN find /usr/local/lib/python3.11/site-packages \
    -type d \( -name 'tests' -o -name 'test' -o -name 'examples' \) -exec rm -rf '{}' + \
    && find /usr/local/lib/python3.11/site-packages -type d -name '__pycache__' -exec rm -rf '{}' + \
    && find /usr/local/lib/python3.11/site-packages -type f -name '*.pyc' -exec rm -f '{}' + \
    && find /usr/local/lib/python3.11/site-packages -type f -name '*.pyo' -exec rm -f '{}' +

# Stage 2: Final image
FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    HOME=/home/vectara \
    XDG_RUNTIME_DIR=/tmp \
    RAY_DEDUP_LOGS="0" \
    CUDA_VISIBLE_DEVICES=""

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
#    libopenblas-dev \
    tesseract-ocr \
#    xvfb \
    unixodbc poppler-utils libmagic1 libjpeg62-turbo \
    libfontconfig fonts-noto-color-emoji unifont fonts-indic xfonts-75dpi \
    && rm -rf /var/lib/apt/lists/*
    
# Copy Python packages and application code from the builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Install Playwright browsers
RUN playwright install --with-deps firefox \
    && rm -f /usr/local/bin/pwdebug \
    && rm -rf /var/lib/apt/lists/* /tmp/* /root/.cache/*

# Set working directory
WORKDIR ${HOME}

COPY docker/bin/download-easyocr-models.py /bin/

ARG DOWNLOAD_EASYOCR_MODELS=false

RUN if [ "$DOWNLOAD_EASYOCR_MODELS" = "true" ]; then \
            python3 /bin/download-easyocr-models.py 1>&2; \
    fi


# Copy application code
COPY *.py $HOME/
COPY core/*.py $HOME/core/
COPY crawlers/ $HOME/crawlers/

COPY docker/bin/docker-entrypoint.sh /bin/docker-entrypoint.sh
RUN chmod +x /bin/docker-entrypoint.sh

# Use the script as the entrypoint
ENTRYPOINT ["/bin/docker-entrypoint.sh"]