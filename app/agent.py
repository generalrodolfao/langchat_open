"""
Agente LangChain com SQL.
Usa SQLDatabaseChain / create_sql_agent para transformar
linguagem natural em queries SQL e devolver resultados.
"""
import logging
import time
import uuid
from typing import Any
import re

logger = logging.getLogger(__name__)

from langchain_ollama import ChatOllama
from langchain_anthropic import ChatAnthropic
from langchain_community.agent_toolkits import create_sql_agent
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
from langchain_core.callbacks import BaseCallbackHandler
from langsmith import Client as LangSmithClient
import chromadb
from pathlib import Path

from app.config import OPENAI_MODEL, ANTHROPIC_API_KEY, ANTHROPIC_MODEL, LANGSMITH_API_KEY, LANGSMITH_PROJECT
from app.database import get_langchain_db


def _build_llm(model: str | None, temperature: float):
    """Retorna ChatAnthropic se a chave estiver disponível, senão ChatOllama."""
    if ANTHROPIC_API_KEY:
        # Ignora model names do Ollama (não são válidos na API Anthropic)
        anthropic_model = model if model and model.startswith("claude") else ANTHROPIC_MODEL
        return ChatAnthropic(
            model=anthropic_model,
            temperature=temperature,
            api_key=ANTHROPIC_API_KEY,
        )
    return ChatOllama(model=model or OPENAI_MODEL, temperature=temperature)


# ── Callback para capturar tokens / latência ──────────────────────────────────
class MetricsCallback(BaseCallbackHandler):
    def __init__(self):
        self.start_time: float = 0.0
        self.end_time: float = 0.0
        self.total_tokens: int = 0
        self.prompt_tokens: int = 0
        self.completion_tokens: int = 0

    def on_llm_start(self, *args, **kwargs):
        self.start_time = time.time()

    def on_llm_end(self, response, **kwargs):
        self.end_time = time.time()
        if hasattr(response, "llm_output") and response.llm_output:
            usage = response.llm_output.get("token_usage", {})
            self.total_tokens = usage.get("total_tokens", 0)
            self.prompt_tokens = usage.get("prompt_tokens", 0)
            self.completion_tokens = usage.get("completion_tokens", 0)

    @property
    def latency_ms(self) -> int:
        if self.end_time and self.start_time:
            return int((self.end_time - self.start_time) * 1000)
        return 0


def build_agent(db_url: str, temperature: float = 0.0, model: str | None = None):
    """Constrói um SQL agent LangChain para a URL de banco fornecida."""
    llm = _build_llm(model, temperature)
    db = get_langchain_db(db_url)
    toolkit = SQLDatabaseToolkit(db=db, llm=llm)
    custom_prefix = (
        "You are a Senior Business Analyst and Data Consultant from Brazil. IMPORTANT RULES: "
        "1. The database tables and columns are entirely in PORTUGUESE (e.g. 'pedidos' not 'orders'). "
        "2. You DO NOT know the database schema yet. YOU MUST ALWAYS call 'sql_db_list_tables' to list tables first! "
        "3. NEVER guess or translate table names. NEVER hallucinate or fake tool outputs. "
        "4. NEVER just write out the SQL query in plaintext. YOU MUST ALWAYS USE the 'sql_db_query' tool to execute your SQL against the database. "
        "5. When giving the final answer, ALWAYS provide the exact requested number/data AND include a valuable BUSINESS INSIGHT based on context. Act like a consultant giving strategic advice (e.g., 'Você teve X pedidos. Para escalar, sugiro focar em aumentar leads de marketing...' ou analisando tendências sugerindo focar em novos produtos). "
        "6. Final response MUST be in fluent PT-BR. DO NOT output intermediate technical thoughts or SQL code to the user."
    )

    agent = create_sql_agent(
        llm=llm,
        toolkit=toolkit,
        verbose=True,
        agent_type="tool-calling",
        handle_parsing_errors=True,
        prefix=custom_prefix,
    )
    return agent


_agent_cache: dict[str, Any] = {}


def _get_agent(db_url: str, temperature: float, model: str | None):
    cache_key = f"{db_url}|{temperature}|{model or ''}"
    if cache_key not in _agent_cache:
        _agent_cache[cache_key] = build_agent(db_url, temperature=temperature, model=model)
    return _agent_cache[cache_key]


# ── Cache Semântico (ChromaDB) — inicialização lazy ──────────────────────────
_chroma_client: chromadb.PersistentClient | None = None
_semantic_cache = None
_embed_fn = None


def _get_semantic_cache():
    global _chroma_client, _semantic_cache, _embed_fn
    if _semantic_cache is None:
        from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
        cache_dir = Path(__file__).resolve().parent.parent / ".cache_db"
        _embed_fn = DefaultEmbeddingFunction()
        _chroma_client = chromadb.PersistentClient(path=str(cache_dir))
        _semantic_cache = _chroma_client.get_or_create_collection(
            name="langchat_cache",
            embedding_function=_embed_fn,
        )
    return _semantic_cache, _embed_fn


