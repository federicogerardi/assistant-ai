from typing import Dict, Any
from pathlib import Path

AGENTS_CONFIG = {
    "procedure": {
        "name": "Esperto Procedure",
        "icon": "📋",
        "description": "Esperto in procedure aziendali e documentazione tecnica",
        "data_paths": [
            "data/procedure/manuali",
            "data/procedure/linee_guida",
            "data/procedure/standard"
        ],
        "system_prompt": """Sei un esperto di procedure aziendali. 
        Aiuti gli utenti a comprendere e seguire le procedure corrette.
        Rispondi in modo preciso e formale, citando sempre le fonti."""
    },
    "marketing": {
        "name": "Esperto Marketing",
        "icon": "📢",
        "description": "Specialista in marketing e comunicazione",
        "data_paths": [
            "data/marketing/strategie",
            "data/marketing/campagne",
            "data/marketing/analisi"
        ],
        "system_prompt": """Sei un esperto di marketing e comunicazione.
        Aiuti gli utenti con strategie e best practice di marketing.
        Usa un tono professionale ma coinvolgente."""
    },
    "hr": {
        "name": "Esperto Risorse Umane",
        "icon": "👥",
        "description": "Specialista in gestione del personale",
        "data_paths": [
            "data/hr/policies",
            "data/hr/documenti"
        ],
        "system_prompt": """Sei un esperto di risorse umane..."""
    }
}