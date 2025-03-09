import streamlit as st
from components.sidebar import render_sidebar
from components.chat import render_chat
from components.dashboard import render_dashboard
from utils.state import init_session_state
from services.document_service import DocumentService
from services.assistant_service import AssistantService
from config.agents import AGENTS_CONFIG
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

@st.cache_resource
def init_agent_services():
    """Initialize services for all agents in read-only mode."""
    services = {}
    for agent_id, config in AGENTS_CONFIG.items():
        # Inizializza i servizi in modalità "read-only"
        doc_service = DocumentService(
            data_paths=config['data_paths'], 
            config=config,
            read_only=True
        )
        assistant_service = AssistantService(doc_service, config)
        services[agent_id] = {
            'doc_service': doc_service,
            'assistant_service': assistant_service
        }
    return services

# Setup della pagina
st.set_page_config(
    page_title="Document Q&A",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inizializzazione dello state
init_session_state()

try:
    # Inizializzazione dei servizi in modalità read-only
    services = init_agent_services()
except Exception as e:
    error_msg = str(e)
    if "Database non inizializzato" in error_msg:
        st.error("Il database non è stato inizializzato. Esegui 'python cli.py refresh' per inizializzare il database.")
    elif "Tabella" in error_msg and "non trovata" in error_msg:
        command = error_msg.split("Esegui '")[1].split("'")[0]
        st.error(f"Tabella non trovata. Esegui questo comando nel terminale:\n\n```bash\n{command}\n```")
    else:
        st.error(f"Errore nell'inizializzazione dei servizi: {error_msg}")
    st.stop()

# Rendering della sidebar con il footer
with st.sidebar:
    selected_agent_id = render_sidebar()
    # Aggiungi uno spazio vuoto per spingere il footer in basso
    st.markdown("<br>" * 5, unsafe_allow_html=True)
    st.caption("Powered by OpenAI GPT-4 & LanceDB")

# Rendering del contenuto principale
if st.session_state.current_page == "Chat":
    render_chat(selected_agent_id, services)
else:
    render_dashboard(services) 