import os
import uuid
import time
import hashlib
import redis
from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from openai import OpenAI
import chromadb
from . import models
from .database import engine, get_db

# Create DB tables on startup
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# Clients Initialization
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
CHROMA_COLLECTION_NAME = "enterprise-knowledge-base"

openai_client = OpenAI(api_key=OPENAI_API_KEY)
chroma_client = chromadb.Client()
collection = chroma_client.get_collection(CHROMA_COLLECTION_NAME)

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
    return db.query(models.ChatHistory).filter(models.ChatHistory.conversation_id == conversation_id).order_by(models.ChatHistory.timestamp).all()

def save_chat_history(db: Session, conversation_id, user_query, assistant_response):
    timestamp = int(time.time())
    user_turn = models.ChatHistory(conversation_id=conversation_id, timestamp=timestamp, role='user', content=user_query)
    assistant_turn = models.ChatHistory(conversation_id=conversation_id, timestamp=timestamp + 1, role='assistant', content=assistant_response)
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
    query_result = collection.query(query_embeddings=[query_embedding], n_results=3)
    return "\n\n".join(query_result['documents'][0])

def get_llm_response(query, context):
    prompt = f"You are an expert Q&A assistant. Answer the user's question based only on the provided context. If the answer is not in the context, say you don't have enough information.\n\n<context>\n{context}\n</context>\n\nQuestion: {query}"
    
    response = openai_client.chat.completions.create(
        model="gpt-4-turbo",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content

# API Endpoint

@app.post("/chat")
def chat_handler(request: ChatRequest, db: Session = Depends(get_db)):
    try:
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
        query_embedding = get_query_embedding(standalone_question)
        rag_context = get_rag_context(query_embedding)
        answer = get_llm_response(standalone_question, rag_context)

        redis_client.setex(cache_key, 86400, answer)
        save_chat_history(db, conversation_id, request.query, answer)

        return {'answer': answer, 'conversation_id': conversation_id, 'source': 'generated'}

    except Exception as e:
        print(f"Error in handler: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
