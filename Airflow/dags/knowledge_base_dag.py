# Build DAG for Open-Source Knowledge Base Indexing
import pendulum
from airflow.models.dag import DAG
from airflow.operators.python import PythonOperator
from processing_logic.indexer import run_indexing_pipeline

with DAG(
    dag_id='knowledge_base_indexing_daily_opensource',
    start_date=pendulum.datetime(2023, 1, 1, tz="UTC"),
    schedule_interval='@daily',
    catchup=False,
    tags=['rag', 'openai', 'minio', 'opensource'],
    doc_md="""
    Open-Source Knowledge Base Indexing DAG
    This DAG is responsible for ingesting text documents from MinIO,
    generating embeddings using OpenAI, and storing them in Qdrant.
    """
) as dag:
    
    indexing_task = PythonOperator(
        task_id='run_full_indexing_pipeline',
        python_callable=run_indexing_pipeline,
    )
