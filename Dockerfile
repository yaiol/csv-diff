FROM python:3.12-alpine
RUN pip install csv-diff
WORKDIR /files
ENTRYPOINT ["csv-diff"]
CMD ["--help"]
