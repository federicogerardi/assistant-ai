import streamlit as st
from src.document_service import DocumentService
from src.assistant_service import AssistantService
from config.agents import AGENTS_CONFIG
import logging
from pathlib import Path
import time  # Aggiungi questo import se non c'è già

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Initialize services for all agents
@st.cache_resource
def init_agent_services():
    """Initialize services for all configured agents."""
    services = {}
    for agent_id, config in AGENTS_CONFIG.items():
        try:
            doc_service = DocumentService(config['data_paths'], config)
            assistant_service = AssistantService(doc_service, config)
            doc_service.process_documents()
            services[agent_id] = {
                'doc_service': doc_service,
                'assistant_service': assistant_service,
                'config': config
            }
        except Exception as e:
            logger.error(f"Error initializing agent {agent_id}: {e}")
    return services

# Configurazione della pagina
st.set_page_config(
    page_title="Document Q&A",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Sidebar for agent selection
with st.sidebar:
    st.title("🤖 Selezione Agente")
    
    # Initialize session state variables if they don't exist
    if 'refresh_state' not in st.session_state:
        st.session_state.refresh_state = 'ready'
    if 'show_toast' not in st.session_state:
        st.session_state.show_toast = False
    
    # Show toast if needed
    if st.session_state.show_toast:
        st.toast("✅ Database ricaricato con successo!", icon="✅")
        st.session_state.show_toast = False
    
    # Refresh button with status
    if st.session_state.refresh_state == 'refreshing':
        st.toast("🔄 Ricaricamento in corso...", icon="🔄")
        st.session_state.refresh_state = 'ready'
        st.session_state.show_toast = True
        st.cache_resource.clear()
        st.rerun()
    
    if st.button("🔄 Ricarica Documenti"):
        st.session_state.refresh_state = 'refreshing'
        st.rerun()
    
    # Agent selection
    agent_options = {f"{config['icon']} {config['name']}": agent_id 
                    for agent_id, config in AGENTS_CONFIG.items()}
    selected_agent_name = st.selectbox(
        "Scegli l'esperto con cui parlare:",
        options=list(agent_options.keys())
    )
    selected_agent_id = agent_options[selected_agent_name]
    
    # Show agent description
    st.info(AGENTS_CONFIG[selected_agent_id]['description'])
    
    # Debug settings
    st.subheader("🛠️ Debug Settings")
    show_debug = st.checkbox("Mostra informazioni di debug", False)

# Initialize services
services = init_agent_services()
current_services = services[selected_agent_id]

# Initialize session state for each agent
if "agent_messages" not in st.session_state:
    st.session_state.agent_messages = {agent_id: [] for agent_id in AGENTS_CONFIG}

# Set success state after initialization
if st.session_state.get('refresh_state') == 'ready':
    st.session_state.just_refreshed = True

# Main chat interface
st.title(f"{AGENTS_CONFIG[selected_agent_id]['icon']} {AGENTS_CONFIG[selected_agent_id]['name']}")

# Display chat history for current agent
for message in st.session_state.agent_messages[selected_agent_id]:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Chat input and processing
if prompt := st.chat_input(f"Chiedi all'esperto {AGENTS_CONFIG[selected_agent_id]['name']}..."):
    # Display user message
    with st.chat_message("user"):
        st.markdown(prompt)
    
    st.session_state.agent_messages[selected_agent_id].append({"role": "user", "content": prompt})

    try:
        # Search documents
        with st.spinner("🔍 Ricerca nei documenti..."):
            results = current_services['doc_service'].search_documents(prompt)
        
        # Display debug information if enabled
        if show_debug and results:
            with st.expander("🔍 Debug: Sezioni rilevanti trovate"):
                for result in results:
                    st.write("---")
                    st.write(f"📄 {Path(result['metadata']['source']).name}")
                    st.caption(f"Score: {result['score']:.4f}")
                    st.write(result['text'])
        
        # Get context from results
        context = "\n\n".join([r['text'] for r in results])

        # Get and display assistant response
        with st.chat_message("assistant"):
            with st.spinner("🤔 Elaborazione risposta..."):
                response = current_services['assistant_service'].get_assistant_response(
                    st.session_state.agent_messages[selected_agent_id], 
                    context
                )
                st.markdown(response)

        st.session_state.agent_messages[selected_agent_id].append({"role": "assistant", "content": response})
    
    except Exception as e:
        logger.error(f"Error processing query: {e}", exc_info=True)
        st.error("Si è verificato un errore durante l'elaborazione della richiesta.")

st.caption("Powered by OpenAI GPT-4 & LanceDB") 