
"""
FastAPI backend with LangGraph agentic framework for persona-switching chatbot.
Implements a 4-node state machine for dynamic persona/profession management.
"""

import os
import re
import json
from typing import TypedDict, List, Dict, Annotated
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from database import db_manager
import uvicorn


# Initialize FastAPI app
app = FastAPI(title="Persona-Switching Agentic Chatbot")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# LLM initialization
llm = ChatOpenAI(
    model="gpt-4o",
    api_key=os.getenv("OPENAI_API_KEY"),
    temperature=0.7,
)


# State definition for LangGraph
class ChatState(TypedDict, total=False):
    user_id: str
    message: str
    current_persona: str  # profession name for the current thread
    conversation_history: List[Dict]
    response: str
    user_exists: bool
    persona_detected: str
    action: str
    profession_name: str
    profession_prompt: str


# Pydantic models for API
class ChatRequest(BaseModel):
    user_id: str
    message: str
    # This will be treated as the initial profession name / thread name
    persona_name: str = "general_expert"


class ChatResponse(BaseModel):
    response: str
    # This will always be the profession name that backs the thread
    persona_name: str
    user_id: str


# Node 1: Initialize Chat
def initialize_chat(state: ChatState) -> ChatState:
    """
    Node 1: Chat initialization.
    Sets up the initial state and prepares for user validation.
    """
    print(f"[Node 1] Initializing chat for user: {state['user_id']}")

    # Set default values if not present
    if "current_persona" not in state or not state["current_persona"]:
        # Default "profession" if user hasn't chosen one yet
        state["current_persona"] = "general_expert"

    if "conversation_history" not in state:
        state["conversation_history"] = []

    state["action"] = "validate_user"
    return state


# Node 2: Validate User
def validate_user(state: ChatState) -> ChatState:
    """
    Node 2: Check if user exists in database.
    If yes, load all personas. If no, create new user.
    """
    user_id = state["user_id"]
    print(f"[Node 2] Validating user: {user_id}")

    user_exists = db_manager.user_exists(user_id)
    state["user_exists"] = user_exists

    if not user_exists:
        print(f"[Node 2] Creating new user: {user_id}")
        db_manager.create_user(user_id)
        state["conversation_history"] = []
    else:
        print(f"[Node 2] User exists")

    state["action"] = "handle_persona"
    return state


def detect_profession_from_message(message: str, current_profession: str = "") -> Dict[str, str]:
    """
    Use the LLM to detect whether the user is asking the assistant
    to behave as a particular profession (teacher, investor, etc.).
    Returns a dict with:
      - should_switch: bool (as a Python bool)
      - profession_name: the normalized profession name to use for the thread.
    """
    payload = {
        "message": message,
        "current_profession": current_profession,
    }
    system = SystemMessage(
        content=(
            "You extract the profession or role a user wants an AI assistant to adopt.\n"
            "You are given a JSON object with two fields: `message` and `current_profession`.\n"
            "Respond ONLY with JSON in the form:\n"
            '{"should_switch": true or false, "profession_name": "<profession or empty>"}.\\n'
            "If the user clearly asks the assistant to act/behave like some profession or role, "
            "set should_switch to true and profession_name to a short noun phrase like "
            "\"teacher\", \"investor\", \"lawyer\", \"sales coach\", etc.\n"
            "If they do NOT ask for any profession or role change, set should_switch to false and "
            "profession_name to the current_profession (which may be empty)."
        )
    )
    human = HumanMessage(content=json.dumps(payload))
    result = llm.invoke([system, human])
    try:
        raw_content = result.content if isinstance(result.content, str) else str(result.content)
        data = json.loads(raw_content)
    except Exception:
        return {
            "should_switch": False,
            "profession_name": current_profession,
        }
    should_switch = bool(data.get("should_switch", False))
    profession_name = (data.get("profession_name") or "").strip()
    if not profession_name:
        profession_name = current_profession
    return {
        "should_switch": should_switch,
        "profession_name": profession_name,
    }


