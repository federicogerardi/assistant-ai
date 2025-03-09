import streamlit as st
from src.document_service import DocumentService
from src.assistant_service import AssistantService
from config.agents import AGENTS_CONFIG
import logging
import time
import pandas as pd
import plotly.express as px
from pathlib import Path

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

# Funzioni per la dashboard (spostate dal file status.py)
def get_document_stats(agent_id, config):
    doc_service = DocumentService(config['data_paths'], config)
    stats = {
        'agent_id': agent_id,
        'name': config['name'],
        'icon': config['icon'],
        'total_documents': 0,
        'total_chunks': 0,
        'avg_chunks_per_doc': 0,
        'last_updated': None,
        'documents': []
    }
    
    if doc_service.table_name in doc_service.db.table_names():
        table = doc_service.db.open_table(doc_service.table_name)
        if 'metadata' in table.schema.names:
            df = table.to_pandas()
            if not df.empty:
                # Raccogli statistiche sui documenti
                unique_docs = df['metadata'].apply(lambda x: x['source']).unique()
                stats['total_documents'] = len(unique_docs)
                stats['total_chunks'] = len(df)
                stats['avg_chunks_per_doc'] = stats['total_chunks'] / stats['total_documents'] if stats['total_documents'] > 0 else 0
                
                # Raccogli info sui singoli documenti
                for doc in unique_docs:
                    doc_chunks = df[df['metadata'].apply(lambda x: x['source'] == doc)]
                    doc_metadata = doc_chunks.iloc[0]['metadata']
                    stats['documents'].append({
                        'filename': doc_metadata['filename'],
                        'path': doc_metadata['source'],
                        'chunks': len(doc_chunks),
                        'last_modified': doc_metadata.get('last_modified', 'N/A'),
                        'size': doc_metadata.get('file_size', 0)
                    })
                
                # Trova l'ultimo aggiornamento
                last_modified = max([doc.get('last_modified', '1970-01-01') for doc in stats['documents']])
                stats['last_updated'] = last_modified
    
    return stats

# Sidebar per la navigazione principale
with st.sidebar:
    st.title("🤖 Document Q&A")
    
    # Initialize session state variables if they don't exist
    if 'refresh_state' not in st.session_state:
        st.session_state.refresh_state = 'ready'
    if 'show_toast' not in st.session_state:
        st.session_state.show_toast = False
    if 'current_page' not in st.session_state:
        st.session_state.current_page = "Chat"
    
    # 1. Agent selection
    st.subheader("Scegli l'esperto")
    agent_options = {f"{config['icon']} {config['name']}": agent_id 
                    for agent_id, config in AGENTS_CONFIG.items()}
    selected_agent_name = st.selectbox(
        "Con chi vuoi parlare?",
        options=list(agent_options.keys()),
        label_visibility="collapsed"
    )
    selected_agent_id = agent_options[selected_agent_name]
    
    # 2. Navigation
    st.markdown("---")
    st.subheader("📍 Navigazione")
    page = st.radio("", ["💬 Chat", "📊 Dashboard"], label_visibility="collapsed")
    st.session_state.current_page = "Chat" if "Chat" in page else "Dashboard"
    
    # 3. Refresh button in alert area
    st.markdown("---")
    with st.expander("⚠️ Azioni Amministrative"):
        st.warning("Le seguenti azioni potrebbero influenzare il funzionamento del sistema")
        
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

# Initialize services
services = init_agent_services()

# Main content area
if st.session_state.current_page == "Chat":
    # Chat Interface
    current_services = services[selected_agent_id]
    
    # Initialize session state for each agent if not exists
    if "agent_messages" not in st.session_state:
        st.session_state.agent_messages = {agent_id: [] for agent_id in AGENTS_CONFIG}

    # Main chat interface
    st.title(f"{AGENTS_CONFIG[selected_agent_id]['icon']} {AGENTS_CONFIG[selected_agent_id]['name']}")

    # Display chat history for current agent
    for message in st.session_state.agent_messages[selected_agent_id]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Chat input and processing
    if prompt := st.chat_input(f"Chiedi all'esperto {AGENTS_CONFIG[selected_agent_id]['name']}..."):
        with st.chat_message("user"):
            st.markdown(prompt)
        
        st.session_state.agent_messages[selected_agent_id].append({"role": "user", "content": prompt})

        try:
            with st.spinner("🔍 Ricerca nei documenti..."):
                results = current_services['doc_service'].search_documents(prompt)
            
            context = "\n\n".join([r['text'] for r in results])

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

