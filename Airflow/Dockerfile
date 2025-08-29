# airflow/Dockerfile
FROM apache/airflow:2.8.0-python3.9

USER root

USER airflow

# Install Python packages required by our custom DAG and processing logic
RUN pip install --no-cache-dir \
    numpy"<2.0" \
    apache-airflow-providers-amazon \
    chromadb \
    openai \
    langchain-community \
    boto3

# Explicitly add boto3 as it's used for S3 operations

# Copy our custom Airflow processing logic into the container's plugins path

COPY ./processing_logic /opt/airflow/processing_logic

# Ensure Airflow can find the DAG file
COPY ./dags /opt/airflow/dags

# Set the default user for Airflow processes
USER airflow

ENV PYTHONPATH "${PYTHONPATH}:/opt/airflow"
