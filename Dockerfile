FROM --platform=linux/amd64 ubuntu:22.04

ENV DEBIAN_FRONTEND noninteractive
RUN sed 's/main$/main universe/' -i /etc/apt/sources.list
RUN apt-get update
RUN apt-get upgrade -y

# Download and install stuff
RUN apt-get install -y build-essential xorg libssl-dev libxrender-dev wget git curl
RUN apt-get install -y --no-install-recommends xvfb libfontconfig libjpeg-turbo8 xfonts-75dpi fontconfig
RUN apt-get update
RUN apt-get install -y vim
RUN apt install -y unixodbc

RUN apt-get install -y python3-pip
RUN pip3 install --upgrade pip
RUN pip install psycopg2-binary


RUN wget http://archive.ubuntu.com/ubuntu/pool/main/o/openssl/libssl1.1_1.1.0g-2ubuntu4_amd64.deb
RUN dpkg -i libssl1.1_1.1.0g-2ubuntu4_amd64.deb

# Install wkhtmltopdf stuff
RUN wget --no-check-certificate https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6-1/wkhtmltox_0.12.6-1.focal_amd64.deb
RUN dpkg -i wkhtmltox_0.12.6-1.focal_amd64.deb
RUN rm wkhtmltox_0.12.6-1.focal_amd64.deb

RUN apt-get install -y python3-pip
RUN pip3 install --upgrade pip

RUN apt-get update
RUN apt-get install -y poppler-utils tesseract-ocr libtesseract-dev 

ENV HOME /home/vectara
ENV XDG_RUNTIME_DIR=/tmp
WORKDIR ${HOME}

RUN pip3.10 install poetry

COPY poetry.lock pyproject.toml $HOME/
RUN poetry config virtualenvs.create false
RUN poetry install --no-dev

RUN python3 -m spacy download en_core_web_lg
RUN playwright install --with-deps firefox

# Fixing issue with onnxruntime
RUN apt-get install execstack
RUN execstack -c /usr/local/lib/python3.10/dist-packages/onnxruntime/capi/onnxruntime_pybind11_state.cpython-310-x86_64-linux-gnu.so

COPY *.py $HOME/
COPY core/*.py $HOME/core/
COPY crawlers/ $HOME/crawlers/

ENTRYPOINT ["/bin/bash", "-l", "-c"]
#CMD ["tail -f /dev/null"]
CMD ["python3 ingest.py $CONFIG $PROFILE"]