else:
    # Dashboard Interface
    st.title("📊 Status Dashboard")
    
    tab1, tab2, tab3 = st.tabs(["📑 Overview", "🤖 Agenti", "📈 Statistiche"])
    
    # Tab 1: Overview
    with tab1:
        st.header("📑 Overview Sistema")
        
        # Metriche principali
        col1, col2, col3, col4 = st.columns(4)
        
        total_agents = len(AGENTS_CONFIG)
        total_docs = 0
        total_chunks = 0
        
        # Raccogli statistiche per tutti gli agenti
        all_stats = []
        for agent_id, config in AGENTS_CONFIG.items():
            stats = get_document_stats(agent_id, config)
            all_stats.append(stats)
            total_docs += stats['total_documents']
            total_chunks += stats['total_chunks']
        
        with col1:
            st.metric("Agenti Attivi", total_agents)
        with col2:
            st.metric("Documenti Totali", total_docs)
        with col3:
            st.metric("Chunks Totali", total_chunks)
        with col4:
            avg_chunks = total_chunks / total_docs if total_docs > 0 else 0
            st.metric("Media Chunks/Doc", f"{avg_chunks:.1f}")
        
        # Grafico distribuzione documenti per agente
        st.subheader("Distribuzione Documenti per Agente")
        docs_per_agent = pd.DataFrame([
            {'Agente': f"{stats['icon']} {stats['name']}", 
             'Documenti': stats['total_documents'],
             'Chunks': stats['total_chunks']}
            for stats in all_stats
        ])
        
        fig = px.bar(docs_per_agent, 
                     x='Agente', 
                     y=['Documenti', 'Chunks'],
                     barmode='group',
                     title="Documenti e Chunks per Agente")
        st.plotly_chart(fig, use_container_width=True)
    
    # Tab 2: Dettagli Agenti
    with tab2:
        st.header("🤖 Dettagli Agenti")
        
        for stats in all_stats:
            with st.expander(f"{stats['icon']} {stats['name']}"):
                if stats['total_documents'] > 0:
                    # Mostra documenti in una tabella
                    docs_df = pd.DataFrame(stats['documents'])
                    docs_df['size_mb'] = docs_df['size'] / (1024 * 1024)
                    docs_df = docs_df.rename(columns={
                        'filename': 'Nome File',
                        'chunks': 'Chunks',
                        'last_modified': 'Ultimo Aggiornamento',
                        'size_mb': 'Dimensione (MB)'
                    })
                    st.dataframe(
                        docs_df[['Nome File', 'Chunks', 'Ultimo Aggiornamento', 'Dimensione (MB)']],
                        hide_index=True
                    )
                else:
                    st.info("Nessun documento presente per questo agente")
    
    # Tab 3: Statistiche Avanzate
    with tab3:
        st.header("📈 Statistiche Avanzate")
        
        # Grafico a torta della distribuzione dei chunks
        chunks_data = pd.DataFrame([
            {'Agente': f"{stats['icon']} {stats['name']}", 
             'Chunks': stats['total_chunks']}
            for stats in all_stats if stats['total_chunks'] > 0
        ])
        
        if not chunks_data.empty:
            fig = px.pie(chunks_data, 
                         values='Chunks', 
                         names='Agente',
                         title="Distribuzione Chunks tra Agenti")
            st.plotly_chart(fig, use_container_width=True)
        
        # Timeline aggiornamenti
        st.subheader("Timeline Aggiornamenti")
        timeline_data = []
        for stats in all_stats:
            for doc in stats['documents']:
                # Gestiamo il caso in cui last_modified sia 'N/A'
                if doc['last_modified'] != 'N/A':
                    timeline_data.append({
                        'Agente': f"{stats['icon']} {stats['name']}",
                        'File': doc['filename'],
                        'Data': pd.to_datetime(doc['last_modified'])
                    })
        
        if timeline_data:
            timeline_df = pd.DataFrame(timeline_data)
            timeline_df = timeline_df.sort_values('Data')
            
            fig = px.timeline(timeline_df, 
                             x_start='Data',
                             y='Agente',
                             color='Agente',
                             hover_data=['File'])
            fig.update_layout(showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

# Footer
st.caption("Powered by OpenAI GPT-4 & LanceDB") 