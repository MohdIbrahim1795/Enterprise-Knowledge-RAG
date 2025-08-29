# airflow/processing_logic/indexer.py
import os
import boto3
from openai import OpenAI
from langchain_community.document_loaders import S3DirectoryLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
import chromadb

# Configuration from Environment Variables & Airflow Connections ---

CHROMA_COLLECTION_NAME = "enterprise-knowledge-base"
MINIO_ENDPOINT = "http://minio:9000" # Service name from docker-compose
MINIO_ROOT_USER = os.environ.get("MINIO_ROOT_USER")
MINIO_ROOT_PASSWORD = os.environ.get("MINIO_ROOT_PASSWORD")
MINIO_BUCKET = os.environ.get("MINIO_BUCKET")
SOURCE_PREFIX = "source/"
PROCESSED_PREFIX = "processed/"

# Initializing Client
s3_client = boto3.client(
    's3',
    endpoint_url=MINIO_ENDPOINT,
    aws_access_key_id=MINIO_ROOT_USER,
    aws_secret_access_key=MINIO_ROOT_PASSWORD
)

openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY")) # Corrected

chroma_client = chromadb.Client()
try:
    # Check if Chroma collection exists, create if not
    collection = chroma_client.get_or_create_collection(CHROMA_COLLECTION_NAME)
    print(f"Chroma collection '{CHROMA_COLLECTION_NAME}' loaded/created.")
except Exception as e:
    print(f"Error initializing ChromaDB: {e}")
    raise

def get_openai_embeddings(texts):
    """Generates embeddings for a list of texts using OpenAI's text-embedding-3-small."""
    try:
        response = openai_client.embeddings.create(input=texts, model="text-embedding-3-small")
        return [item.embedding for item in response.data]
    except Exception as e:
        print(f"Error generating OpenAI embeddings: {e}")
        raise

def run_indexing_pipeline():
    """
    The main indexing pipeline function.
    Loads documents from MinIO, splits them, generates embeddings, and upserts to ChromaDB.
    """
    print("Starting Open-Source RAG indexing pipeline...")
    
    try:
        loader = S3DirectoryLoader(
            bucket_name=MINIO_BUCKET,
            prefix=SOURCE_PREFIX,
            s3_client=s3_client # Pass the configured s3_client
        )
        documents = loader.load()
        print(f"Loaded {len(documents)} documents from MinIO bucket '{MINIO_BUCKET}' with prefix '{SOURCE_PREFIX}'.")
        
        if not documents:
            print("No new documents found. Exiting.")
            return

    except Exception as e:
        print(f"Error loading documents from MinIO: {e}")
        raise

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    docs_chunks = text_splitter.split_documents(documents)
    print(f"Split documents into {len(docs_chunks)} chunks.")

    batch_size = 30

    print(f"Generating embeddings and preparing vectors in batches of {batch_size}...")
    for i in range(0, len(docs_chunks), batch_size):
        batch_chunks = docs_chunks[i:i + batch_size]
        texts_to_embed = [chunk.page_content for chunk in batch_chunks]
        
        print(f"  Processing batch {i//batch_size + 1}/{(len(docs_chunks) + batch_size - 1)//batch_size}...")
        
        try:
            embeddings = get_openai_embeddings(texts_to_embed)
        except Exception as e:
            print(f"  Error generating embeddings for batch {i//batch_size + 1}. Skipping batch. Error: {e}")
            continue # Skip to the next batch if embedding fails
            
        ids = []
        metadatas = []
        for j, chunk in enumerate(batch_chunks):
            # Create a unique ID for each chunk. Source file + chunk index.
            source_filename = os.path.basename(chunk.metadata.get('source', f'unknown_file_{i+j}'))
            sanitized_source_filename = ''.join(e if e.isalnum() else '-' for e in source_filename)
            vector_id = f"{sanitized_source_filename}-{i+j}"
            ids.append(vector_id)
            metadatas.append({
                "source": chunk.metadata.get('source'), # Store original source filename
                "text": chunk.page_content # Store the actual text chunk
            })
        
        # Upsert to ChromaDB in batches
        try:
            print(f"    Upserting {len(ids)} vectors to ChromaDB...")
            collection.add(
                embeddings=embeddings,
                documents=texts_to_embed,
                metadatas=metadatas,
                ids=ids
            )
            print(f"    Upserted batch {i//batch_size + 1} successfully.")
        except Exception as e:
            print(f"    Error upserting to ChromaDB for batch {i//batch_size + 1}: {e}")

    print("Moving processed files in MinIO...")
    # This part needs careful handling when using Langchain's S3DirectoryLoader
    # Langchain's loader doesn't inherently handle moving files.
    # We need to manually iterate through objects to copy and delete them.
    try:
        paginator = s3_client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=MINIO_BUCKET, Prefix=SOURCE_PREFIX)
        
        for page in pages:
            objects_to_process = page.get('Contents', [])
            if not objects_to_process: continue

            for obj in objects_to_process:
                # Skip the prefix itself if it's listed as an object
                if obj['Key'] == SOURCE_PREFIX: continue
                
                copy_source = {'Bucket': MINIO_BUCKET, 'Key': obj['Key']}
                # Construct the new key by replacing the source prefix with the processed prefix
                new_key = obj['Key'].replace(SOURCE_PREFIX, PROCESSED_PREFIX, 1)
                
                print(f"  Copying s3://{MINIO_BUCKET}/{obj['Key']} to s3://{MINIO_BUCKET}/{new_key}")
                s3_client.copy_object(Bucket=MINIO_BUCKET, CopySource=copy_source, Key=new_key)
                
                print(f"  Deleting original s3://{MINIO_BUCKET}/{obj['Key']}")
                s3_client.delete_object(Bucket=MINIO_BUCKET, Key=obj['Key'])
        
        print("Finished moving processed files.")

    except Exception as e:
        print(f"Error during MinIO file processing: {e}")
        # Depending on requirements, you might want to fail the task here if file moving is critical.
        # raise

    print("Open-Source RAG indexing pipeline finished successfully.")

# --- End of File ---
