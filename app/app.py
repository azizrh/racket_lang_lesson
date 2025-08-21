from typing import List
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from pydantic_settings import BaseSettings
from psycopg_pool import AsyncConnectionPool
from fastapi.middleware.cors import CORSMiddleware
import httpx
import json




# --- settings ---
class Settings(BaseSettings):
    DATABASE_URL: str
    RACKET_RUNNER_URL: str
    class Config:
        env_file = ".env"

settings = Settings()
pool = AsyncConnectionPool(settings.DATABASE_URL, min_size=1, max_size=10, open=False)
app = FastAPI(title="S-Expression Lessons API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from typing import Any, Union, Optional

class RunnerResponse(BaseModel):
    ok: bool
    error: Optional[str] = None
    details: Optional[Union[dict[str, Any], str]] = None  # accept dict or str


# --- models ---
class LessonCreate(BaseModel):
    title: str
    body_md: str

class LessonOut(LessonCreate):
    id: int

class ProblemCreate(BaseModel):
    lesson_id: int
    prompt_text: str
    answer_text: str

class ProblemOut(ProblemCreate):
    id: int

# --- lifecycle ---
@app.on_event("startup")
async def on_startup():
    await pool.open()
    ddl = """
    CREATE TABLE IF NOT EXISTS lesson (
      id BIGSERIAL PRIMARY KEY,
      title TEXT NOT NULL UNIQUE,
      body_md TEXT NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS problem (
      id BIGSERIAL PRIMARY KEY,
      lesson_id BIGINT NOT NULL REFERENCES lesson(id) ON DELETE CASCADE,
      prompt_text TEXT NOT NULL,
      answer_text TEXT NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_problem_lesson_id ON problem(lesson_id);
    """
    async with pool.connection() as con:
        async with con.cursor() as cur:
            await cur.execute(ddl)

@app.on_event("shutdown")
async def on_shutdown():
    await pool.close()

# --- endpoints ---
@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/lessons", response_model=LessonOut)
async def create_lesson(payload: LessonCreate):
    q = "INSERT INTO lesson (title, body_md) VALUES (%s, %s) RETURNING id, title, body_md"
    async with pool.connection() as con:
        async with con.cursor() as cur:
            try:
                await cur.execute(q, (payload.title, payload.body_md))
                row = await cur.fetchone()
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))
    return LessonOut(id=row[0], title=row[1], body_md=row[2])

@app.get("/lessons/{lesson_id}", response_model=LessonOut)
async def get_lesson(lesson_id: int):
    q = "SELECT id, title, body_md FROM lesson WHERE id = %s"
    async with pool.connection() as con:
        async with con.cursor() as cur:
            await cur.execute(q, (lesson_id,))
            row = await cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Lesson not found")
    return LessonOut(id=row[0], title=row[1], body_md=row[2])

@app.post("/problems", response_model=ProblemOut)
async def create_problem(payload: ProblemCreate):
    async with pool.connection() as con:
        async with con.cursor() as cur:
            await cur.execute("SELECT 1 FROM lesson WHERE id = %s", (payload.lesson_id,))
            if not await cur.fetchone():
                raise HTTPException(status_code=404, detail="Lesson not found")
            q = """INSERT INTO problem (lesson_id, prompt_text, answer_text)
                   VALUES (%s, %s, %s)
                   RETURNING id, lesson_id, prompt_text, answer_text"""
            await cur.execute(q, (payload.lesson_id, payload.prompt_text, payload.answer_text))
            row = await cur.fetchone()
    return ProblemOut(id=row[0], lesson_id=row[1], prompt_text=row[2], answer_text=row[3])

@app.get("/lessons/{lesson_id}/problems", response_model=List[ProblemOut])
async def list_problems(lesson_id: int):
    q = """SELECT id, lesson_id, prompt_text, answer_text
           FROM problem WHERE lesson_id = %s ORDER BY id"""
    async with pool.connection() as con:
        async with con.cursor() as cur:
            await cur.execute(q, (lesson_id,))
            rows = await cur.fetchall()
    return [ProblemOut(id=r[0], lesson_id=r[1], prompt_text=r[2], answer_text=r[3]) for r in rows]

