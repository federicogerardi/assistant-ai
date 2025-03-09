import lancedb
import os
from pathlib import Path

def connect_to_lancedb():
    """Connette al database LanceDB."""
    db_path = Path("data/lancedb")
    db_path.mkdir(parents=True, exist_ok=True)
    return lancedb.connect(str(db_path)) 