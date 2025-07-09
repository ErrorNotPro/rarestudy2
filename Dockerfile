FROM python:3.10.14-bookworm
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . /app
CMD ["sh", "-c", "gunicorn app:app --bind 0.0.0.0:$PORT"]