# Node 3: Profession Detection and Thread Management
def handle_persona(state: ChatState) -> ChatState:
    """
    Node 3: Use the AI model to extract the profession the user wants
    and create / load a thread based purely on that profession name.
    The thread name is always the profession name.
    """
    user_id = state["user_id"]
    message = state["message"]
    current_profession = state.get("current_persona") or "general_expert"

    print(f"[Node 3] Handling profession for user: {user_id}")
    print(f"[Node 3] Current profession: {current_profession}")

    # Use LLM to detect whether user wants a new profession behavior
    detection = detect_profession_from_message(message, current_profession)
    profession_name = detection["profession_name"] or current_profession

    print(f"[Node 3] Detected profession: {profession_name}")

    # Store on state so downstream nodes (and DB) only see profession names
    state["persona_detected"] = profession_name
    state["current_persona"] = profession_name
    state["profession_name"] = profession_name

    # Each profession has its own thread (conversation history)
    persona_exists = db_manager.persona_exists_for_user(user_id, profession_name)
    if persona_exists:
        print(f"[Node 3] Loading existing thread for profession: {profession_name}")
        history = db_manager.get_persona_history(user_id, profession_name)
        state["conversation_history"] = history
    else:
        print(f"[Node 3] Creating new thread for profession: {profession_name}")
        state["conversation_history"] = []

    state["action"] = "execute_chat"
    return state


# Node 4: Execute Chat with Profession Persona

def generate_profession_prompt_with_llm(profession_name: str) -> str:
    """
    Use the LLM to dynamically generate a system prompt for a given profession.
    This describes HOW the assistant should behave when acting as that profession.
    """
    system = SystemMessage(
        content=(
            "You write system prompts for an AI assistant.\n"
            "Given the name of a profession or role, you must write a single, clear system prompt "
            "that tells the assistant how to behave as an expert in that profession.\n"
            "Focus on communication style, goals, and how they should respond to user questions."
        )
    )
    human = HumanMessage(
        content=json.dumps(
            {
                "profession_name": profession_name,
                "instruction": "Write a system prompt for an AI that is acting as this profession.",
            }
        )
    )
    result = llm.invoke([system, human])
    raw_content = result.content if isinstance(result.content, str) else str(result.content)
    prompt = raw_content.strip()
    if not prompt:
        # Fallback generic prompt
        prompt = (
            f"You are an AI assistant acting as a professional {profession_name}. "
            f"Answer as a knowledgeable, helpful {profession_name}, using the tone, priorities, "
            f"and expertise that such a professional would use."
        )
    return prompt


def get_or_create_profession_prompt(user_id: str, profession_name: str) -> str:
    """
    Retrieve a stored prompt for this user + profession from the database,
    or generate and store a new one if it doesn't exist yet.
    """
    existing = db_manager.get_profession_prompt(user_id, profession_name)
    if existing:
        return existing

    prompt = generate_profession_prompt_with_llm(profession_name)
    db_manager.save_profession_prompt(user_id, profession_name, prompt)
    return prompt


def execute_chat(state: ChatState) -> ChatState:
    """
    Node 4: Execute chat with the selected profession-based persona.
    Generates a profession-specific prompt, stores it, and uses it to answer the user.
    """
    user_id = state["user_id"]
    message = state["message"]
    profession_name = state.get("profession_name") or state.get("current_persona") or "general_expert"
    conversation_history = state.get("conversation_history", [])

    print(f"[Node 4] Executing chat for user: {user_id}, profession: {profession_name}")

    # Get (or create) a dynamic prompt for this profession from the backend/database
    profession_prompt = state.get("profession_prompt")
    if not profession_prompt:
        profession_prompt = get_or_create_profession_prompt(user_id, profession_name)

    # Persist on state so callers can inspect it if needed
    state["profession_prompt"] = profession_prompt

    # Build message history for LLM
    messages = [SystemMessage(content=profession_prompt)]

    # Add conversation history (stored per profession thread)
    for msg in conversation_history[-10:]:  # Last 10 messages for context
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["message"]))
        elif msg["role"] == "assistant":
            messages.append(AIMessage(content=msg["message"]))

    # Add current message
    messages.append(HumanMessage(content=message))

    # Generate response using the profession-specific prompt
    try:
        response = llm.invoke(messages)
        assistant_message = response.content

        # Save user message to database
        db_manager.save_message(user_id, profession_name, "user", message)

        # Save assistant response to database
        db_manager.save_message(user_id, profession_name, "assistant", assistant_message)

        state["response"] = assistant_message
        print("[Node 4] Response generated and saved")

    except Exception as e:
        print(f"[Node 4] Error generating response: {e}")
        state["response"] = f"I apologize, but I encountered an error: {str(e)}"

    state["action"] = "complete"
    return state


