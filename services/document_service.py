import logging
from pathlib import Path
from typing import List, Dict, Any, Union
import lancedb
from openai import OpenAI
from docling.document_converter import DocumentConverter
from docling.chunking import HybridChunker
from services.tokenizer import OpenAITokenizerWrapper
import time
from datetime import datetime, timedelta
import hashlib
import json
import tempfile
from utils.db import connect_to_lancedb

# Configurazione avanzata del logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class DocumentService:
    def __init__(self, data_paths: List[str], config: dict, read_only: bool = False):
        self.data_paths = data_paths
        self.config = config
        
        # Usa l'ID esplicito dalla config
        agent_id = config.get('id', '').lower()
        self.table_name = f"docs_{agent_id}"
        
        self.db = connect_to_lancedb()
        self.client = OpenAI()
        
        # Se in modalità read-only, verifica che il DB sia inizializzato
        if read_only:
            if not self.db.table_names():
                # Crea una tabella vuota se non esiste il DB
                logger.info(f"Creazione tabella vuota {self.table_name}")
                self._create_empty_table()
            elif self.table_name not in self.db.table_names():
                # Crea una tabella vuota se non esiste per questo agente
                logger.info(f"Creazione tabella vuota {self.table_name}")
                self._create_empty_table()
            self.table = self.db.open_table(self.table_name)
        else:
            # Modalità normale con processing dei documenti
            self.converter = DocumentConverter()
            self.chunker = HybridChunker()
        
        # Initialize components
        self.tokenizer = OpenAITokenizerWrapper()
        self.chunker = HybridChunker(
            tokenizer=self.tokenizer,
            max_tokens=8191,
            merge_peers=True
        )
        
        # Ensure all data directories exist
        for path in self.data_paths:
            Path(path).mkdir(parents=True, exist_ok=True)
        
        # Ensure database directory exists
        self.db_path = Path(self.data_paths[0]).parents[1] / "lancedb"
        self.db_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize database with agent-specific table
        self.db = lancedb.connect(self.db_path)
        
        logger.info(f"DocumentService initialization completed for {self.table_name}")

    def _create_empty_table(self):
        """Crea una tabella vuota con la struttura corretta."""
        empty_data = [{
            "text": "",
            "vector": [0.0] * 1536,  # dimensione standard per embedding OpenAI
            "metadata": {
                "source": "",
                "filename": "",
                "page_numbers": [],
                "last_modified": "",
                "file_hash": "",
                "file_size": 0
            }
        }]
        self.db.create_table(self.table_name, data=empty_data)
        table = self.db.open_table(self.table_name)
        # Rimuovi il record vuoto iniziale
        table.delete("text = ''")
        logger.info(f"Tabella vuota {self.table_name} creata con successo")

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
                logger.warning(f"Nessun documento supportato trovato per l'agente {self.config.get('name')}. "
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
            
            table = self.db.open_table(self.table_name)
            df = table.to_pandas()
            if df.empty:
                logger.info(f"Nessun documento trovato per l'agente {self.config.get('name')}")
                return []
            
            start_time = time.time()
            
            response = self.client.embeddings.create(
                model="text-embedding-3-small",
                input=query
            )
            
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
        """Aggiunge nuovi documenti usando Batch API."""
        try:
            if not file_paths:
                logger.info("Nessun nuovo documento da aggiungere")
                return []

            start_time = time.time()
            processed_chunks = []
            
            # Configurazione ottimizzata
            POLLING_INTERVAL = 10  # invariato
            MAX_WAIT_TIME = 30 * 60  # invariato
            MIN_CHUNKS_FOR_BATCH = 5  # nuovo: minimo numero di chunks per usare batch
            
            for file_path in file_paths:
                doc_start_time = time.time()
                logger.info(f"Processing document: {file_path}")
                
                # Convert document
                result = self.converter.convert(str(file_path))
                if not result.document:
                    logger.error(f"Failed to convert document: {file_path}")
                    continue
                
                # Apply chunking
                chunks = list(self.chunker.chunk(dl_doc=result.document))
                chunk_count = len(chunks)
                logger.info(f"Created {chunk_count} chunks from {file_path}")
                
                # Decisione se usare batch o chiamate sincrone
                if chunk_count < MIN_CHUNKS_FOR_BATCH:
                    logger.info(f"Processing {chunk_count} chunks synchronously (below batch threshold)")
                    # Processo sincrono per pochi chunks
                    chunk_embeddings = []
                    for chunk in chunks:
                        response = self.client.embeddings.create(
                            model="text-embedding-3-small",
                            input=chunk.text
                        )
                        chunk_embeddings.append(response.data[0].embedding)
                        logger.debug(f"Processed chunk synchronously")
                else:
                    # Processo batch per molti chunks
                    logger.info(f"Processing {chunk_count} chunks via batch API")
                    # Prepare batch file
                    batch_requests = []
                    for i, chunk in enumerate(chunks):
                        batch_requests.append({
                            "custom_id": f"{file_path}_{i}",
                            "method": "POST",
                            "url": "/v1/embeddings",
                            "body": {
                                "model": "text-embedding-3-small",
                                "input": chunk.text
                            }
                        })
                    
                    # Create temporary JSONL file
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
                        for request in batch_requests:
                            f.write(json.dumps(request) + '\n')
                    
                    try:
                        # Upload batch file
                        logger.info("Uploading batch file...")
                        with open(f.name, 'rb') as file:
                            batch_file = self.client.files.create(
                                file=file,
                                purpose="batch"
                            )
                        
                        # Create batch
                        logger.info("Creating batch job...")
                        batch = self.client.batches.create(
                            input_file_id=batch_file.id,
                            endpoint="/v1/embeddings",
                            completion_window="24h"
                        )
                        
                        logger.info(f"Created batch {batch.id} for {file_path}")
                        
                        # Wait for batch completion with timeout
                        timeout_time = datetime.now() + timedelta(seconds=MAX_WAIT_TIME)
                        last_progress = 0
                        
                        while datetime.now() < timeout_time:
                            batch_status = self.client.batches.retrieve(batch.id)
                            
                            # Calcola e mostra il progresso
                            if batch_status.request_counts.total > 0:
                                progress = (batch_status.request_counts.completed / 
                                          batch_status.request_counts.total) * 100
                                if progress > last_progress + 20:  # Log ogni 20% invece di 5%
                                    logger.info(f"Batch progress: {progress:.1f}% completed")
                                    last_progress = progress
                            
                            if batch_status.status == "completed":
                                logger.info("Batch completed successfully!")
                                break
                            elif batch_status.status in ["failed", "expired", "cancelled"]:
                                raise Exception(f"Batch failed with status: {batch_status.status}")
                            
                            time.sleep(POLLING_INTERVAL)
                        else:
                            raise Exception(f"Batch processing timed out after {MAX_WAIT_TIME/60:.1f} minutes")
                        
                        # Get results
                        logger.info("Retrieving batch results...")
                        output = self.client.files.content(batch_status.output_file_id)
                        results = [json.loads(line) for line in output.text.splitlines()]
                        
                        # Process results
                        successful_chunks = 0
                        for chunk, result in zip(chunks, results):
                            if result.get("error") is None:
                                embedding = result["response"]["body"]["data"][0]["embedding"]
                                processed_chunks.append({
                                    "text": chunk.text,
                                    "vector": embedding,
                                    "metadata": {
                                        "source": str(file_path),
                                        "filename": Path(file_path).name,
                                        "page_numbers": [
                                            page_no for page_no in sorted(
                                                set(prov.page_no for item in chunk.meta.doc_items for prov in item.prov)
                                            )
                                        ] if hasattr(chunk.meta, 'doc_items') else None,
                                        "last_modified": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat(),
                                        "file_hash": calculate_file_hash(file_path),
                                        "file_size": file_path.stat().st_size
                                    }
                                })
                                successful_chunks += 1
                        
                        logger.info(f"Successfully processed {successful_chunks}/{len(chunks)} chunks")
                        
                    finally:
                        # Cleanup
                        Path(f.name).unlink()
                        logger.debug("Cleaned up temporary files")
                    
                    doc_process_time = time.time() - doc_start_time
                    logger.info(f"Document processing completed in {doc_process_time:.2f} seconds")

            # Add to database
            if processed_chunks:
                if self.table_name in self.db.table_names():
                    table = self.db.open_table(self.table_name)
                    table.add(processed_chunks)
                else:
                    self.db.create_table(self.table_name, data=processed_chunks)
                
                total_time = time.time() - start_time
                logger.info(f"Total processing time: {total_time:.2f} seconds for {len(processed_chunks)} chunks")
            
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