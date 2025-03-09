import streamlit as st
from config.agents import AGENTS_CONFIG
import logging

logger = logging.getLogger(__name__)

def render_chat(selected_agent_id, services):
    """Render the chat interface."""
    current_services = services[selected_agent_id]
    
    # Main chat interface
    st.title(f"{AGENTS_CONFIG[selected_agent_id]['icon']} {AGENTS_CONFIG[selected_agent_id]['name']}")

    # Initialize messages for new agents
    if selected_agent_id not in st.session_state.agent_messages:
        st.session_state.agent_messages[selected_agent_id] = []

    # Display chat history
    for message in st.session_state.agent_messages[selected_agent_id]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Chat input
    if prompt := st.chat_input(f"Chiedi all'esperto {AGENTS_CONFIG[selected_agent_id]['name']}..."):
        # Display user message
        with st.chat_message("user"):
            st.markdown(prompt)

        # Add user message to history
        st.session_state.agent_messages[selected_agent_id].append(
            {"role": "user", "content": prompt}
        )

        # Get assistant response
        try:
            results = current_services['doc_service'].search_documents(prompt)
            context = "\n\n".join([r['text'] for r in results])
            
            with st.chat_message("assistant"):
                response = current_services['assistant_service'].get_assistant_response(
                    st.session_state.agent_messages[selected_agent_id], 
                    context
                )
                st.markdown(response)

            # Add assistant response to history
            st.session_state.agent_messages[selected_agent_id].append(
                {"role": "assistant", "content": response}
            )
        
        except Exception as e:
            logger.error(f"Error processing query: {e}", exc_info=True)
            with st.chat_message("assistant"):
                st.error("Mi dispiace, si è verificato un errore. Riprova tra poco.") 