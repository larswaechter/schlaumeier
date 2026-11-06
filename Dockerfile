FROM python:3.14-slim-trixie

WORKDIR /code

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr adb \
    && rm -rf /var/lib/apt/lists/*

COPY ./main.py ./cropper.py ./run.sh ./requirements.txt /code/

RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

RUN chmod +x ./run.sh
RUN mkdir ./screenshots

EXPOSE 5037

CMD ["./run.sh"]
