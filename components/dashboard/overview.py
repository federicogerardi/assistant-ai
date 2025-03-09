import streamlit as st
import plotly.express as px
import pandas as pd
from config.agents import AGENTS_CONFIG
from services.stats import get_document_stats

def render_overview(services):
    """Render the overview tab of the dashboard."""
    st.header("📑 Overview Sistema")
    
    # Metriche principali
    col1, col2, col3, col4 = st.columns(4)
    
    total_agents = len(AGENTS_CONFIG)
    total_docs = 0
    total_chunks = 0
    
    # Raccogli statistiche per tutti gli agenti
    all_stats = []
    for agent_id, config in AGENTS_CONFIG.items():
        stats = get_document_stats(agent_id, config, services[agent_id]['doc_service'])
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
    
    if not docs_per_agent.empty:
        fig = px.bar(docs_per_agent, 
                     x='Agente', 
                     y=['Documenti', 'Chunks'],
                     barmode='group',
                     title="Documenti e Chunks per Agente")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Nessun documento presente nel sistema") 