@app.get("/lessons")
async def list_lessons():
    q = "SELECT id, title, body_md FROM lesson ORDER BY id"
    async with pool.connection() as con:
        async with con.cursor() as cur:
            await cur.execute(q)
            rows = await cur.fetchall()
    return [{"id": r[0], "title": r[1], "body_md": r[2]} for r in rows]


@app.delete("/problems/{problem_id}")
async def delete_problem(problem_id: int):
    q = "DELETE FROM problem WHERE id = %s RETURNING id"
    async with pool.connection() as con:
        async with con.cursor() as cur:
            await cur.execute(q, (problem_id,))
            row = await cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Problem not found")
    return {"deleted_id": row[0]}


class ValidateReq(BaseModel):
    problem_id: int
    submission: str

@app.post("/validate")
async def validate(req: ValidateReq):
    # 1) Load problem + lesson to decide validator strategy
    q = """SELECT p.id, p.prompt_text, p.answer_text,
                  l.validator_default, l.validator_spec,
                  p.validator_kind, p.validator_spec
           FROM problem p
           JOIN lesson l ON l.id = p.lesson_id
           WHERE p.id = %s"""
    async with pool.connection() as con:
        async with con.cursor() as cur:
            await cur.execute(q, (req.problem_id,))
            row = await cur.fetchone()
            if not row:
                raise HTTPException(404, "Problem not found")
    (_pid, prompt, answer, l_def, l_spec, p_kind, p_spec) = row

    # Defaults if you haven't added these columns yet:
    l_def = l_def or "cfg"
    l_spec = l_spec or {}
    p_spec = p_spec or {}
    kind = p_kind or l_def

    # If CFG, do a simple strict match on backend as a fallback (you already do it client-side)
    if kind == "cfg":
        ok = (req.submission.strip() == answer.strip())
        return {"ok": bool(ok), "stage": "cfg",
                "error": None if ok else "answer mismatch",
                "details": {"expected": answer}}

    # Otherwise, call racket runner
    if kind == "racket":
        # Merge spec (lesson default < problem override)
        def merge(a, b):
            aa = a or {}
            bb = b or {}
            out = dict(aa)
            out.update(bb)
            return out

        spec = merge(l_spec, p_spec)
        payload = {
            "submission": req.submission,
            "mode": spec.get("mode", "parse"),
            "lang": spec.get("lang", "racket/base"),
            "time_ms": spec.get("time_ms", 200),
            "mem_mb": spec.get("mem_mb", 64),
            "tests": spec.get("tests", [])
        }
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                r = await client.post(f"{settings.RACKET_RUNNER_URL}/validate",
                                      content=json.dumps(payload),
                                      headers={"Content-Type": "application/json"})


            r.raise_for_status()
            data = r.json()
            if isinstance(data.get("details"), str):
                data["details"] = {"message": data["details"]}
            return data
        except Exception as e:
            raise HTTPException(400, f"racket runner error: {e}")

    raise HTTPException(400, f"Unknown validator kind: {kind}")

# app.py (add near other models)
from typing import Optional, Any, Dict
from pydantic import BaseModel

class AttemptIn(BaseModel):
    problem_id: int
    submitted_text: str
    is_correct: bool
    stage: Optional[str] = None
    error_reason: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

@app.post("/attempts")
async def create_attempt(a: AttemptIn):
    q = """INSERT INTO attempt (problem_id, submitted_text, is_correct, stage, error_reason, details_json)
           VALUES (%s, %s, %s, %s, %s, %s)
           RETURNING id, created_at"""
    async with pool.connection() as con:
        async with con.cursor() as cur:
            await cur.execute(q, (
                a.problem_id, a.submitted_text, a.is_correct,
                a.stage, a.error_reason, json.dumps(a.details) if a.details else None
            ))
            row = await cur.fetchone()
    return {"id": row[0], "created_at": row[1]}
