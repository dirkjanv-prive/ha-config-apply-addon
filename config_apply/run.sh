#!/usr/bin/with-contenv bashio
# with-contenv imports the container environment (incl. SUPERVISOR_TOKEN) that
# s6-overlay otherwise hides from the CMD process. Then hand off to the service.
exec python3 -u /run.py
