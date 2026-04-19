"""
Configurações globais do projeto.
Lê variáveis de ambiente via python-dotenv.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Resolve o .env na raiz do projeto
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


# ── LLM ──────────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")
ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "llama3.1")  # fallback Ollama

# ── LangSmith ────────────────────────────────────────────────────────────────
LANGSMITH_API_KEY: str = os.getenv("LANGSMITH_API_KEY", "")
LANGSMITH_PROJECT: str = os.getenv("LANGSMITH_PROJECT", "lang-chat-test")
LANGSMITH_ENDPOINT: str = os.getenv(
    "LANGSMITH_ENDPOINT", "https://api.smith.langchain.com"
)

# ── Banco de dados padrão (SQLite embutido p/ demo) ──────────────────────────
DEFAULT_DB_URL: str = os.getenv(
    "DATABASE_URL", f"sqlite:///{BASE_DIR / 'demo.db'}"
)

# ── Ativa o tracing do LangSmith automaticamente ─────────────────────────────
if LANGSMITH_API_KEY:
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = LANGSMITH_API_KEY
    os.environ["LANGCHAIN_PROJECT"] = LANGSMITH_PROJECT
    os.environ["LANGCHAIN_ENDPOINT"] = LANGSMITH_ENDPOINT
