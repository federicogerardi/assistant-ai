import logging
from pathlib import Path
from typing import List, Dict, Any, Union
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
    def __init__(self, data_paths: Union[str, List[str]], agent_config: Dict[str, Any] = None):
        """Initialize document service with specific agent configuration."""
        self.agent_config = agent_config or {}
        self.data_paths = [data_paths] if isinstance(data_paths, str) else data_paths
        logger.info(f"Initializing DocumentService for {agent_config.get('name', 'default')} with paths: {self.data_paths}")
        
        # Il database sarà nella directory principale 'data'
        first_path = Path(self.data_paths[0])
        root_data_dir = first_path.parents[1]  # Risale di due livelli per arrivare a 'data'
        self.db_path = root_data_dir / "lancedb"
        
        # Initialize components
        self.tokenizer = OpenAITokenizerWrapper()
        self.converter = DocumentConverter()
        self.chunker = HybridChunker(
            tokenizer=self.tokenizer,
            max_tokens=8191,
            merge_peers=True
        )
        self.client = OpenAI()
        
        # Ensure all data directories exist
        for path in self.data_paths:
            Path(path).mkdir(parents=True, exist_ok=True)
        
        # Ensure database directory exists
        self.db_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize database with agent-specific table
        self.db = lancedb.connect(self.db_path)
        # Sostituiamo gli spazi con underscore e rimuoviamo caratteri speciali
        sanitized_name = agent_config.get('name', 'default').lower().replace(' ', '_')
        self.table_name = f"documents_{sanitized_name}"
        
        logger.info(f"DocumentService initialization completed for {self.table_name}")

    def process_documents(self):
        """Process all documents from all configured paths."""
        try:
            # Check if table exists and has data
            if self.table_name in self.db.table_names():
                logger.info(f"{self.table_name} table already exists, skipping processing")
                return

            start_time = time.time()
            processed_chunks = []
            total_documents = 0
            total_chunks = 0
            
            # Process each directory
            files_found = False
            for data_path in self.data_paths:
                path = Path(data_path)
                logger.info(f"Processing documents in: {path}")
                
                # Check if directory contains supported files
                supported_files = list(path.glob("*.pdf")) + list(path.glob("*.txt")) + list(path.glob("*.docx"))
                if not supported_files:
                    logger.info(f"No supported documents found in {path}")
                    continue
                
                files_found = True
                # Process each document in the current path
                for file_path in path.glob("*.*"):
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
            
            if not files_found:
                logger.warning(f"Nessun documento supportato trovato per l'agente {self.agent_config.get('name')}. "
                             f"Percorsi controllati: {', '.join(str(p) for p in self.data_paths)}")
                return
            
            # Store in database
            if processed_chunks:
                logger.info(f"Storing {len(processed_chunks)} chunks in database...")
                self.db.create_table(self.table_name, data=processed_chunks, mode="overwrite")
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
            
            # Check if table exists before searching
            if self.table_name not in self.db.table_names():
                logger.info(f"Table {self.table_name} does not exist. No documents available for this agent.")
                return []
            
            start_time = time.time()
            
            response = self.client.embeddings.create(
                model="text-embedding-3-small",
                input=query
            )
            
            table = self.db.open_table(self.table_name)
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