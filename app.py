import streamlit as st
from openai import OpenAI
from dotenv import load_dotenv
import os

# Carica le variabili d'ambiente
load_dotenv()

# Inizializza il client OpenAI
client = OpenAI()

# Configurazione della pagina Streamlit
st.set_page_config(
    page_title="AI Assistant Chat",
    page_icon="🤖",
    layout="wide"
)

# Titolo dell'applicazione
st.title("💬 AI Assistant Chat")

# Inizializza lo stato della sessione per la cronologia delle chat
if "messages" not in st.session_state:
    st.session_state.messages = []

# Funzione per ottenere la risposta dall'assistente
def get_assistant_response(messages):
    """Ottiene la risposta dall'assistente OpenAI.

    Args:
        messages: Cronologia dei messaggi

    Returns:
        str: Risposta dell'assistente
    """
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Sei un assistente AI utile e amichevole."},
            *messages
        ],
        temperature=0.7,
    )
    return response.choices[0].message.content

# Visualizza la cronologia dei messaggi
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Input dell'utente
if prompt := st.chat_input("Scrivi il tuo messaggio qui..."):
    # Mostra il messaggio dell'utente
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # Aggiungi il messaggio dell'utente alla cronologia
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Ottieni e mostra la risposta dell'assistente
    with st.chat_message("assistant"):
        with st.spinner("Pensando..."):
            response = get_assistant_response(st.session_state.messages)
            st.markdown(response)
    
    # Aggiungi la risposta dell'assistente alla cronologia
    st.session_state.messages.append({"role": "assistant", "content": response}) 