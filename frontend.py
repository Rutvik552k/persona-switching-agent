"""
Streamlit frontend for Persona-Switching Agentic Chatbot.
Provides an intuitive UI with sidebar for persona management and real-time chat.
"""

import streamlit as st
import requests
import json
from datetime import datetime
import os


# Configuration
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")


# Initialize session state
def initialize_session_state():
    """Initialize Streamlit session state variables."""
    if 'user_id' not in st.session_state:
        st.session_state.user_id = None
    if 'current_persona' not in st.session_state:
        st.session_state.current_persona = 'default'
    if 'chat_history' not in st.session_state:
        st.session_state.chat_history = {}
    if 'personas' not in st.session_state:
        st.session_state.personas = ['default']
    if 'messages' not in st.session_state:
        st.session_state.messages = []


def load_user_data(user_id: str):
    """Load all personas and chat history for a user."""
    try:
        # Get chat history
        response = requests.get(f"{BACKEND_URL}/chat_history/{user_id}")
        if response.status_code == 200:
            data = response.json()
            st.session_state.personas = data.get('personas', ['default'])
            st.session_state.chat_history = data.get('history', {})
            
            # Load messages for current persona
            if st.session_state.current_persona in st.session_state.chat_history:
                history = st.session_state.chat_history[st.session_state.current_persona]
                st.session_state.messages = [
                    {"role": msg['role'], "content": msg['message']}
                    for msg in history
                ]
            else:
                st.session_state.messages = []
            
            return True
        elif response.status_code == 404:
            # New user
            st.session_state.personas = ['default']
            st.session_state.chat_history = {}
            st.session_state.messages = []
            return True
        else:
            st.error(f"Error loading user data: {response.status_code}")
            return False
    except Exception as e:
        st.error(f"Connection error: {e}")
        return False


