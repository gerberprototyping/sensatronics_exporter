FROM python:3-alpine

WORKDIR /usr/src/app

COPY pip-requirements.txt ./
RUN pip install --no-cache-dir -r pip-requirements.txt

COPY sensatronics_exporter.py ./

EXPOSE 9862
CMD [ "python", "./sensatronics_exporter.py" ]