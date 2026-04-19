"""
FastAPI – API REST do lang_chat.
Endpoints:
  GET  /                      → serve o frontend (index.html)
  GET  /api/health            → healthcheck
  POST /api/prompt            → executa um prompt no agente SQL
  POST /api/tts               → converte texto em áudio via ElevenLabs
  GET  /api/tables            → lista tabelas do banco
  GET  /api/sample/{table}    → amostra de dados de uma tabela
  GET  /api/runs              → runs recentes no LangSmith
  GET  /api/config            → configuração atual (mascarada)
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pathlib import Path
import os
import re

from app.config import DEFAULT_DB_URL, LANGSMITH_API_KEY, LANGSMITH_PROJECT, OPENAI_MODEL, ELEVENLABS_API_KEY
from app.database import list_tables, get_table_sample, seed_demo_db
from app.agent import run_prompt, list_langsmith_runs
from app.warmup import seed_demo_cache, warmup_agent


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    if DEFAULT_DB_URL.startswith("sqlite"):
        seed_demo_db(DEFAULT_DB_URL)
    seed_demo_cache(DEFAULT_DB_URL)
    yield
    # Shutdown (nada por enquanto)


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="LangChat – Prompt Tester", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

# Serve arquivos estáticos do frontend
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


# ── Schemas ───────────────────────────────────────────────────────────────────
class PromptRequest(BaseModel):
    prompt: str = Field(..., min_length=3)
    db_url: str = Field(default="")
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    model: str = Field(default="")
    run_name: str = Field(default="")


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)
    voice_id: str = Field(default="cgSgspJ2msm6clMCkdW9")  # Jessica - PT friendly


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def serve_frontend():
    index = FRONTEND_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return JSONResponse({"message": "Frontend not found – serve index.html from /frontend"})


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "langsmith_configured": bool(LANGSMITH_API_KEY),
        "default_db": DEFAULT_DB_URL.split("///")[-1] if "///" in DEFAULT_DB_URL else DEFAULT_DB_URL,
    }


@app.post("/api/prompt")
async def execute_prompt(body: PromptRequest):
    db_url = body.db_url.strip() or DEFAULT_DB_URL
    try:
        result = run_prompt(
            db_url=db_url,
            prompt=body.prompt,
            temperature=body.temperature,
            model=body.model or None,
            run_name=body.run_name or body.prompt[:60],
        )
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/tts")
async def text_to_speech(body: TTSRequest):
    if not ELEVENLABS_API_KEY:
        raise HTTPException(status_code=503, detail="ElevenLabs não configurado")
    try:
        from elevenlabs import ElevenLabs
        client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
        # Remove markdown e emojis antes de enviar
        clean = re.sub(r"[*_~`#\[\]>]", "", body.text)
        clean = re.sub(r"[\U0001F000-\U0001FFFF]", "", clean).strip()
        audio = client.text_to_speech.convert(
            voice_id=body.voice_id,
            text=clean,
            model_id="eleven_multilingual_v2",
            output_format="mp3_44100_128",
        )
        def stream():
            for chunk in audio:
                yield chunk
        return StreamingResponse(stream(), media_type="audio/mpeg")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/tables")
async def get_tables(db_url: str = Query(default="")):
    url = db_url.strip() or DEFAULT_DB_URL
    try:
        return {"tables": list_tables(url)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/sample/{table}")
async def table_sample(
    table: str,
    db_url: str = Query(default=""),
    limit: int = Query(default=5, le=100),
):
    url = db_url.strip() or DEFAULT_DB_URL
    try:
        rows = get_table_sample(url, table, limit=limit)
        return {"table": table, "rows": rows, "count": len(rows)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/warmup")
async def trigger_warmup(background_tasks: BackgroundTasks, db_url: str = Query(default="")):
    url = db_url.strip() or DEFAULT_DB_URL
    background_tasks.add_task(warmup_agent, url)
    return {"status": "warmup iniciado em background", "db_url": url}


@app.get("/api/runs")
async def get_runs(limit: int = Query(default=20, le=100)):
    runs = list_langsmith_runs(limit=limit)
    return {"runs": runs, "project": LANGSMITH_PROJECT}


@app.get("/api/config")
async def get_config():
    return {
        "model": OPENAI_MODEL,
        "langsmith_project": LANGSMITH_PROJECT,
        "langsmith_configured": bool(LANGSMITH_API_KEY),
        "openai_configured": bool(os.getenv("OPENAI_API_KEY")),
        "default_db": DEFAULT_DB_URL.split("///")[-1] if "///" in DEFAULT_DB_URL else DEFAULT_DB_URL,
    }