def send_message(user_id: str, message: str, persona_name: str):
    """Send a message to the backend and get response."""
    try:
        response = requests.post(
            f"{BACKEND_URL}/chat",
            json={
                "user_id": user_id,
                "message": message,
                "persona_name": persona_name
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            return data['response'], data['persona_name']
        else:
            st.error(f"Error: {response.status_code} - {response.text}")
            return None, None
    except Exception as e:
        st.error(f"Connection error: {e}")
        return None, None


def switch_persona(persona_name: str):
    """Switch to a different persona thread."""
    st.session_state.current_persona = persona_name
    
    # Load messages for this persona
    if persona_name in st.session_state.chat_history:
        history = st.session_state.chat_history[persona_name]
        st.session_state.messages = [
            {"role": msg['role'], "content": msg['message']}
            for msg in history
        ]
    else:
        st.session_state.messages = []


def format_persona_name(persona: str) -> str:
    """Format persona name for display."""
    if persona == 'default':
        return "🏠 Default"
    else:
        # Capitalize and add emoji
        emoji_map = {
            'mentor': '🎓',
            'investor': '💼',
            'customer': '👤',
            'technical': '⚙️',
            'critic': '🔍',
            'coach': '🏆'
        }
        
        for key, emoji in emoji_map.items():
            if key in persona.lower():
                return f"{emoji} {persona.title()}"
        
        return f"💬 {persona.title()}"


def main():
    """Main Streamlit application."""
    st.set_page_config(
        page_title="Persona-Switching AI Chatbot",
        page_icon="🤖",
        layout="wide"
    )
    
    initialize_session_state()
    
    # Sidebar
    with st.sidebar:
        st.title("🤖 Persona Chat")
        st.markdown("---")
        
        # User ID input
        if st.session_state.user_id is None:
            st.subheader("Get Started")
            user_input = st.text_input(
                "Enter your User ID:",
                placeholder="e.g., user123",
                help="Create a new ID or use an existing one"
            )
            
            if st.button("Start Chat", type="primary"):
                if user_input:
                    st.session_state.user_id = user_input
                    if load_user_data(user_input):
                        st.rerun()
                else:
                    st.warning("Please enter a User ID")
        
        else:
            # Show current user
            st.success(f"**User:** {st.session_state.user_id}")
            
            if st.button("Logout", type="secondary"):
                st.session_state.user_id = None
                st.session_state.personas = ['default']
                st.session_state.chat_history = {}
                st.session_state.messages = []
                st.session_state.current_persona = 'default'
                st.rerun()
            
            st.markdown("---")
            
            # Persona threads
            st.subheader("Conversation Threads")
            
            # Refresh button
            if st.button("🔄 Refresh", help="Reload persona threads"):
                load_user_data(st.session_state.user_id)
                st.rerun()
            
            st.markdown("---")
            
            # Display persona threads
            for persona in st.session_state.personas:
                is_current = persona == st.session_state.current_persona
                
                button_type = "primary" if is_current else "secondary"
                button_label = format_persona_name(persona)
                
                if is_current:
                    button_label += " ✓"
                
                # Display message count
                msg_count = len(st.session_state.chat_history.get(persona, []))
                
                col1, col2 = st.columns([3, 1])
                with col1:
                    if st.button(
                        button_label,
                        key=f"persona_{persona}",
                        type=button_type,
                        use_container_width=True
                    ):
                        if not is_current:
                            switch_persona(persona)
                            st.rerun()
                
                with col2:
                    st.caption(f"{msg_count//2} msgs")
            
            st.markdown("---")
            
            # Instructions
            with st.expander("ℹ️ How to Use"):
                st.markdown("""
                **Creating New Personas:**
                - Type: "act like a mentor"
                - Type: "be an investor"
                - Type: "switch to technical advisor"
                
                **Switching Threads:**
                - Type: "back to mentor thread"
                - Type: "return to investor"
                - Or click persona buttons in sidebar
                
                **Tips:**
                - Each persona maintains separate conversation history
                - Your conversations are saved automatically
                - You can create unlimited custom personas
                """)
            
            # About
            with st.expander("ℹ️ About"):
                st.markdown("""
                **Persona-Switching Agentic Chatbot**
                
                Built with:
                - 🔷 LangGraph (State Machine)
                - ⚡ FastAPI (Backend)
                - 🎨 Streamlit (Frontend)
                - 🗄️ PostgreSQL (Database)
                - 🤖 Claude AI (LLM)
                
                Features:
                - Dynamic persona switching
                - Persistent conversation history
                - Multi-threaded conversations
                - Real-time context switching
                """)
    
    # Main chat interface
    if st.session_state.user_id is None:
        # Welcome screen
        st.title("Welcome to Persona-Switching AI Chatbot 🤖")
        st.markdown("""
        ### Get Started
        
        This is an advanced agentic chatbot that can dynamically adopt different expert personas based on your needs.
        
        **Features:**
        - 🎭 **Dynamic Persona Switching**: Create and switch between different AI personas
        - 💾 **Persistent Memory**: Your conversations are saved and can be resumed anytime
        - 🔄 **Context Switching**: Seamlessly switch between different conversation threads
        - 🧠 **Smart State Management**: Powered by LangGraph for robust conversation flow
        
        **To begin:**
        1. Enter a User ID in the sidebar (create new or use existing)
        2. Start chatting with the default persona
        3. Request persona changes by typing commands like "act like a mentor"
        4. Switch between personas anytime using the sidebar or chat commands
        
        ---
        
        **Example Commands:**
        - "act like my mentor" - Creates a mentor persona thread
        - "be a skeptical investor" - Switch to investor persona
        - "back to mentor thread" - Return to mentor conversation
        - "switch to technical advisor" - Create/switch to technical advisor
        """)
        
        st.info("👈 Please enter your User ID in the sidebar to start chatting!")
    
    else:
        # Chat interface
        st.title(f"💬 Chat: {format_persona_name(st.session_state.current_persona)}")
        
        # Display chat messages
        chat_container = st.container()
        with chat_container:
            for message in st.session_state.messages:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])
        
        # Chat input
        if prompt := st.chat_input("Type your message here..."):
            # Add user message to chat
            st.session_state.messages.append({"role": "user", "content": prompt})
            
            with st.chat_message("user"):
                st.markdown(prompt)
            
            # Get assistant response
            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    response, new_persona = send_message(
                        st.session_state.user_id,
                        prompt,
                        st.session_state.current_persona
                    )
                    
                    if response:
                        st.markdown(response)
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": response
                        })
                        
                        # Check if persona changed
                        if new_persona != st.session_state.current_persona:
                            st.session_state.current_persona = new_persona
                            st.success(f"Switched to: {format_persona_name(new_persona)}")
                            
                            # Reload user data to update sidebar
                            load_user_data(st.session_state.user_id)
                            st.rerun()


if __name__ == "__main__":
    main()
