
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND noninteractive
RUN sed 's/main$/main universe/' -i /etc/apt/sources.list
RUN apt-get upgrade -y
RUN apt-get update

# Download and install stuff

RUN apt-get install -y -f build-essential xorg libssl-dev libxrender-dev wget git curl \
                          vim wkhtmltopdf libssl-dev unixodbc poppler-utils tesseract-ocr libtesseract-dev 
RUN apt-get install -y --no-install-recommends xvfb libfontconfig libjpeg-turbo8 xfonts-75dpi fontconfig
RUN apt-get update

ENV HOME /home/vectara
ENV XDG_RUNTIME_DIR=/tmp
ENV RAY_DEDUP_LOGS="0"
WORKDIR ${HOME}
SHELL ["/bin/bash", "-c"]

RUN apt-get install -y python3-pip
RUN pip3 install poetry

COPY poetry.lock pyproject.toml $HOME/
RUN poetry config virtualenvs.create false
RUN poetry install --only main
RUN playwright install --with-deps firefox

# Install additional large libraries for unstructured inference and PII detection
ARG INSTALL_EXTRA=false
COPY requirements.txt $HOME/
RUN if [ "$INSTALL_EXTRA" = "true" ]; then \
        pip3 install -r requirements.txt && \
        python3 -m spacy download en_core_web_lg; \
    fi

COPY *.py $HOME/
COPY core/*.py $HOME/core/
COPY crawlers/ $HOME/crawlers/

ENTRYPOINT ["/bin/bash", "-l", "-c"]
CMD ["python3 ingest.py $CONFIG $PROFILE"]
