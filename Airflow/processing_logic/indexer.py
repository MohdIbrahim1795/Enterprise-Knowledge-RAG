import os
import boto3
import hashlib
import uuid
import pypdf
from openai import OpenAI
from langchain_community.document_loaders import S3DirectoryLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document
from qdrant_client import QdrantClient
from qdrant_client.http import models
import time
import tempfile

# Configuration from Environment Variables & Airflow Connections ---

COLLECTION_NAME = "enterprise-knowledge-base"
MINIO_ENDPOINT = "http://minio:9000" 
MINIO_ROOT_USER = os.environ.get("MINIO_ROOT_USER")
MINIO_ROOT_PASSWORD = os.environ.get("MINIO_ROOT_PASSWORD")
MINIO_BUCKET = os.environ.get("MINIO_BUCKET")
SOURCE_PREFIX = "source/" 
PROCESSED_PREFIX = "processed/"
VECTOR_SIZE = 1536  # OpenAI embedding dimension

# Initializing Client
s3_client = boto3.client(
    's3',
    endpoint_url=MINIO_ENDPOINT,
    aws_access_key_id=MINIO_ROOT_USER,
    aws_secret_access_key=MINIO_ROOT_PASSWORD
)

openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# Initialize Qdrant client
qdrant_client = QdrantClient(host="qdrant", port=6333)

try:
    try:
        # Try to get collections as a health check
        collections = qdrant_client.get_collections()
        print(f"Qdrant connection test successful. Found {len(collections.collections)} collections.")
    except Exception as test_e:
        print(f"WARNING: Qdrant health check failed: {test_e}")
    
    # Check if collection exists, create if not
    collections = qdrant_client.get_collections().collections
    collection_names = [collection.name for collection in collections]
    
    if COLLECTION_NAME not in collection_names:
        # Create collection with the specified parameters
        qdrant_client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(
                size=VECTOR_SIZE,
                distance=models.Distance.COSINE
            )
        )
        print(f"Qdrant collection '{COLLECTION_NAME}' created.")
    else:
        print(f"Qdrant collection '{COLLECTION_NAME}' already exists.")
except TimeoutError as te:
    print(f"ERROR: Qdrant is not responding: {te}")
    raise
except Exception as e:
    print(f"Error initializing Qdrant: {e}")
    raise

def get_openai_embeddings(texts):
    """Generates embeddings for a list of texts using OpenAI's text-embedding-3-small."""
    try:
        response = openai_client.embeddings.create(input=texts, model="text-embedding-3-small")
        return [item.embedding for item in response.data]
    except Exception as e:
        print(f"Error generating OpenAI embeddings: {e}")
        raise

def process_pdf_file(bucket, key):
    """Process a PDF file from MinIO and extract text"""
    try:
        # Download the file to a temporary location
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_file:
            s3_client.download_file(bucket, key, temp_file.name)
            temp_path = temp_file.name
        
        try:
            # Try PyPDFLoader first
            loader = PyPDFLoader(temp_path)
            documents = loader.load()
            print(f"Successfully extracted {len(documents)} documents from file: {key}")
            return documents
        except Exception as e1:
            print(f"PyPDFLoader failed: {e1}, trying alternative method...")
            
        
            # If PyPDFLoader fails, try a different approach with PyPDF directly
        try:
            pdf_reader = pypdf.PdfReader(temp_path)
            documents = []
                
            for i, page in enumerate(pdf_reader.pages):
                text = page.extract_text()
                if text.strip():  # Only add non-empty pages
                    doc = Document(
                        page_content=text,
                        metadata={
                            "source": key,
                            "page": i + 1
                        })
                    documents.append(doc)
                
            print(f"Successfully extracted {len(documents)} documents using PyPDF directly from file: {key}")
            return documents
        except Exception as e2:
            print(f"PyPDF direct extraction failed: {e2}")
        
            # If all methods fail, return a placeholder document
            doc = Document(
                page_content=f"Error processing document {key}. Error: {str(e1)}; {str(e2)}",
                metadata={"source": key, "error": f"{str(e1)}; {str(e2)}"}
            )
            return [doc]
    except Exception as e:
        print(f"Error in process_pdf_file for {key}: {e}")
        # Create a placeholder document if parsing fails
        doc = Document(
            page_content=f"Error processing document {key}. Error: {str(e)}",
            metadata={"source": key, "error": str(e)}
        )
        return [doc]
    finally:
        # Clean up the temp file
        try:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception as e:
            print(f"Warning: Failed to delete temporary file: {e}")

