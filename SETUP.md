# Setup & Run Guide

This document explains how to set up and run the **Persona-Switching Agentic Chatbot** (backend, database, and Streamlit frontend).

---

## 1. Prerequisites

- **Python**: 3.11 (recommended)
- **PostgreSQL**: local installation or Docker
- **pip** or `pipx` / `virtualenv`
- An **OpenAI API key** (for `langchain-openai` / `ChatOpenAI`). :contentReference[oaicite:15]{index=15}  

Optional for convenience:
- **Docker** (for a quick Postgres instance)

docker run --name persona-db \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=postgres \
  -p 5432:5432 \
  -d postgres:16


---

## 2. Clone & create virtual environment

```bash
git clone giturl
cd persona-switch-agent

# Create & activate virtualenv (Windows PowerShell)
python -m venv agent 
.\agent\Scripts\activate

# Or on macOS/Linux:
# python -m venv agent
# source agent/bin/activate

Run the frontend :streamlit run frontend.py
Run the backend : python backend.py