import streamlit as st
import plotly.express as px
import pandas as pd
from config.agents import AGENTS_CONFIG
from services.stats import get_document_stats

def render_advanced_stats(services):
    """Render the advanced statistics tab of the dashboard."""
    st.header("📈 Statistiche Avanzate")
    
    # Raccogli statistiche per tutti gli agenti
    all_stats = []
    for agent_id, config in AGENTS_CONFIG.items():
        stats = get_document_stats(agent_id, config, services[agent_id]['doc_service'])
        all_stats.append(stats)
    
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
    else:
        st.info("Nessun dato temporale disponibile") 