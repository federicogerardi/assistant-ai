import streamlit as st

def init_session_state():
    """Initialize session state variables."""
    if 'refresh_state' not in st.session_state:
        st.session_state.refresh_state = 'ready'
    if 'show_toast' not in st.session_state:
        st.session_state.show_toast = False
    if 'current_page' not in st.session_state:
        st.session_state.current_page = "Chat"
    if "agent_messages" not in st.session_state:
        st.session_state.agent_messages = {} 