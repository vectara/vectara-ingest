FROM --platform=linux/amd64 ubuntu:22.04

ENV DEBIAN_FRONTEND noninteractive
RUN sed 's/main$/main universe/' -i /etc/apt/sources.list
RUN apt-get upgrade -y
RUN apt-get update

# Download and install stuff
RUN apt-get install -y -f build-essential xorg libssl-dev libxrender-dev wget git curl
RUN apt-get install -y --no-install-recommends xvfb libfontconfig libjpeg-turbo8 xfonts-75dpi fontconfig
RUN apt-get update
RUN apt-get install -y vim
RUN apt install -y unixodbc

RUN wget http://archive.ubuntu.com/ubuntu/pool/main/o/openssl/libssl1.1_1.1.0g-2ubuntu4_amd64.deb
RUN dpkg -i libssl1.1_1.1.0g-2ubuntu4_amd64.deb

# Install wkhtmltopdf stuff
RUN wget --no-check-certificate https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6-1/wkhtmltox_0.12.6-1.focal_amd64.deb
RUN dpkg -i wkhtmltox_0.12.6-1.focal_amd64.deb
RUN rm wkhtmltox_0.12.6-1.focal_amd64.deb

RUN apt-get update
RUN apt-get install -y poppler-utils tesseract-ocr libtesseract-dev 

ENV HOME /home/vectara
ENV XDG_RUNTIME_DIR=/tmp
WORKDIR ${HOME}

RUN apt-get install -y python3-pip
RUN pip3 install poetry

COPY poetry.lock pyproject.toml $HOME/
RUN poetry config virtualenvs.create false
RUN poetry install --only main
RUN playwright install --with-deps firefox

# Install additional large libraries for unstructured inference and PII detection
ARG INSTALL_EXTRA=false
RUN echo $INSTALL_EXTRA >> qq.txt
COPY requirements.txt $HOME/
RUN if [ "$INSTALL_EXTRA" = "true" ]; then \
        pip3 install -r requirements.txt && \
        python3 -m spacy download en_core_web_lg; \
    fi

COPY *.py $HOME/
COPY core/*.py $HOME/core/
COPY crawlers/ $HOME/crawlers/

ENTRYPOINT ["/bin/bash", "-l", "-c"]
#CMD ["tail -f /dev/null"]
CMD ["python3 ingest.py $CONFIG $PROFILE"]
