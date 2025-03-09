import os
import hashlib
import json
from pathlib import Path
import lancedb
from datetime import datetime

class VectorStore:
    def __init__(self, data_dir="data", db_path="data/vector_db"):
        self.data_dir = Path(data_dir)
        self.db_path = Path(db_path)
        self.processed_dir = self.data_dir / "processed"
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.mkdir(parents=True, exist_ok=True)
        
        # File per tenere traccia degli hash dei documenti
        self.hash_file = self.processed_dir / "file_hashes.json"
        self.db = lancedb.connect(self.db_path)

    def _calculate_file_hash(self, filepath):
        """Calcola l'hash MD5 di un file."""
        hasher = hashlib.md5()
        with open(filepath, 'rb') as f:
            buf = f.read(65536)
            while len(buf) > 0:
                hasher.update(buf)
                buf = f.read(65536)
        return hasher.hexdigest()

    def _load_file_hashes(self):
        """Carica gli hash dei file precedentemente processati."""
        if self.hash_file.exists():
            with open(self.hash_file, 'r') as f:
                return json.load(f)
        return {}

    def _save_file_hashes(self, hashes):
        """Salva gli hash dei file processati."""
        with open(self.hash_file, 'w') as f:
            json.dump(hashes, f, indent=2)

    def check_files_changed(self):
        """Controlla se ci sono file nuovi o modificati nella cartella data."""
        current_hashes = {}
        changed_files = []
        
        # Calcola gli hash dei file attuali
        for file in self.data_dir.glob('**/*.*'):
            if file.is_file() and not str(file).startswith(str(self.processed_dir)):
                current_hash = self._calculate_file_hash(file)
                current_hashes[str(file)] = {
                    'hash': current_hash,
                    'last_processed': datetime.now().isoformat()
                }

        # Carica gli hash precedenti
        previous_hashes = self._load_file_hashes()

        # Confronta gli hash
        for file_path, current_info in current_hashes.items():
            if (file_path not in previous_hashes or 
                previous_hashes[file_path]['hash'] != current_info['hash']):
                changed_files.append(Path(file_path))

        # Salva i nuovi hash
        self._save_file_hashes(current_hashes)

        return changed_files