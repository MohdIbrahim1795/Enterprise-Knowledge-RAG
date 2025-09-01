# airflow/Dockerfile
FROM apache/airflow:2.8.0-python3.9

USER root

# Install system dependencies for PDF processing
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    poppler-utils \
    tesseract-ocr \
    libtesseract-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

USER airflow

# Install Python packages required by our custom DAG and processing logic
# Specify numpy<2.0 to avoid compatibility issues with other packages
RUN pip install --no-cache-dir \
    "numpy<2.0" \
    apache-airflow-providers-amazon \
    chromadb \
    openai \
    langchain-community \
    langchain \
    boto3 \
    "unstructured[pdf]" \
    qdrant-client \
    python-dotenv \
    pypdf \
    pdfminer.six \
    pdf2image \
    pillow \
    pytesseract

# Copy our custom Airflow processing logic into the container's plugins path
COPY ./processing_logic /opt/airflow/processing_logic

# Ensure Airflow can find the DAG file
COPY ./dags /opt/airflow/dags

# Set the default user for Airflow processes
USER airflow

ENV PYTHONPATH "${PYTHONPATH}:/opt/airflow"
