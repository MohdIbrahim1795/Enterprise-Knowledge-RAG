# airflow/Dockerfile
FROM apache/airflow:2.5.0

USER root
# Install any system dependencies if needed. For this example, only vim for debugging is useful.
# RUN apt-get update && apt-get install -y vim

USER airflow # Switch back to airflow user for Airflow commands and packages

# Install Python packages required by our custom DAG and processing logic
RUN pip install --no-cache-dir \
    apache-airflow-providers-amazon \
    chromadb \
    openai \
    langchain-community \
    boto3 # Explicitly add boto3 as it's used for S3 operations

# Copy our custom Airflow processing logic into the container's plugins path
# This makes 'processing_logic' importable by our DAGs.
# Ensure you create a zip file of the 'processing_logic' folder.
# Place 'processing_logic.zip' in your Airflow S3 bucket's root (e.g., plugins.zip)
# Airflow MWAA automatically unpacks plugins.zip into the correct location.
# If running Airflow manually via Docker, you'd need to copy it differently.
# For the docker-compose setup provided earlier, we copy it directly into the container.
COPY ./processing_logic /opt/airflow/processing_logic

# Ensure Airflow can find the DAG file
COPY ./dags /opt/airflow/dags

# Set the default user for Airflow processes
USER airflow
