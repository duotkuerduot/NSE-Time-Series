# PDF processing
from langchain_community.document_loaders import PyPDFDirectoryLoader
# Splitting
from langchain.text_splitter import RecursiveCharacterTextSplitter
# Embedding
from langchain_community.embeddings import HuggingFaceEmbeddings
# FAISS VectorDB
from langchain_community.vectorstores import FAISS
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

PDFS_FOLDER = r"C:\Users\HomePC\Desktop\LuxDevHQ Internship\QDoctor AI\backend\pdfs"
FAISS_INDEX_PATH = "faiss_index"

def create_and_save_vector_store(pdfs_folder: str = PDFS_FOLDER, index_path: str = FAISS_INDEX_PATH):
    """
    Loads all PDF documents from a specified folder, splits them into chunks,
    creates embeddings, and saves a FAISS vector store locally.

    Args:
        pdfs_folder (str): The path to the folder containing PDF documents.
        index_path (str): The directory where the FAISS index will be saved.
    """
    # Ensure the PDFs folder exists
    if not os.path.exists(pdfs_folder):
        print(f"Error: The folder '{pdfs_folder}' does not exist. Please create it and place your PDF documents inside.")
        return

    # Load all PDF documents from the specified directory
    # PyPDFDirectoryLoader will load all .pdf files in the given directory
    print(f"Loading PDF documents from '{pdfs_folder}'...")
    loader = PyPDFDirectoryLoader(pdfs_folder)
    documents = loader.load()

    if not documents:
        print(f"No PDF documents found in '{pdfs_folder}'. Please ensure there are PDF files in the folder.")
        return

    print(f"Successfully loaded {len(documents)} documents.")

    # Initialize text splitter for chunking documents
    # Chunking helps in breaking down large documents into smaller, manageable pieces
    # for better retrieval and to fit within model context windows.
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,  # Maximum size of each text chunk
        chunk_overlap=200,  # Overlap between chunks to maintain context
        length_function=len, # Function to calculate chunk length (using character count)
        add_start_index=True, # Add metadata about the starting index of each chunk
    )
    chunks = text_splitter.split_documents(documents)
    print(f"Split documents into {len(chunks)} chunks.")


    print("Initializing embeddings model...")
    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    print("Embeddings model initialized.")

    # Create FAISS vector store from the document chunks and embeddings
    # FAISS (Facebook AI Similarity Search) is a library for efficient similarity search
    # and clustering of dense vectors. It's suitable for large datasets.
    print(f"Creating FAISS index with {len(chunks)} chunks...")
    vector_store = FAISS.from_documents(chunks, embeddings)
    print("FAISS index created.")

# Save the FAISS index to the specified path
    if not os.path.exists(index_path):
        os.makedirs(index_path)
        print(f"Created directory '{index_path}' for saving the FAISS index.")
    vector_store.save_local("faiss_index")
    print("FAISS index saved to 'faiss_index'.")
    print("Vector store creation and saving completed successfully.")
    
def load_vector_store(index_path: str = FAISS_INDEX_PATH):
    """
    Loads a FAISS vector store from disk for retrieval.
    Returns the FAISS vector store object.
    """
    print(f"Loading FAISS index from '{index_path}'...")
    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    vector_store = FAISS.load_local(index_path, embeddings, allow_dangerous_deserialization=True)
    print("FAISS index loaded successfully.")
    return vector_store

# Utility: Initialize and save vector store at startup if needed
def initialize_knowledge_base():
    if not os.path.exists(FAISS_INDEX_PATH) or not os.listdir(FAISS_INDEX_PATH):
        print("FAISS index not found. Creating new vector store from PDFs...")
        create_and_save_vector_store()
    else:
        print("FAISS index already exists. Skipping creation.")

# Call this at startup in main.py if you want to ensure the vector store is ready
# initialize_knowledge_base()