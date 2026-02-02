import os
import boto3
import logging
from langchain_aws import BedrockEmbeddings
from langchain_aws.vectorstores import AmazonS3Vectors

# Force INFO logging to see output
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', force=True)

class RagService:
    def __init__(self):
        self.s3_region = os.getenv("AWS_S3_REGION", "us-east-1")
        self.bedrock_region = os.getenv("AWS_DEFAULT_REGION", "us-west-2")
        self.bucket_name = os.getenv("VECTOR_BUCKET_NAME")
        self.index_name = os.getenv("VECTOR_INDEX_NAME")
        
        # Initialize Clients
        self.s3_client = boto3.client(
            's3', 
            region_name=self.s3_region,
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
        )
        self.bedrock_client = boto3.client(
            'bedrock-runtime', 
            region_name=self.bedrock_region,
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
        )
        
        self.embeddings = BedrockEmbeddings(
            client=self.bedrock_client,
            model_id=os.getenv("EMBED_MODEL_ID", "amazon.titan-embed-text-v2:0")
        )
        
        self.vector_store = None

    def initialize_vector_store(self):
        """Initializes the connection to Amazon S3 Vectors."""
        try:
            logging.info(f"Connecting to S3 Vectors: Bucket={self.bucket_name}, Index={self.index_name}")
            
            # According to LangChain docs for AmazonS3Vectors
            self.vector_store = AmazonS3Vectors(
                embedding=self.embeddings,
                vector_bucket_name=self.bucket_name,
                index_name=self.index_name,
                region_name=self.s3_region
            )
            
            logging.info("S3 Vector Store initialized successfully.")
        except Exception as e:
            logging.error(f"Failed to initialize S3 Vector Store: {e}")
            self.vector_store = None

    def query_knowledge_base(self, query: str):
        if not self.vector_store:
            logging.warning("RAG Attempted but Vector Store not initialized.")
            return "Knowledge Base is currently unavailable. Please contact support."
            
        try:
            logging.info(f"--- RAG QUERY START ---")
            logging.info(f"Query: {query}")
            
            # S3 Vectors supports similarity search
            docs = self.vector_store.similarity_search(query, k=3)
            
            logging.info(f"Retrieved {len(docs)} documents.")
            for i, doc in enumerate(docs):
                logging.info(f"Doc {i+1} Content Preview: '{doc.page_content[:200]}'")
                logging.info(f"Doc {i+1} Metadata: {doc.metadata}")
                
            final_response = "\n\n".join([d.page_content for d in docs])
            
            if not final_response.strip():
                logging.warning("RAG retrieved 0 non-empty documents.")
                return "No relevant information found in the Knowledge Base."
                
            logging.info(f"--- RAG QUERY END ---")
            return final_response
            
        except Exception as e:
            logging.error(f"RAG Query Error: {e}", exc_info=True)
            return "Error retrieving information from Knowledge Base."

# Global Instance
rag_service = RagService()
