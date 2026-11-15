# API image, shaped for a Hugging Face Docker Space (port 7860, non-root user 1000).
# Not built yet: Docker is not installed on the development machine. Debian ships
# Tesseract 5.3, the benchmark used 5.5.4, so rerun the tests after building.
FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr curl \
 && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 user
WORKDIR /home/user/app

COPY requirements-app.txt .
RUN pip install --no-cache-dir -r requirements-app.txt

# The benchmark used the tessdata_best models, not Debian's default ones.
RUN mkdir -p data/tessdata \
 && for lang in tha eng; do \
      curl -fsSL -o data/tessdata/$lang.traineddata https://github.com/tesseract-ocr/tessdata_best/raw/main/$lang.traineddata; \
    done

COPY scripts scripts
COPY app app
RUN chown -R user /home/user/app
USER user

EXPOSE 7860
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
