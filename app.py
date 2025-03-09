import streamlit as st
from src.document_service import DocumentService
from src.assistant_service import AssistantService
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize services
@st.cache_resource
def init_services():
    doc_service = DocumentService()
    assistant_service = AssistantService(doc_service)
    return doc_service, assistant_service

# Configurazione della pagina
st.set_page_config(
    page_title="Document Q&A",
    page_icon="📚",
    layout="wide"
)

# Initialize Streamlit app
st.title("📚 Document Q&A")

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []

# Initialize services and process documents at startup
doc_service, assistant_service = init_services()
doc_service.process_documents()

# Debug settings in sidebar
with st.sidebar:
    st.subheader("🛠️ Debug Settings")
    show_debug = st.checkbox("Mostra informazioni di debug", False)
    
    if show_debug:
        st.write("Session State:")
        st.json(dict(st.session_state))
        st.write("Messaggi nella conversazione:")
        st.write(f"Numero messaggi: {len(st.session_state.messages)}")

# Chat interface
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Fai una domanda sui documenti..."):
    # Display user message
    with st.chat_message("user"):
        st.markdown(prompt)
    
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Search documents
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
        with st.spinner("Elaborazione risposta..."):
            response = assistant_service.get_assistant_response(
                st.session_state.messages, 
                context
            )
            st.markdown(response)

    st.session_state.messages.append({"role": "assistant", "content": response})

st.caption("Powered by OpenAI GPT-4 & LanceDB") 