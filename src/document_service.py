import logging
from pathlib import Path
from typing import List, Dict, Any
import lancedb
from openai import OpenAI
from docling.document_converter import DocumentConverter
from docling.chunking import HybridChunker
from utils.tokenizer import OpenAITokenizerWrapper
import time

# Configurazione avanzata del logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class DocumentService:
    def __init__(self, data_dir: str = "data"):
        """Initialize document service with all necessary components."""
        logger.info(f"Initializing DocumentService with data_dir: {data_dir}")
        self.data_dir = Path(data_dir)
        self.db_path = self.data_dir / "lancedb"
        self.documents_dir = self.data_dir / "documents"
        
        # Initialize components
        logger.info("Initializing components...")
        self.tokenizer = OpenAITokenizerWrapper()
        self.converter = DocumentConverter()
        self.chunker = HybridChunker(
            tokenizer=self.tokenizer,
            max_tokens=8191,
            merge_peers=True
        )
        self.client = OpenAI()
        
        # Ensure directories exist
        logger.info("Creating necessary directories...")
        self.documents_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize database
        logger.info(f"Connecting to LanceDB at {self.db_path}")
        self.db = lancedb.connect(self.db_path)
        logger.info("DocumentService initialization completed")

    def process_documents(self):
        """Process all documents in the documents directory."""
        try:
            # Check if table exists and has data
            if "documents" in self.db.table_names():
                logger.info("Documents table already exists, skipping processing")
                return

            start_time = time.time()
            processed_chunks = []
            total_documents = 0
            total_chunks = 0
            
            # Process each document
            logger.info("Starting document processing...")
            for file_path in self.documents_dir.glob("*.*"):
                if file_path.suffix.lower() not in ['.pdf', '.txt', '.docx']:
                    logger.warning(f"Skipping unsupported file type: {file_path}")
                    continue
                    
                doc_start_time = time.time()
                logger.info(f"Processing document: {file_path}")
                
                # Convert document
                result = self.converter.convert(str(file_path))
                if not result.document:
                    logger.error(f"Failed to convert document: {file_path}")
                    continue
                
                # Apply chunking
                chunks = list(self.chunker.chunk(dl_doc=result.document))
                logger.info(f"Created {len(chunks)} chunks from {file_path}")
                
                # Get embeddings and prepare for storage
                chunk_count = 0
                for chunk in chunks:
                    response = self.client.embeddings.create(
                        model="text-embedding-3-small",
                        input=chunk.text
                    )
                    
                    processed_chunks.append({
                        "text": chunk.text,
                        "vector": response.data[0].embedding,
                        "metadata": {
                            "source": str(file_path),
                            "filename": Path(file_path).name,
                            "page_numbers": [
                                page_no
                                for page_no in sorted(
                                    set(
                                        prov.page_no
                                        for item in chunk.meta.doc_items
                                        for prov in item.prov
                                    )
                                )
                            ] if hasattr(chunk.meta, 'doc_items') else None
                        }
                    })
                    chunk_count += 1
                
                doc_process_time = time.time() - doc_start_time
                logger.info(f"Processed {chunk_count} chunks from {file_path} in {doc_process_time:.2f} seconds")
                total_documents += 1
                total_chunks += chunk_count
            
            # Store in database
            if processed_chunks:
                logger.info(f"Storing {len(processed_chunks)} chunks in database...")
                self.db.create_table("documents", data=processed_chunks, mode="overwrite")
                total_time = time.time() - start_time
                logger.info(f"Processing completed: {total_documents} documents, {total_chunks} chunks in {total_time:.2f} seconds")
            else:
                logger.warning("No chunks were processed")
                
        except Exception as e:
            logger.error(f"Error processing documents: {str(e)}", exc_info=True)

    def search_documents(self, query: str, num_results: int = 3) -> List[Dict[str, Any]]:
        """Search for relevant documents."""
        try:
            logger.info(f"Searching documents for query: {query[:50]}...")
            start_time = time.time()
            
            response = self.client.embeddings.create(
                model="text-embedding-3-small",
                input=query
            )
            
            table = self.db.open_table("documents")
            results = table.search(response.data[0].embedding).limit(num_results).to_pandas()
            
            search_time = time.time() - start_time
            logger.info(f"Found {len(results)} results in {search_time:.2f} seconds")
            
            return [
                {
                    'text': row['text'],
                    'metadata': row['metadata'],
                    'score': row['_distance']
                }
                for _, row in results.iterrows()
            ]
            
        except Exception as e:
            logger.error(f"Error searching documents: {str(e)}", exc_info=True)
            return []

    def get_chat_response(self, messages: List[Dict[str, str]], context: str) -> str:
        """Get chat response from OpenAI."""
        from src.assistant_service import AssistantService  # Import locale per evitare cicli
        
        assistant = AssistantService(self)  # Passiamo l'istanza di DocumentService
        return assistant.get_assistant_response(messages, context) 