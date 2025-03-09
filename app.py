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

# Aggiungiamo cache per i servizi
@st.cache_resource
def init_agent_services():
    """Initialize services for all agents."""
    services = {}
    for agent_id, config in AGENTS_CONFIG.items():
        doc_service = DocumentService(config['data_paths'], config)
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

# Inizializzazione dei servizi
services = init_agent_services()

# Rendering della sidebar
selected_agent_id = render_sidebar()

# Rendering del contenuto principale
if st.session_state.current_page == "Chat":
    render_chat(selected_agent_id, services)
else:
    render_dashboard(services)

# Footer
st.caption("Powered by OpenAI GPT-4 & LanceDB") 