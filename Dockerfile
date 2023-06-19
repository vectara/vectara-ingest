FROM --platform=linux/amd64 ubuntu:20.04

ENV DEBIAN_FRONTEND noninteractive
RUN sed 's/main$/main universe/' -i /etc/apt/sources.list
RUN apt-get update
RUN apt-get upgrade -y

# Download and install stuff
RUN apt-get install -y build-essential xorg libssl-dev libxrender-dev wget git
RUN apt-get install -y --no-install-recommends xvfb libfontconfig libjpeg-turbo8 xfonts-75dpi fontconfig
RUN apt-get update
RUN apt-get install -y vim

# Install wkhtmltopdf stuff
RUN wget --no-check-certificate https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6-1/wkhtmltox_0.12.6-1.focal_amd64.deb
RUN dpkg -i wkhtmltox_0.12.6-1.focal_amd64.deb
RUN rm wkhtmltox_0.12.6-1.focal_amd64.deb

# Python and PIP
RUN apt-get install -y python3 python3-pip
RUN pip3 install --upgrade pip

RUN apt-get update
RUN apt-get install -y poppler-utils tesseract-ocr libtesseract-dev

ENV HOME /home/vectara
ENV XDG_RUNTIME_DIR=/tmp
WORKDIR ${HOME}

RUN apt-get update && apt-get install -y curl ca-certificates
RUN curl -fsSL https://deb.nodesource.com/setup_16.x | bash -
RUN apt-get install -y nodejs

COPY requirements.txt $HOME/
RUN pip install -r requirements.txt
RUN playwright install --with-deps firefox

COPY *.py $HOME/
COPY core/*.py $HOME/core/
COPY crawlers/ $HOME/crawlers/

ENTRYPOINT ["/bin/bash", "-l", "-c"]
#CMD ["tail -f /dev/null"]
CMD ["python3 ingest.py $CONFIG $PROFILE"]
