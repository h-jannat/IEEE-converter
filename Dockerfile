FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

ARG PANDOC_VERSION=3.6.4
ENV PANDOC_VERSION=${PANDOC_VERSION}

RUN apt-get update && apt-get install -y --no-install-recommends \
  ca-certificates \
  curl \
  python3 \
  python3-pip \
  texlive-bibtex-extra \
  texlive-fonts-recommended \
  texlive-latex-base \
  texlive-latex-extra \
  texlive-latex-recommended \
  texlive-science \
  && rm -rf /var/lib/apt/lists/*

# Download and install pandoc as a separate step.
RUN curl -fsSL -o /tmp/pandoc.deb \
  "https://github.com/jgm/pandoc/releases/download/${PANDOC_VERSION}/pandoc-${PANDOC_VERSION}-1-amd64.deb" \
  && dpkg -i /tmp/pandoc.deb || apt-get -f install -y \
  && rm -f /tmp/pandoc.deb

COPY requirements.txt /app/requirements.txt
RUN python3 -m pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

EXPOSE 5000

CMD ["python3", "app.py"]
