import streamlit as st
import pandas as pd
from config.agents import AGENTS_CONFIG
from services.stats import get_document_stats

def render_agents_details(services):
    """Render the agents details tab of the dashboard."""
    st.header("🤖 Dettagli Agenti")
    
    # Raccogli statistiche per tutti gli agenti
    all_stats = []
    for agent_id, config in AGENTS_CONFIG.items():
        stats = get_document_stats(agent_id, config, services[agent_id]['doc_service'])
        all_stats.append(stats)
    
    # Mostra dettagli per ogni agente
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
                
                # Formatta le colonne numeriche
                docs_df['Dimensione (MB)'] = docs_df['Dimensione (MB)'].round(2)
                
                st.dataframe(
                    docs_df[['Nome File', 'Chunks', 'Ultimo Aggiornamento', 'Dimensione (MB)']],
                    hide_index=True
                )
            else:
                st.info("Nessun documento presente per questo agente") 