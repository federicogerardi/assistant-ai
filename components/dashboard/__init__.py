import streamlit as st
from .overview import render_overview
from .agents import render_agents_details
from .stats import render_advanced_stats

def render_dashboard(services):
    """Render the main dashboard interface."""
    st.title("📊 Status Dashboard")
    
    # Create tabs
    tab1, tab2, tab3 = st.tabs(["📑 Overview", "🤖 Agenti", "📈 Statistiche"])
    
    # Render each tab
    with tab1:
        render_overview(services)
    
    with tab2:
        render_agents_details(services)
    
    with tab3:
        render_advanced_stats(services)