def run_indexing_pipeline():
    """
    The main indexing pipeline function.
    Loads documents from MinIO, splits them, generates embeddings, and upserts to Qdrant.
    """
    print("Starting Open-Source RAG indexing pipeline...")
    
    try:
        print(f"Attempting to load documents from bucket '{MINIO_BUCKET}' with prefix '{SOURCE_PREFIX}'")
        
        # List objects in the bucket
        paginator = s3_client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=MINIO_BUCKET, Prefix=SOURCE_PREFIX)
        
        all_documents = []
        file_keys = []
        
        # Get all file keys first
        for page in pages:
            for obj in page.get('Contents', []):
                file_key = obj['Key']
                
                # Skip the directory itself
                if file_key == SOURCE_PREFIX or file_key.endswith('/'):
                    continue
                
                file_keys.append(file_key)
        
        if not file_keys:
            print("No files found in the source directory. Exiting.")
            return
        
        print(f"Processing files: {file_keys}")
        
        # Process each file
        for file_key in file_keys:
            print(f"Processing file: {file_key}")
            
            # Check file extension and use appropriate processing method
            if file_key.lower().endswith('.pdf'):
                documents = process_pdf_file(MINIO_BUCKET, file_key)
                all_documents.extend(documents)
            else:
                # Handle other file types if needed
                print(f"Unsupported file type: {file_key}. Skipping.")
                continue
        
        if not all_documents:
            print("No documents were successfully processed. Exiting.")
            return

        # Split documents into chunks
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
        docs_chunks = text_splitter.split_documents(all_documents)
        print(f"Split documents into {len(docs_chunks)} chunks.")
        
        # Filter out very short chunks or chunks with error messages
        filtered_chunks = [chunk for chunk in docs_chunks 
                          if len(chunk.page_content.strip()) > 20 
                          and not chunk.page_content.startswith("Error processing document")]
        
        print(f"After filtering, {len(filtered_chunks)} chunks remain.")
        
        if not filtered_chunks:
            print("No valid chunks remain after filtering. Exiting.")
            return
        
        batch_size = 30

        print(f"Generating embeddings and preparing vectors in batches of {batch_size}...")
        for i in range(0, len(filtered_chunks), batch_size):
            batch_chunks = filtered_chunks[i:i + batch_size]
            texts_to_embed = [chunk.page_content for chunk in batch_chunks]
            
            print(f"  Processing batch {i//batch_size + 1}/{(len(filtered_chunks) + batch_size - 1)//batch_size}...")
            
            try:
                embeddings = get_openai_embeddings(texts_to_embed)
                
                # Create IDs and metadata
                ids = []
                metadatas = []
                for j, chunk in enumerate(batch_chunks):
                    # Create a unique ID for each chunk using UUID
                    source_filename = os.path.basename(chunk.metadata.get('source', f'unknown_file_{i+j}'))
                    content_hash = hashlib.md5(f"{source_filename}-{i+j}-{chunk.page_content[:50]}".encode()).hexdigest()
                    vector_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, content_hash))
                    ids.append(vector_id)
                    metadatas.append({
                        "source": chunk.metadata.get('source'), # Store original source filename
                        "text": chunk.page_content, # Store the actual text chunk
                        "page": chunk.metadata.get('page', None), # Store page number if available
                        "original_id": f"{source_filename}-{i+j}" # Store the original ID for reference
                    })
            except Exception as e:
                print(f"  Error generating embeddings for batch {i//batch_size + 1}. Skipping batch. Error: {e}")
                continue # Skip to the next batch if embedding fails
            
            # Upsert to Qdrant in batches
            try:
                print(f"    Upserting {len(ids)} vectors to Qdrant...")
                
                # Prepare points for Qdrant
                points = []
                for idx, (vector_id, metadata, embedding) in enumerate(zip(ids, metadatas, embeddings)):
                    points.append(models.PointStruct(
                        id=vector_id,  # Using UUID string as ID
                        vector=embedding,
                        payload=metadata  # Using the full metadata object which already contains the text
                    ))
                
                # Attempt the upsert
                if points:  # Only try to upsert if we have points
                    qdrant_client.upsert(
                        collection_name=COLLECTION_NAME,
                        points=points
                    )
                    print(f"    Upserted batch {i//batch_size + 1} successfully.")
                else:
                    print(f"    No valid points to upsert for batch {i//batch_size + 1}.")
                    
            except TimeoutError as te:
                print(f"    WARNING: Qdrant operation timed out for batch {i//batch_size + 1}: {te}")
                print(f"    Skipping this batch and continuing...")
                continue
            except Exception as e:
                print(f"    Error upserting to Qdrant for batch {i//batch_size + 1}: {e}")
                print(f"    Skipping this batch and continuing...")

        print("Moving processed files in MinIO...")
        # Move files from source to processed
        try:
            for file_key in file_keys:
                copy_source = {'Bucket': MINIO_BUCKET, 'Key': file_key}
                # Construct the new key by replacing the source prefix with the processed prefix
                new_key = file_key.replace(SOURCE_PREFIX, PROCESSED_PREFIX, 1)
                
                print(f"  Copying s3://{MINIO_BUCKET}/{file_key} to s3://{MINIO_BUCKET}/{new_key}")
                s3_client.copy_object(Bucket=MINIO_BUCKET, CopySource=copy_source, Key=new_key)
                
                print(f"  Deleting original s3://{MINIO_BUCKET}/{file_key}")
                s3_client.delete_object(Bucket=MINIO_BUCKET, Key=file_key)
            
            print("Finished moving processed files.")

        except Exception as e:
            print(f"Error during MinIO file processing: {e}")
            # Depending on requirements, you might want to fail the task here if file moving is critical.

    except Exception as e:
        print(f"Error in indexing pipeline: {e}")
        raise

    print("Open-Source RAG indexing pipeline finished successfully.")

# --- End of File ---
