Caustion : Don't forgot to add the api key otherwise it won't produces the results you desired. 

# Persona-Switching Agentic Chatbot – Project Summary

## 1. Overview

This project is an **agentic, persona-switching chatbot** where each conversation thread is bound to a **profession** (e.g., “teacher”, “investor”).  
When the user says “behave like a teacher”, the system:

1. Extracts the profession name using an LLM.
2. Creates/loads a dedicated thread for that profession.
3. Dynamically generates a system prompt describing how that profession should behave.
4. Stores both the **profession name** and its **generated prompt** in PostgreSQL, along with chat history. :contentReference[oaicite:0]{index=0} :contentReference[oaicite:1]{index=1}

A Streamlit frontend provides a multi-thread chat UI, where each thread is simply labeled by the corresponding profession. :contentReference[oaicite:2]{index=2}


## 2. Architecture

### Backend (FastAPI + LangGraph)

- **FastAPI** app exposes:
  - `GET /` – health check
  - `POST /chat` – main chat endpoint
  - `GET /chat_history/{user_id}` – full history grouped by profession
  - `GET /personas/{user_id}` – list of profession threads
  - `DELETE /user/{user_id}` – delete all data for a user :contentReference[oaicite:3]{index=3}  
- **LangGraph** defines a 4-node state machine:
  1. `initialize_chat` – bootstraps state.
  2. `validate_user` – checks/creates user in DB.
  3. `handle_persona` – uses an LLM to detect the profession and select the right thread.
  4. `execute_chat` – builds a dynamic profession prompt, calls the LLM, and persists messages. :contentReference[oaicite:4]{index=4}  
- **LLM usage**:
  - First LLM call: extract profession from user message.
  - Second LLM call: generate a profession-specific system prompt.
  - Third LLM call: answer the user with that prompt as `SystemMessage`. :contentReference[oaicite:5]{index=5}  

### Database (PostgreSQL)

Schema managed by `DatabaseManager`:

- `users(user_id, created_at)`
- `conversations(id, user_id, persona_name, role, message, timestamp)`
  - `persona_name` is always the **profession name** and acts as the thread key.
- `professions(id, user_id, profession_name, prompt, created_at)`
  - Stores the generated system prompt per `(user_id, profession_name)` pair. :contentReference[oaicite:6]{index=6}  

`DatabaseManager` encapsulates:

- Connection management using env-based config.
- User existence checks and creation.
- Per-profession chat history reads/writes.
- Read/write of the stored profession prompts. :contentReference[oaicite:7]{index=7}  


### Frontend (Streamlit)

- Single-page Streamlit app (`frontend.py`) that:
  - Asks for a **user_id**.
  - Fetches `chat_history` and `personas` from the backend.
  - Shows persona threads in a **sidebar**, one per profession name.
  - Uses `st.chat_message` for a nice conversational UI.
  - Sends messages to `POST /chat` and updates the active thread if the profession changes. :contentReference[oaicite:8]{index=8}  

UI behavior:

- `current_persona` in the frontend tracks the active profession.
- Threads are clickable in the sidebar and show independent timelines.
- On every send, the backend may switch the thread if a new profession is detected, and the frontend updates accordingly. :contentReference[oaicite:9]{index=9}  


## 3. Core Flow

1. **User sends message** – e.g., “Behave like a teacher and explain RLHF”.
2. **LangGraph Node 1–2** – initialize state and check/create user. :contentReference[oaicite:10]{index=10}  
3. **Node 3: handle_persona**
   - Calls `detect_profession_from_message()`:
     - LLM returns `{"should_switch": ..., "profession_name": "teacher"}`.
   - Sets `current_persona = "teacher"` and loads/creates the corresponding thread.
   - Stores `profession_name` on the state. :contentReference[oaicite:11]{index=11}  
4. **Node 4: execute_chat**
   - Calls `get_or_create_profession_prompt(user_id, "teacher")`.
   - If missing, LLM generates a system prompt describing how a teacher should respond.
   - Prompt is stored in `professions` table.
   - Builds message history for this profession and calls the LLM for the final reply.
   - Saves user & assistant messages into `conversations`. :contentReference[oaicite:12]{index=12} :contentReference[oaicite:13]{index=13}  
5. **Frontend** updates the view with the new message, and, if the profession changed, switches the active thread name to the new profession. :contentReference[oaicite:14]{index=14}  


## 4. Future Improvements

1. **Stronger profession detection**
   - Add explicit confidence scores and fallback rules if the model is uncertain.
   - Support “stacked roles” (e.g., “teacher + investor”) via composite prompts.

2. **Per-profession settings and controls**
   - Let users edit the stored prompt for a profession in the UI.
   - Add sliders/toggles for tone (formal vs casual), risk appetite (for investor), level (high school vs PhD teacher).

3. **Analytics & observability**
   - Store token usage, response latency, and profession-level stats per user.
   - Build a Streamlit dashboard for most-used professions, average conversation length, etc.

4. **Multi-model support**
   - Configure different base models per profession (e.g., a math-focused model for “math teacher”, legal-focused for “lawyer”) via routing logic in Node 4.

5. **Auth & multi-tenant support**
   - Add JWT-based auth.
   - Namespace data by tenant/project in the DB for safer multi-user hosting.

6. **RAG + tool integration**
   - Allow certain professions to bring their own tools (e.g., “financial analyst” with live market data, “doctor” with medical guidelines) by plugging LangChain tools into the graph.

7. **Export & import of profession profiles**
   - Allow users to export a profession prompt as JSON, share with others, and import back for reuse across deployments.
