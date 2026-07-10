# FrameInsight edge runtime image.
# One image for every client site — what changes per client is the mounted
# site directory (site.yaml + zones/ + apps/), never the image.
#
#   docker build -t frameinsight/edge:0.1.0 -f docker/Dockerfile .
#
# (scripts/run_edge.sh builds it on first use and runs a site.)

FROM nvcr.io/nvidia/deepstream:9.0-triton-multiarch

# pyservicemaker (the DeepStream Python API) ships as a wheel inside the
# container — it is not on PyPI.
RUN pip3 install --no-cache-dir --break-system-packages \
    /opt/nvidia/deepstream/deepstream/service-maker/python/pyservicemaker*.whl \
    pyyaml

COPY pyproject.toml /opt/frameinsight/
COPY frameinsight /opt/frameinsight/frameinsight
RUN pip3 install --no-cache-dir --break-system-packages /opt/frameinsight

ENTRYPOINT ["frameinsight"]
CMD ["--help"]
