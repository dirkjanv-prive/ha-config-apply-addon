ARG BUILD_FROM
FROM $BUILD_FROM

# git to fetch the config repo; python3 + libs to run the repo's apply scripts.
RUN apk add --no-cache git python3 py3-pip \
    && pip3 install --no-cache-dir --break-system-packages websocket-client

COPY run.py /run.py
COPY run.sh /run.sh
RUN chmod +x /run.sh

# Start via with-contenv (in run.sh) so SUPERVISOR_TOKEN reaches the process.
CMD [ "/run.sh" ]
