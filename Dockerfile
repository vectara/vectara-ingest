FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    HOME=/home/vectara  \
    XDG_RUNTIME_DIR=/tmp \
    RAY_DEDUP_LOGS="0" \
    CUDA_VISIBLE_DEVICES=""

RUN sed 's/main$/main universe/' -i /etc/apt/sources.list

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libopenblas-dev \
    unzip \
    wget \
    git \
    curl \
    wkhtmltopdf \
    libssl-dev \
    unixodbc \
    poppler-utils \
    tesseract-ocr \
    libtesseract-dev \
    xvfb \
    python3-pip python3-dev \
    libmagic1  \
    libfontconfig fontconfig \
    libjpeg-turbo8 \
    fonts-noto-color-emoji unifont fonts-indic xfonts-75dpi \
    && apt-get purge -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

ENV OMP_NUM_THREADS=4

# Install python packages
WORKDIR ${HOME}
COPY requirements.txt requirements-extra.txt $HOME/

RUN pip install --no-cache-dir torch==2.4.1 --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps firefox \
    && find /usr/local -type d \( -name test -o -name tests \) -exec rm -rf '{}' + \
    && find /usr/local -type f \( -name '*.pyc' -o -name '*.pyo' \) -exec rm -rf '{}' + \
    && find /usr/local -type d \( -name '__pycache__' \) -exec rm -rf '{}' + \
    && find /usr/local -type d \( -name 'build' \) -exec rm -rf '{}' + \
    && rm -rf /root/.cache/* /tmp/* \
    && pip cache purge

# Install additional large packages for all-docs unstructured inference and PII detection
ARG INSTALL_EXTRA=false
RUN if [ "$INSTALL_EXTRA" = "true" ]; then \
        pip3 install --no-cache-dir -r requirements-extra.txt && \
        python3 -m spacy download en_core_web_lg; \
    fi

COPY *.py $HOME/
COPY core/*.py $HOME/core/
COPY crawlers/ $HOME/crawlers/

#SHELL ["/bin/bash", "-c"]
ENTRYPOINT ["/bin/bash", "-l", "-c"]
CMD ["python3 ingest.py $CONFIG $PROFILE"]