FROM python:slim
ENV DEBIAN_FRONTEND=noninteractive

RUN sed -i -e's/ main/ main contrib non-free/g' /etc/apt/sources.list.d/debian.sources \
    && apt update \
    && apt-get install -y netperf iputils-ping irtt \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir matplotlib flent 

ENTRYPOINT ["flent"]