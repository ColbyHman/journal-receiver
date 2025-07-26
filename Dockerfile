FROM python:3.11

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

RUN mkdir -p /app/src/journal_receiver/uploads

ENV UPLOAD_FOLDER=/app/src/journal_receiver/uploads

EXPOSE 8000

CMD ["uvicorn", "src.journal_receiver.main:app", "--host", "0.0.0.0", "--port", "8000"]
