
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND noninteractive
RUN sed 's/main$/main universe/' -i /etc/apt/sources.list

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libssl-dev wget git curl \
    vim wkhtmltopdf unixodbc poppler-utils \
    fontconfig fonts-noto-color-emoji fonts-unifont \
    python3-pip python3-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

ENV HOME /home/vectara
ENV XDG_RUNTIME_DIR=/tmp
ENV RAY_DEDUP_LOGS="0"
WORKDIR ${HOME}

COPY poetry.lock pyproject.toml $HOME/

RUN pip3 install poetry && \
    poetry config virtualenvs.create false && \
    poetry install --only main && \
    rm -rf ~/.cache/pypoetry

RUN playwright install --with-deps firefox

# Install additional large libraries for unstructured inference and PII detection
ARG INSTALL_EXTRA=false
COPY requirements.txt $HOME/
RUN if [ "$INSTALL_EXTRA" = "true" ]; then \
        apt-get install -y --no-install-recommends tesseract-ocr libtesseract-dev && \
        python3 -m pip install -r requirements.txt && \
        python3 -m spacy download en_core_web_lg; \
    fi

COPY *.py $HOME/
COPY core/*.py $HOME/core/
COPY crawlers/ $HOME/crawlers/

SHELL ["/bin/bash", "-c"]
ENTRYPOINT ["/bin/bash", "-l", "-c"]
CMD ["python3 ingest.py $CONFIG $PROFILE"]
