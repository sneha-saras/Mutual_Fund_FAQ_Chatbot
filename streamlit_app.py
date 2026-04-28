"""
Streamlit App for INDMoney FAQ Assistant
"""

import streamlit as st
import requests
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# App configuration
st.set_page_config(
    page_title="INDMoney FAQ Assistant",
    page_icon="💰",
    layout="wide"
)

# Custom CSS
st.markdown("""
<style>
    .stApp {
        background-color: #f5f5f5;
    }
    .header {
        background-color: #4CAF50;
        color: white;
        padding: 1rem;
        border-radius: 10px;
        margin-bottom: 2rem;
    }
    .fund-card {
        background-color: white;
        padding: 1rem;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        margin-bottom: 1rem;
    }
    .chat-message {
        padding: 1rem;
        border-radius: 10px;
        margin-bottom: 1rem;
    }
    .user-message {
        background-color: #2196F3;
        color: white;
    }
    .bot-message {
        background-color: #E3F2FD;
        color: black;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'messages' not in st.session_state:
    st.session_state.messages = []
if 'funds' not in st.session_state:
    st.session_state.funds = []

# Get backend URL from environment or use default
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

# Header
st.markdown("<div class='header'><h1>💰 INDMoney FAQ Assistant</h1><p>Get answers about HDFC mutual funds</p></div>", unsafe_allow_html=True)

# Tabs
tab1, tab2 = st.tabs(["💬 Chat", "📊 Funds"])

# Chat Tab
with tab1:
    st.header("Ask about Mutual Funds")
    
    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    
    # User input
    if prompt := st.chat_input("Ask anything about mutual funds..."):
        # Add user message to chat
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # Prefer AI + RAG when API returns a real Gemini answer; else keyword FAQ search
        try:
            answer = None
            ai_resp = requests.post(
                f"{BACKEND_URL}/api/ai/ask",
                json={
                    "question": prompt,
                    "use_context": True,
                    "use_rag": True,
                },
                timeout=120,
            )
            if ai_resp.status_code == 200:
                payload = ai_resp.json()
                src = payload.get("source")
                text = (payload.get("answer") or "").strip()
                if src and src != "error" and text:
                    answer = text
            if answer is None:
                response = requests.get(
                    f"{BACKEND_URL}/api/faq",
                    params={"q": prompt, "limit": 5},
                    timeout=30,
                )
                if response.status_code == 200:
                    data = response.json()
                    if data:
                        answer = "\n\n".join(
                            [f"**Q: {faq['question']}**\n\n{faq['answer']}" for faq in data]
                        )
                    else:
                        answer = "I couldn't find any relevant information for your question. Please try rephrasing."
                else:
                    answer = "Sorry, I'm having trouble connecting to the backend service."
        except Exception:
            answer = "Sorry, I encountered an error while processing your request."
        
        # Add bot response to chat
        st.session_state.messages.append({"role": "assistant", "content": answer})
        with st.chat_message("assistant"):
            st.markdown(answer)

# Funds Tab
with tab2:
    st.header("HDFC Mutual Funds")
    
    # Load funds data
    if not st.session_state.funds:
        try:
            response = requests.get(f"{BACKEND_URL}/api/funds?limit=100")
            if response.status_code == 200:
                st.session_state.funds = response.json()
        except Exception as e:
            st.error("Failed to load funds data")
    
    # Display funds
    if st.session_state.funds:
        for fund in st.session_state.funds:
            with st.container():
                st.markdown(f"<div class='fund-card'>", unsafe_allow_html=True)
                st.subheader(fund.get('fund_name', 'N/A'))
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.write("**Manager:**", fund.get('fund_manager', 'N/A'))
                    st.write("**Expense Ratio:**", fund.get('expense_ratio', 'N/A'))
                with col2:
                    st.write("**Risk:**", fund.get('riskometer', 'N/A'))
                    st.write("**Minimum SIP:**", fund.get('minimum_sip', 'N/A'))
                with col3:
                    st.write("**Exit Load:**", fund.get('exit_load', 'N/A'))
                
                # Returns
                if fund.get('returns'):
                    st.write("**Returns:**")
                    returns_cols = st.columns(len(fund['returns']))
                    for i, (period, value) in enumerate(fund['returns'].items()):
                        returns_cols[i].metric(period, value)
                
                st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.info("No funds data available. Make sure the backend is running.")

# Sidebar
st.sidebar.title("About")
st.sidebar.info("""
This is the INDMoney FAQ Assistant, 
a Streamlit app that provides 
information about HDFC mutual funds.

Built with:
- Streamlit
- FastAPI (Backend)
- SQLite (Database)
""")

st.sidebar.title("Quick Questions")
if st.sidebar.button("What is minimum SIP amount?"):
    st.session_state.messages.append({"role": "user", "content": "What is the minimum SIP amount?"})
    st.rerun()

if st.sidebar.button("What is expense ratio?"):
    st.session_state.messages.append({"role": "user", "content": "What is expense ratio?"})
    st.rerun()

if st.sidebar.button("Tell me about HDFC Mid Cap Fund"):
    st.session_state.messages.append({"role": "user", "content": "Tell me about HDFC Mid Cap Fund"})
    st.rerun()