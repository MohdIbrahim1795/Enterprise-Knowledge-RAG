import os
import uuid
import time
import hashlib
import redis
from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.http import models
from . import models as db_models
from .database import engine, get_db

# Create DB tables on startup
db_models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# Clients Initialization
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if OPENAI_API_KEY and (OPENAI_API_KEY.startswith("'") or OPENAI_API_KEY.startswith('"')):
    # Remove quotes if they exist
    OPENAI_API_KEY = OPENAI_API_KEY.strip("'\"")
COLLECTION_NAME = "enterprise-knowledge-base"
VECTOR_SIZE = 1536  # OpenAI embedding dimension

# Check if the OpenAI API key is valid
if not OPENAI_API_KEY or OPENAI_API_KEY == "sk-..." or (OPENAI_API_KEY.startswith("sk-") and len(OPENAI_API_KEY) < 30):
    print("WARNING: Invalid or missing OpenAI API key. API calls will fail!")
    openai_client = OpenAI(api_key=OPENAI_API_KEY or "dummy_key")
else:
    print(f"Using OpenAI API key: {OPENAI_API_KEY[:10]}...{OPENAI_API_KEY[-4:]}")
    openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Initialize Qdrant client
qdrant_client = QdrantClient(host="qdrant", port=6333)
try:
    # Check if collection exists
    collections = qdrant_client.get_collections().collections
    collection_names = [collection.name for collection in collections]
    
    if COLLECTION_NAME not in collection_names:
        print(f"Creating new Qdrant collection '{COLLECTION_NAME}'...")
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
except Exception as e:
    print(f"Error initializing Qdrant: {e}")
    # We'll continue and let the application fail later if necessary

redis_client = redis.Redis(
    host=os.environ.get("REDIS_HOST"),
    port=int(os.environ.get("REDIS_PORT")),
    decode_responses=True
)

class ChatRequest(BaseModel):
    query: str
    conversation_id: str = None

# Functions for Chat History Management

def get_chat_history(db: Session, conversation_id: str):
    return db.query(db_models.ChatHistory).filter(db_models.ChatHistory.conversation_id == conversation_id).order_by(db_models.ChatHistory.timestamp).all()

def save_chat_history(db: Session, conversation_id, user_query, assistant_response):
    timestamp = int(time.time())
    user_turn = db_models.ChatHistory(conversation_id=conversation_id, timestamp=timestamp, role='user', content=user_query)
    assistant_turn = db_models.ChatHistory(conversation_id=conversation_id, timestamp=timestamp + 1, role='assistant', content=assistant_response)
    db.add(user_turn)
    db.add(assistant_turn)
    db.commit()

def generate_standalone_question(chat_history, latest_query):
    if not chat_history:
        return latest_query
    
    formatted_history = "\n".join([f"{msg.role}: {msg.content}" for msg in chat_history])
    prompt = f"Given the conversation history, rephrase the follow-up question to be a standalone question.\n\n<history>\n{formatted_history}\n</history>\n\nFollow-up Question: {latest_query}\nStandalone Question:"
    
    response = openai_client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0
    )
    return response.choices[0].message.content.strip()

def get_query_embedding(query):
    response = openai_client.embeddings.create(input=[query], model="text-embedding-3-small")
    return response.data[0].embedding

def get_rag_context(query_embedding):
    search_result = qdrant_client.search(
        collection_name=COLLECTION_NAME,
        query_vector=query_embedding,
        limit=3
    )
    
    # Extract text from search results
    contexts = []
    for result in search_result:
        contexts.append(result.payload.get("text", ""))
    
    return "\n\n".join(contexts)

def get_llm_response(query, context):
    prompt = f"You are an expert Q&A assistant. Answer the user's question based only on the provided context. If the answer is not in the context, say you don't have enough information.\n\n<context>\n{context}\n</context>\n\nQuestion: {query}"
    
    # Try different models in order of preference
    models = ["gpt-3.5-turbo", "gpt-3.5-turbo-instruct", "text-davinci-003", "davinci"]
    
    for model in models:
        try:
            print(f"Trying model: {model}")
            
            # Different handling for chat models vs completion models
            if "gpt" in model.lower():
                response = openai_client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}]
                )
                return response.choices[0].message.content
            else:
                # For older completion models
                response = openai_client.completions.create(
                    model=model,
                    prompt=prompt,
                    max_tokens=500
                )
                return response.choices[0].text.strip()
                
        except Exception as e:
            print(f"Error with model {model}: {e}")
            continue
    
    # If all models fail, return an error message
    raise Exception("All available OpenAI models failed to generate a response. Please check your API key and available models.")
    return response.choices[0].message.content

# API Endpoint

@app.post("/chat")
def chat_handler(request: ChatRequest, db: Session = Depends(get_db)):
    try:
        # Check if OpenAI API key is valid
        api_key = OPENAI_API_KEY
        if api_key and (api_key.startswith("'") or api_key.startswith('"')):
            api_key = api_key.strip("'\"")
            
        if not api_key or api_key == "sk-..." or (api_key.startswith("sk-") and len(api_key) < 30):
            return {
                'answer': "The OpenAI API key is missing or invalid. Please configure a valid API key in the .env file.",
                'conversation_id': request.conversation_id or str(uuid.uuid4()),
                'source': 'error'
            }
        
        # Special case: if the query is about available models, return them
        if "available models" in request.query.lower() or "what models" in request.query.lower():
            try:
                models = openai_client.models.list()
                model_names = [model.id for model in models.data]
                return {
                    'answer': f"Available models with your API key: {', '.join(model_names)}",
                    'conversation_id': request.conversation_id or str(uuid.uuid4()),
                    'source': 'system'
                }
            except Exception as e:
                return {
                    'answer': f"Error listing models: {str(e)}",
                    'conversation_id': request.conversation_id or str(uuid.uuid4()),
                    'source': 'error'
                }
            
        conversation_id = request.conversation_id or str(uuid.uuid4())
        
        chat_history = get_chat_history(db, conversation_id)
        standalone_question = generate_standalone_question(chat_history, request.query)
        
        cache_key = f"rag-cache:{hashlib.sha256(standalone_question.lower().encode()).hexdigest()}"
        cached_response = redis_client.get(cache_key)
        
        if cached_response:
            print("CACHE HIT")
            save_chat_history(db, conversation_id, request.query, cached_response)
            return {'answer': cached_response, 'conversation_id': conversation_id, 'source': 'cache'}

        print("CACHE MISS")
        try:
            query_embedding = get_query_embedding(standalone_question)
            rag_context = get_rag_context(query_embedding)
            try:
                answer = get_llm_response(standalone_question, rag_context)
            except Exception as e:
                print(f"LLM response failed: {e}")
                # Fallback to a simple response using just the context
                answer = f"I encountered an issue with the language model. Here's the relevant information I found:\n\n{rag_context}\n\nThis is raw context data that might help answer your question about: {standalone_question}"
        except Exception as e:
            print(f"Error during RAG processing: {e}")
            return {
                'answer': f"An error occurred while retrieving information: {str(e)}. Please try again later or ask a different question.",
                'conversation_id': conversation_id,
                'source': 'error'
            }

        redis_client.setex(cache_key, 86400, answer)
        save_chat_history(db, conversation_id, request.query, answer)

        return {'answer': answer, 'conversation_id': conversation_id, 'source': 'generated'}

    except Exception as e:
        print(f"Error in handler: {e}")
        return {
            'answer': f"An error occurred while processing your request: {str(e)}",
            'conversation_id': request.conversation_id or str(uuid.uuid4()),
            'source': 'error'
        }