def run_prompt(
    db_url: str,
    prompt: str,
    temperature: float = 0.0,
    model: str | None = None,
    run_name: str | None = None,
) -> dict[str, Any]:
    """
    Executa um prompt no agente SQL e retorna o resultado com métricas.
    """
    t0 = time.time()

    # Verifica no Cache Semântico primeiro
    try:
        semantic_cache, _ = _get_semantic_cache()
        cache_results = semantic_cache.query(query_texts=[prompt], n_results=1)
        if cache_results["distances"] and len(cache_results["distances"][0]) > 0:
            distance = cache_results["distances"][0][0]
            if distance < 0.35:  # Threshold para embedder all-MiniLM (distância coseno 0–2)
                elapsed = int((time.time() - t0) * 1000)
                meta = cache_results["metadatas"][0][0]
                cached_answer = meta.get("answer") or cache_results["documents"][0][0]
                return {
                    "answer": f"⚡ [Cópia do Cache]\n{cached_answer}",
                    "error": None,
                    "latency_ms": elapsed,
                    "total_tokens": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "model": "chromadb_cache",
                    "temperature": temperature,
                }
    except Exception:
        logger.warning("Cache semântico indisponível, seguindo para o LLM.", exc_info=True)

    metrics = MetricsCallback()
    agent = _get_agent(db_url, temperature=temperature, model=model)

    config: dict[str, Any] = {
        "callbacks": [metrics],
    }
    if run_name:
        config["run_name"] = run_name

    t0 = time.time()
    try:
        result = agent.invoke({"input": prompt}, config=config)
        output = result.get("output", result)
        # Claude com tool-calling pode retornar AIMessage ou lista de content blocks
        if hasattr(output, "content"):
            raw_answer = output.content if isinstance(output.content, str) else str(output.content)
        elif isinstance(output, list):
            raw_answer = " ".join(
                (item.get("text", "") if isinstance(item, dict) else str(item))
                for item in output
            )
        else:
            raw_answer = str(output)
        
        # O Llama 3 local às vezes mistura "pensamentos" na saída em vez de rodar o tool JSON.
        # Vamos usar heurística para extrair apenas a resposta comercial consolidada (últimos parágrafos).
        if "sql_db_" in raw_answer or "A saída do" in raw_answer or "The output" in raw_answer or "As a result" in raw_answer:
            blocks = [b.strip() for b in raw_answer.split('\n\n') if b.strip()]
            clean_blocks = []
            for b in blocks:
                # Ignora tabelas formatadas em markdown, comandos SQL ou respostas falsas de tool
                if b.startswith("sql_db_") or b.startswith("```") or b.startswith("|") or b.startswith("+"):
                    continue
                if "A saída do" in b or "The output is" in b or "Tool call:" in b or "As a result" in b:
                    continue
                # Filtra blocos de resposta JSON crua deixados escapar pelo LLM
                if b.startswith("{") and b.endswith("}"):
                    continue
                clean_blocks.append(b)
            
            # Recupera apenas o ÚLTIMO bloco lógico como resposta final para garantir extrema precisão comercial
            answer = clean_blocks[-1] if clean_blocks else raw_answer
        else:
            answer = raw_answer
            
        # Salva o novo par Pergunta/Resposta no banco vetorial
        if answer and "sql_db_" not in answer:
            try:
                semantic_cache, _ = _get_semantic_cache()
                semantic_cache.add(
                    ids=[str(uuid.uuid4())],
                    documents=[prompt],             # embedding da pergunta
                    metadatas=[{"answer": answer}], # resposta nos metadados
                )
            except Exception:
                logger.warning("Falha ao salvar resposta no cache semântico.", exc_info=True)
            
        error = None
    except Exception as exc:
        answer = None
        error = str(exc)
    elapsed = int((time.time() - t0) * 1000)

    return {
        "answer": answer,
        "error": error,
        "latency_ms": elapsed,
        "total_tokens": metrics.total_tokens,
        "prompt_tokens": metrics.prompt_tokens,
        "completion_tokens": metrics.completion_tokens,
        "model": ANTHROPIC_MODEL if ANTHROPIC_API_KEY else (model or OPENAI_MODEL),
        "temperature": temperature,
    }


def list_langsmith_runs(limit: int = 20) -> list[dict]:
    """Busca os runs recentes do projeto no LangSmith."""
    if not LANGSMITH_API_KEY:
        return []
    try:
        client = LangSmithClient()
        runs = list(client.list_runs(
            project_name=LANGSMITH_PROJECT,
            limit=limit,
            is_root=True,
        ))
        out = []
        for r in runs:
            out.append({
                "id": str(r.id),
                "name": r.name or "–",
                "status": r.status,
                "latency_ms": int(r.total_tokens or 0),  # fallback
                "total_tokens": r.total_tokens or 0,
                "start_time": r.start_time.isoformat() if r.start_time else None,
                "error": r.error,
                "url": f"https://smith.langchain.com/o/public/projects/p/{r.session_id}/r/{r.id}"
                        if r.session_id else None,
            })
        return out
    except Exception as exc:
        return [{"error": str(exc)}]
