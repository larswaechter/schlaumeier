FROM python:3.9

WORKDIR /code

RUN apt-get update
RUN apt-get install -y tesseract-ocr python3-opencv android-tools-adb

COPY ./main.py /code
COPY ./run.sh /code/run.sh
COPY ./requirements.txt /code/requirements.txt

RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

RUN chmod +x ./run.sh
RUN mkdir ./screenshots

EXPOSE 5037

CMD ["./run.sh"]
