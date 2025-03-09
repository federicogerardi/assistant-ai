import logging
from pathlib import Path
from typing import List, Dict, Any, Union
import lancedb
from openai import OpenAI
from docling.document_converter import DocumentConverter
from docling.chunking import HybridChunker
from utils.tokenizer import OpenAITokenizerWrapper
import time
from datetime import datetime
import hashlib

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
            start_time = time.time()
            processed_chunks = []
            total_documents = 0
            total_chunks = 0
            
            # Process each directory
            files_found = False
            files_to_process = []
            
            # Raccogli tutti i file da processare
            for data_path in self.data_paths:
                path = Path(data_path)
                logger.info(f"Processing documents in: {path}")
                
                # Check if directory contains supported files
                for file_path in path.glob("*.*"):
                    if file_path.suffix.lower() in ['.pdf', '.txt', '.docx']:
                        files_to_process.append(file_path)
                        files_found = True
            
            if not files_found:
                logger.warning(f"Nessun documento supportato trovato per l'agente {self.agent_config.get('name')}. "
                             f"Percorsi controllati: {', '.join(str(p) for p in self.data_paths)}")
                return
            
            # Se la tabella esiste, usa la logica incrementale
            if self.table_name in self.db.table_names():
                logger.info(f"Tabella {self.table_name} esistente, verifico aggiornamenti...")
                table = self.db.open_table(self.table_name)
                existing_files = {}
                existing_records = {}
                
                if 'metadata' in table.schema.names:
                    df = table.to_pandas()
                    if not df.empty and 'metadata' in df.columns:
                        for _, row in df.iterrows():
                            metadata = row.metadata
                            source = metadata['source']
                            if source not in existing_records:
                                existing_records[source] = []
                            existing_records[source].append(row.to_dict())
                            
                            existing_files[source] = {
                                'hash': metadata.get('file_hash', ''),
                                'mtime': metadata.get('last_modified', ''),
                                'size': metadata.get('file_size', 0)
                            }
                
                # Processa solo i file nuovi o modificati
                new_or_modified = []
                for file_path in files_to_process:
                    file_str = str(file_path)
                    if file_str not in existing_files:
                        new_or_modified.append(file_path)
                        continue
                    
                    current_hash = calculate_file_hash(file_path)
                    current_mtime = datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
                    current_size = file_path.stat().st_size
                    
                    stored_info = existing_files[file_str]
                    if not all(stored_info.values()) or (
                        current_hash != stored_info['hash'] or 
                        current_mtime != stored_info['mtime'] or 
                        current_size != stored_info['size']
                    ):
                        new_or_modified.append(file_path)
                
                if new_or_modified:
                    logger.info(f"Trovati {len(new_or_modified)} file da aggiornare")
                    self.add_documents(new_or_modified, existing_records)
                else:
                    logger.info("Nessun aggiornamento necessario")
                
                return
            
            # Se la tabella non esiste, processa tutto
            logger.info("Creazione nuova tabella...")
            self.add_documents(files_to_process)
                
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

    def add_documents(self, file_paths: List[Path], existing_records: Dict[str, List[Dict]] = None):
        """Aggiunge nuovi documenti alla tabella esistente."""
        try:
            if not file_paths:
                logger.info("Nessun nuovo documento da aggiungere")
                return []

            start_time = time.time()
            processed_chunks = []
            total_documents = 0
            total_chunks = 0
            
            # Process each document
            for file_path in file_paths:
                doc_start_time = time.time()
                file_str = str(file_path)
                logger.info(f"Processing document: {file_path}")
                
                # Se abbiamo record esistenti per questo file e non è stato modificato
                if existing_records and file_str in existing_records:
                    logger.info(f"Riutilizzo record esistenti per: {file_path}")
                    processed_chunks.extend(existing_records[file_str])
                    doc_process_time = time.time() - doc_start_time
                    logger.info(f"Riutilizzati {len(existing_records[file_str])} chunks da {file_path} in {doc_process_time:.2f} seconds")
                    total_documents += 1
                    total_chunks += len(existing_records[file_str])
                    continue
                
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
                            ] if hasattr(chunk.meta, 'doc_items') else None,
                            "last_modified": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat(),
                            "file_hash": calculate_file_hash(file_path),
                            "file_size": file_path.stat().st_size
                        }
                    })
                    chunk_count += 1
                
                doc_process_time = time.time() - doc_start_time
                logger.info(f"Processed {chunk_count} chunks from {file_path} in {doc_process_time:.2f} seconds")
                total_documents += 1
                total_chunks += chunk_count

            # Add to existing table
            if processed_chunks:
                if self.table_name in self.db.table_names():
                    table = self.db.open_table(self.table_name)
                    table.add(processed_chunks)
                else:
                    self.db.create_table(self.table_name, data=processed_chunks)
                
                total_time = time.time() - start_time
                logger.info(f"Added {total_documents} documents, {total_chunks} chunks in {total_time:.2f} seconds")
            
            return processed_chunks
            
        except Exception as e:
            logger.error(f"Error adding documents: {str(e)}", exc_info=True)
            return []

    def update_metadata(self, records: List[Dict], file_paths: List[Path]) -> List[Dict]:
        """Aggiorna i metadata dei record esistenti."""
        try:
            updated_records = []
            for record in records:
                file_path = Path(record['metadata']['source'])
                if file_path in file_paths:
                    record['metadata'].update({
                        "last_modified": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat(),
                        "file_hash": calculate_file_hash(file_path),
                        "file_size": file_path.stat().st_size
                    })
                updated_records.append(record)
            return updated_records
        except Exception as e:
            logger.error(f"Error updating metadata: {str(e)}", exc_info=True)
            return records

def calculate_file_hash(file_path: Path) -> str:
    """Calcola l'hash MD5 di un file."""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest() 