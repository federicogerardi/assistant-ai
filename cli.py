import click
import logging
from pathlib import Path
import hashlib
from datetime import datetime
from services.document_service import DocumentService
from config.agents import AGENTS_CONFIG

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def calculate_file_hash(file_path: Path) -> str:
    """Calcola l'hash MD5 di un file."""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def get_file_info(file_path: Path) -> dict:
    """Ottiene informazioni sul file."""
    return {
        'hash': calculate_file_hash(file_path),
        'mtime': datetime.fromtimestamp(file_path.stat().st_mtime).isoformat(),
        'size': file_path.stat().st_size
    }

@click.group()
def cli():
    """CLI per la gestione dei documenti degli agenti."""
    pass

@cli.command()
@click.option('--agent', '-a', help='ID dell\'agente da aggiornare (es. procedure, marketing, hr)')
@click.option('--force', '-f', is_flag=True, help='Forza il refresh completo ignorando lo stato precedente')
def refresh(agent, force):
    """Aggiorna incrementalmente i documenti per uno o tutti gli agenti."""
    try:
        if agent:
            if agent not in AGENTS_CONFIG:
                logger.error(f"Agente '{agent}' non trovato. Agenti disponibili: {', '.join(AGENTS_CONFIG.keys())}")
                return
            agents_to_refresh = {agent: AGENTS_CONFIG[agent]}
        else:
            agents_to_refresh = AGENTS_CONFIG
            
        for agent_id, config in agents_to_refresh.items():
            # Assicurati che l'id sia presente nella config
            config['id'] = agent_id
            logger.info(f"Aggiornamento documenti per {config['name']}...")
            doc_service = DocumentService(config['data_paths'], config)
            
            # Verifica se ci sono file da processare
            files_to_process = []
            for data_path in config['data_paths']:
                path = Path(data_path)
                logger.info(f"Cercando documenti in: {path}")
                if path.exists():
                    logger.info(f"Directory {path} esiste")
                    for file_path in path.glob("*.*"):
                        logger.info(f"Trovato file: {file_path}")
                        if file_path.suffix.lower() in ['.pdf', '.txt', '.docx']:
                            logger.info(f"File supportato trovato: {file_path}")
                            files_to_process.append(file_path)
                        else:
                            logger.info(f"File non supportato: {file_path}")
                else:
                    logger.info(f"Directory {path} non esiste")
            
            if not files_to_process:
                logger.info(f"Nessun documento trovato per {config['name']}")
                continue
                
            # Se è force o la tabella non esiste, processa tutto
            if force or doc_service.table_name not in doc_service.db.table_names():
                if force:
                    logger.info("Modalità force: riprocessamento completo...")
                    if doc_service.table_name in doc_service.db.table_names():
                        doc_service.db.drop_table(doc_service.table_name)
                else:
                    logger.info(f"Creazione nuova tabella: {doc_service.table_name}")
                doc_service.process_documents()
                continue
            
            # Modalità incrementale
            table = doc_service.db.open_table(doc_service.table_name)
            existing_files = {}
            existing_records = {}
            
            if 'metadata' in table.schema.names:
                df = table.to_pandas()
                if not df.empty and 'metadata' in df.columns:
                    logger.info(f"Trovati {len(df)} record nel database")
                    for _, row in df.iterrows():
                        metadata = row.metadata
                        source = metadata['source']
                        if source not in existing_records:
                            existing_records[source] = []
                        existing_records[source].append(row.to_dict())
                        
                        # Mantieni i metadata per il confronto
                        existing_files[source] = {
                            'hash': metadata.get('file_hash', ''),
                            'mtime': metadata.get('last_modified', ''),
                            'size': metadata.get('file_size', 0)
                        }
                    logger.info(f"File esistenti nel DB: {list(existing_files.keys())}")
            
            new_files = []
            modified_files = []
            
            for file_path in files_to_process:
                file_str = str(file_path)
                if file_str not in existing_files:
                    logger.info(f"Nuovo file trovato: {file_path}")
                    new_files.append(file_path)
                else:
                    # Se il file esiste, controlla se è stato modificato
                    current_hash = calculate_file_hash(file_path)
                    current_mtime = datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
                    current_size = file_path.stat().st_size
                    
                    stored_info = existing_files[file_str]
                    if not all(stored_info.values()):
                        # Se mancano i metadata, aggiorna solo i metadata mantenendo gli embedding esistenti
                        logger.info(f"Aggiornamento metadata per file esistente: {file_path}")
                        records_to_update = existing_records[file_str]
                        for record in records_to_update:
                            record['metadata'].update({
                                'file_hash': current_hash,
                                'last_modified': current_mtime,
                                'file_size': current_size
                            })
                    elif (current_hash != stored_info['hash'] or 
                          current_mtime != stored_info['mtime'] or 
                          current_size != stored_info['size']):
                        logger.info(f"File modificato rilevato: {file_path}")
                        modified_files.append(file_path)
            
            if new_files or modified_files:
                if new_files:
                    logger.info(f"Trovati {len(new_files)} nuovi documenti da processare")
                if modified_files:
                    logger.info(f"Trovati {len(modified_files)} documenti modificati da aggiornare")
                
                # Processa solo i file nuovi e modificati
                doc_service.add_documents(new_files + modified_files, existing_records)
            else:
                logger.info(f"Nessun nuovo documento o modifica da processare per {config['name']}")
            
        logger.info("Operazione completata con successo!")
        
    except Exception as e:
        logger.error(f"Errore durante l'aggiornamento: {str(e)}", exc_info=True)

if __name__ == '__main__':
    cli() 