# main.py
import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langchain_groq import ChatGroq
from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, AIMessage # Use langchain_core.messages for clarity

# Import functions and constants from your knowledge_base.py
from knowledge_base import initialize_knowledge_base, load_vector_store, FAISS_INDEX_PATH

# Load environment variables
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY is not set. Please add it to your .env file.")

# Initialize FastAPI app
app = FastAPI(title="Doctor's AI Agent Backend")

# Configure CORS for frontend communication
origins = [
    "http://localhost:5173", # For development frontend
    "http://127.0.0.1:5173", # For development frontend
    # Add other frontend origins if deployed
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global variables for RAG components
vector_store = None
rag_chain = None

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default_session" # Kept for potential future session management

class ChatResponse(BaseModel):
    response: str
    context_sources: list[str] = []

@app.on_event("startup")
async def startup_event():
    """
    Initializes the FAISS index (creating it if it doesn't exist)
    and sets up the RAG chain when the FastAPI app starts.
    """
    global vector_store, rag_chain

    print("Application starting up...")

    # Step 1: Ensure the knowledge base (FAISS index) is ready
    # This function will create the index if it doesn't exist or is empty
    initialize_knowledge_base()

    # Step 2: Load the FAISS index for use in the application
    try:
        vector_store = load_vector_store(FAISS_INDEX_PATH)
        print("FAISS index successfully loaded for application use.")
    except Exception as e:
        print(f"Error loading FAISS index: {e}")
        raise RuntimeError("Failed to load FAISS index. Cannot start application without knowledge base.")

    # Initialize Groq LLM
    llm = ChatGroq(
        api_key=GROQ_API_KEY,
        model_name="llama3-8b-8192", # Using a smaller, faster model suitable for Q&A
        temperature=0, # Set temperature to 0 for factual, less creative answers
    )
    print(f"Groq LLM initialized with model: {llm.model_name}")

    # Define the prompt for the LLM
    # This prompt instructs the LLM on how to use the retrieved context for doctors
    prompt = ChatPromptTemplate.from_template("""
    You are an AI assistant designed for healthcare professionals in Kenya. Your primary goal is to provide accurate and concise answers
    to medical questions *strictly based on the provided local medical documents*.
    
    If the information required to answer the question is not explicitly present in the provided context,
    state clearly, "I cannot find specific information on that in the provided documents." Do not invent information.
    
    Focus on being direct and factual. Avoid conversational filler.
    
    Context: {context}
    
    Question: {input}
    """)

    # Create a retriever from the vector store
    # This will search the FAISS index for relevant chunks based on the query.
    retriever = vector_store.as_retriever(search_kwargs={"k": 5}) # Retrieve 5 top relevant documents

    # Create a document combining chain
    # This chain takes the retrieved documents and the user's question and formats them for the LLM.
    document_chain = create_stuff_documents_chain(llm, prompt)

    # Create the full retrieval chain
    # This chain orchestrates the retrieval of documents and then passes them to the LLM for generation.
    rag_chain = create_retrieval_chain(retriever, document_chain)
    print("RAG chain initialized successfully.")
    print("Application startup complete. Ready to receive questions.")


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    Handles incoming chat messages from the frontend, performs RAG using FAISS and Groq,
    and returns a structured response including the answer and source documents.
    """
    if rag_chain is None:
        raise HTTPException(status_code=503, detail="AI agent not initialized. Please ensure the backend started correctly.")

    user_message = request.message
    print(f"Received question: {user_message}")

    try:
        # Invoke the RAG chain with the user's question
        # The chain will automatically handle retrieval and answer generation
        response = await rag_chain.ainvoke({"input": user_message})

        ai_response_content = response.get("answer", "I'm sorry, I couldn't process that request or find an answer in the provided documents.")
        
        # Extract sources from the retrieved documents
        # The 'context' key in the response contains the list of Document objects
        context_docs = response.get("context", [])
        context_sources = []
        for doc in context_docs:
            source_path = doc.metadata.get('source', 'Unknown Source')
            # Extract just the filename for cleaner display, if the source is a file path
            if isinstance(source_path, str) and os.path.isfile(source_path):
                context_sources.append(os.path.basename(source_path))
            else:
                context_sources.append(source_path)
        
        # Deduplicate sources for a cleaner list
        context_sources = list(set(context_sources))

        print(f"Generated answer: {ai_response_content}")
        print(f"Context sources: {context_sources}")

        return ChatResponse(response=ai_response_content, context_sources=context_sources)

    except Exception as e:
        print(f"Error processing chat message: {e}")
        raise HTTPException(status_code=500, detail="An internal server error occurred while processing your request. Please try again.")

# Basic GET endpoint for health check or initial browser access
@app.get("/health")
async def health_check():
    return {"status": "ok", "message": "AI Agent is running and healthy."}

# Add a root endpoint for easy backend testing
@app.get("/")
async def root():
    return {"message": "QDoctor AI backend is running. Use /health for status and /chat for queries."}

if __name__ == "__main__":
    # Ensure FAISS index is initialized before running the app
    from knowledge_base import initialize_knowledge_base
    initialize_knowledge_base()
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)