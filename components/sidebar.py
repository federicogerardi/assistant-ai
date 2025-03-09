import streamlit as st
from config.agents import AGENTS_CONFIG

def render_sidebar():
    """Render the sidebar and return the selected agent ID."""
    with st.sidebar:
        st.title("🤖 Document Q&A")
        
        # 1. Agent selection
        st.subheader("Scegli l'esperto")
        agent_options = {f"{config['icon']} {config['name']}": agent_id 
                        for agent_id, config in AGENTS_CONFIG.items()}
        selected_agent_name = st.selectbox(
            "Seleziona un esperto",
            options=list(agent_options.keys()),
            key="agent_selector"
        )
        selected_agent_id = agent_options[selected_agent_name]
        
        # 2. Navigation
        st.markdown("---")
        st.subheader("📍 Navigazione")
        page = st.radio(
            "Seleziona pagina",
            ["💬 Chat", "📊 Dashboard"],
            key="page_selector"
        )
        st.session_state.current_page = "Chat" if "Chat" in page else "Dashboard"
        
        # 3. Admin actions
        render_admin_actions()
        
        return selected_agent_id

def render_admin_actions():
    """Render the admin actions section."""
    st.markdown("---")
    with st.expander("⚠️ Azioni Amministrative"):
        st.warning("Le seguenti azioni potrebbero influenzare il "
                  "funzionamento del sistema")
        handle_refresh_button()

def handle_refresh_button():
    """Handle the refresh button logic."""
    if st.session_state.show_toast:
        st.toast("✅ Database ricaricato con successo!", icon="✅")
        st.session_state.show_toast = False
    
    if st.session_state.refresh_state == 'refreshing':
        st.toast("🔄 Ricaricamento in corso...", icon="🔄")
        st.session_state.refresh_state = 'ready'
        st.session_state.show_toast = True
        st.cache_resource.clear()
        st.rerun()
    
    if st.button("🔄 Ricarica Documenti"):
        st.session_state.refresh_state = 'refreshing'
        st.rerun() 