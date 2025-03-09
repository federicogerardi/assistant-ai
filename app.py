import streamlit as st
from src.document_service import DocumentService
from src.assistant_service import AssistantService
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Initialize services
@st.cache_resource(show_spinner="Initializing services...")
def init_services():
    """Initialize all services with caching to prevent multiple initializations."""
    logger.info("Initializing services...")
    try:
        doc_service = DocumentService()
        assistant_service = AssistantService(doc_service)
        
        # Process documents only once during initialization
        doc_service.process_documents()
        
        logger.info("Services initialization completed")
        return doc_service, assistant_service
    except Exception as e:
        logger.error(f"Error initializing services: {e}", exc_info=True)
        st.error("Failed to initialize services. Please check the logs.")
        raise

# Configurazione della pagina
st.set_page_config(
    page_title="Document Q&A",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize Streamlit app
st.title("📚 Document Q&A")

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []
if "initialized" not in st.session_state:
    st.session_state.initialized = False

# Initialize services only once
try:
    doc_service, assistant_service = init_services()
    if not st.session_state.initialized:
        st.success("✅ Services initialized successfully!")
        st.session_state.initialized = True
except Exception:
    st.stop()

# Debug settings in sidebar
with st.sidebar:
    st.subheader("🛠️ Debug Settings")
    show_debug = st.checkbox("Mostra informazioni di debug", False)
    
    if show_debug:
        st.write("System Status:")
        st.info("Services: Running")
        st.write("Session State:")
        st.json({k: v for k, v in st.session_state.items() if k != "initialized"})
        st.write("Messaggi nella conversazione:")
        st.write(f"Numero messaggi: {len(st.session_state.messages)}")
        
        # Aggiungiamo statistiche sui documenti
        if hasattr(doc_service, 'db'):
            table = doc_service.db.open_table("documents")
            st.write("Database Stats:")
            st.write(f"- Chunks totali: {len(table)}")

# Chat interface
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Fai una domanda sui documenti..."):
    # Display user message
    with st.chat_message("user"):
        st.markdown(prompt)
    
    st.session_state.messages.append({"role": "user", "content": prompt})

    try:
        # Search documents
        with st.spinner("🔍 Ricerca nei documenti..."):
            results = doc_service.search_documents(prompt)
        
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
                response = assistant_service.get_assistant_response(
                    st.session_state.messages, 
                    context
                )
                st.markdown(response)

        st.session_state.messages.append({"role": "assistant", "content": response})
    
    except Exception as e:
        logger.error(f"Error processing query: {e}", exc_info=True)
        st.error("Si è verificato un errore durante l'elaborazione della richiesta.")

st.caption("Powered by OpenAI GPT-4 & LanceDB") 