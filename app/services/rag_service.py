import os
import boto3
import logging
from langchain_aws import BedrockEmbeddings
from langchain_aws.vectorstores import AmazonS3Vectors

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
            return "Knowledge Base is currently unavailable. Please contact support."
            
        try:
            # S3 Vectors supports similarity search
            docs = self.vector_store.similarity_search(query, k=3)
            return "\n\n".join([d.page_content for d in docs])
        except Exception as e:
            logging.error(f"RAG Query Error: {e}")
            return "Error retrieving information from Knowledge Base."

# Global Instance
rag_service = RagService()
