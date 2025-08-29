import streamlit as st
import requests
import os

# --- Configuration ---
# Ideally, this would be read from environment variables or a config file.
# For simplicity, we'll hardcode it here, assuming FastAPI is running on the same network.
# If running Streamlit and FastAPI in separate Docker containers, you'll need to adjust this.
# If running locally with 'docker-compose up', 'fastapi_app' is the service name.
FASTAPI_URL = os.environ.get("FASTAPI_URL", "http://fastapi_app:8000") # Default for Docker Compose
# FASTAPI_URL = "http://localhost:8000" # Uncomment if running FastAPI locally outside Docker

# --- Streamlit UI Setup ---
st.set_page_config(page_title="RAG Chatbot UI", layout="wide")
st.title("Enterprise Knowledge Chatbot")
st.caption("Powered by OpenAI and your internal knowledge base")

# Initialize chat history in session state if it doesn't exist
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Hello! How can I help you with your knowledge base today?"}]

# Display previous messages from chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Handle user input
if prompt := st.chat_input("Ask your question here..."):
    # Add user message to chat history and display it
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Display assistant's response while waiting for API
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        message_placeholder.markdown("Thinking...")

    try:
        # Prepare the payload for the FastAPI endpoint
        payload = {
            "query": prompt,
            "conversation_id": st.session_state.get("conversation_id", None) # Use stored conversation ID if available
        }

        # Send the request to the FastAPI backend
        response = requests.post(f"{FASTAPI_URL}/chat", json=payload)
        response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)

        data = response.json()
        
        # Extract the answer and update conversation ID from the response
        assistant_response = data.get("answer", "Sorry, I couldn't get a response.")
        st.session_state["conversation_id"] = data.get("conversation_id", st.session_state.get("conversation_id", None))

        # Display the assistant's actual response
        message_placeholder.markdown(assistant_response)
        
        # Add assistant's response to chat history
        st.session_state.messages.append({"role": "assistant", "content": assistant_response})

    except requests.exceptions.RequestException as e:
        error_message = f"Error communicating with the backend: {e}"
        st.error(error_message)
        message_placeholder.markdown(f"Error: {error_message}")
        # Add error to chat history as well
        st.session_state.messages.append({"role": "assistant", "content": error_message})
        
    except Exception as e:
        error_message = f"An unexpected error occurred: {e}"
        st.error(error_message)
        message_placeholder.markdown(f"Error: {error_message}")
        # Add error to chat history
        st.session_state.messages.append({"role": "assistant", "content": error_message})


# Optional: Display full chat history on refresh (if needed, but Streamlit state handles this well)
# if st.sidebar.button("Show Full History"):
#     st.sidebar.write(st.session_state.messages)
