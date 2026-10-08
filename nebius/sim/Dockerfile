# Showtime simulation sandbox: JuPedSim + PedPy. Runs with --network=none as a non-root user.
FROM python:3.12-slim

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLBACKEND=Agg \
    MPLCONFIGDIR=/tmp

COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt \
 && pip install --no-deps jupedsim==1.4.2 \
 && python -c "import jupedsim, pedpy; print('jupedsim', jupedsim.__version__, 'pedpy', pedpy.__version__)" \
 && rm -rf /root/.cache /tmp/requirements.txt

RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin sim
WORKDIR /app
COPY --chown=root:root *.py /app/
COPY --chown=root:root plugins /app/plugins
RUN python -m compileall -q /app
USER sim
LABEL com.showtime.project="true" org.opencontainers.image.title="showtime-sim"
CMD ["python", "/app/run_sim.py", "/work"]