# Router function to determine next node
def route_next(state: ChatState) -> str:
    """Determine the next node based on current action."""
    action = state.get("action", "complete")

    if action in ("validate_user", "handle_persona", "execute_chat"):
        return action
    return "complete"


# Build LangGraph
def build_graph():
    """Build the LangGraph state machine."""
    workflow = StateGraph(ChatState)

    # Add nodes
    workflow.add_node("initialize_chat", initialize_chat)
    workflow.add_node("validate_user", validate_user)
    workflow.add_node("handle_persona", handle_persona)
    workflow.add_node("execute_chat", execute_chat)

    # Set entry point
    workflow.set_entry_point("initialize_chat")

    # Conditional mapping from router outputs to nodes / END
    conditional_mapping = {
        "validate_user": "validate_user",
        "handle_persona": "handle_persona",
        "execute_chat": "execute_chat",
        "complete": END,
    }

    # Add conditional edges for each node
    workflow.add_conditional_edges("initialize_chat", route_next, conditional_mapping)
    workflow.add_conditional_edges("validate_user", route_next, conditional_mapping)
    workflow.add_conditional_edges("handle_persona", route_next, conditional_mapping)
    workflow.add_conditional_edges("execute_chat", route_next, conditional_mapping)

    return workflow.compile()


# Create the graph
graph = build_graph()


# API Endpoints
@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "online",
        "service": "Persona-Switching Agentic Chatbot",
        "version": "1.0.0",
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Main chat endpoint. Processes user messages through the LangGraph pipeline.
    """
    try:
        # Initialize state
        initial_state: ChatState = {
            "user_id": request.user_id,
            "message": request.message,
            # This is the initial profession/thread name
            "current_persona": request.persona_name,
            "conversation_history": [],
            "response": "",
            "user_exists": False,
            "persona_detected": "",
            "action": "initialize",
        }

        # Run the graph
        final_state = graph.invoke(initial_state)

        return ChatResponse(
            response=final_state["response"],
            persona_name=final_state["current_persona"],  # profession name
            user_id=final_state["user_id"],
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/chat_history/{user_id}")
async def get_chat_history(user_id: str):
    """
    Get all chat history for a user, grouped by profession (persona_name).
    """
    try:
        if not db_manager.user_exists(user_id):
            raise HTTPException(status_code=404, detail="User not found")

        history = db_manager.get_all_chat_history(user_id)
        personas = db_manager.get_user_personas(user_id)

        return {
            "user_id": user_id,
            "personas": personas,  # list of profession names
            "history": history,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/personas/{user_id}")
async def get_user_personas(user_id: str):
    """Get all profession-based personas for a user."""
    try:
        if not db_manager.user_exists(user_id):
            raise HTTPException(status_code=404, detail="User not found")

        personas = db_manager.get_user_personas(user_id)
        return {"user_id": user_id, "personas": personas}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/user/{user_id}")
async def delete_user(user_id: str):
    """Delete a user and all their data (for testing/cleanup)."""
    try:
        success = db_manager.delete_user_data(user_id)
        if success:
            return {"message": f"User {user_id} deleted successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to delete user")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
