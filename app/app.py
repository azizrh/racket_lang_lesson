# # from typing import List
# # from fastapi import FastAPI, HTTPException
# # from pydantic import BaseModel
# # from pydantic_settings import BaseSettings
# # from psycopg_pool import AsyncConnectionPool
# # from fastapi.middleware.cors import CORSMiddleware
# # import httpx
# # import json




# # # --- settings ---
# # class Settings(BaseSettings):
# #     DATABASE_URL: str
# #     RACKET_RUNNER_URL: str
# #     class Config:
# #         env_file = ".env"

# # settings = Settings()
# # pool = AsyncConnectionPool(settings.DATABASE_URL, min_size=1, max_size=10, open=False)
# # app = FastAPI(title="S-Expression Lessons API", version="0.1.0")
# # app.add_middleware(
# #     CORSMiddleware,
# #     allow_origins=["*"],  # tighten in prod
# #     allow_credentials=True,
# #     allow_methods=["*"],
# #     allow_headers=["*"],
# # )

# # from typing import Any, Union, Optional

# # class RunnerResponse(BaseModel):
# #     ok: bool
# #     error: Optional[str] = None
# #     details: Optional[Union[dict[str, Any], str]] = None  # accept dict or str


# # # --- models ---
# # class LessonCreate(BaseModel):
# #     title: str
# #     body_md: str

# # class LessonOut(LessonCreate):
# #     id: int

# # class ProblemCreate(BaseModel):
# #     lesson_id: int
# #     prompt_text: str
# #     answer_text: str

# # class ProblemOut(ProblemCreate):
# #     id: int

# # # --- lifecycle ---
# # @app.on_event("startup")
# # async def on_startup():
# #     await pool.open()
# #     ddl = """
# #     CREATE TABLE IF NOT EXISTS lesson (
# #       id BIGSERIAL PRIMARY KEY,
# #       title TEXT NOT NULL UNIQUE,
# #       body_md TEXT NOT NULL,
# #       created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
# #     );
# #     CREATE TABLE IF NOT EXISTS problem (
# #       id BIGSERIAL PRIMARY KEY,
# #       lesson_id BIGINT NOT NULL REFERENCES lesson(id) ON DELETE CASCADE,
# #       prompt_text TEXT NOT NULL,
# #       answer_text TEXT NOT NULL,
# #       created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
# #     );
# #     CREATE INDEX IF NOT EXISTS idx_problem_lesson_id ON problem(lesson_id);
# #     """
# #     async with pool.connection() as con:
# #         async with con.cursor() as cur:
# #             await cur.execute(ddl)

# # @app.on_event("shutdown")
# # async def on_shutdown():
# #     await pool.close()

# # # --- endpoints ---
# # @app.get("/health")
# # async def health():
# #     return {"status": "ok"}

# # @app.post("/lessons", response_model=LessonOut)
# # async def create_lesson(payload: LessonCreate):
# #     q = "INSERT INTO lesson (title, body_md) VALUES (%s, %s) RETURNING id, title, body_md"
# #     async with pool.connection() as con:
# #         async with con.cursor() as cur:
# #             try:
# #                 await cur.execute(q, (payload.title, payload.body_md))
# #                 row = await cur.fetchone()
# #             except Exception as e:
# #                 raise HTTPException(status_code=400, detail=str(e))
# #     return LessonOut(id=row[0], title=row[1], body_md=row[2])

# # @app.get("/lessons/{lesson_id}", response_model=LessonOut)
# # async def get_lesson(lesson_id: int):
# #     q = "SELECT id, title, body_md FROM lesson WHERE id = %s"
# #     async with pool.connection() as con:
# #         async with con.cursor() as cur:
# #             await cur.execute(q, (lesson_id,))
# #             row = await cur.fetchone()
# #             if not row:
# #                 raise HTTPException(status_code=404, detail="Lesson not found")
# #     return LessonOut(id=row[0], title=row[1], body_md=row[2])

# # @app.post("/problems", response_model=ProblemOut)
# # async def create_problem(payload: ProblemCreate):
# #     async with pool.connection() as con:
# #         async with con.cursor() as cur:
# #             await cur.execute("SELECT 1 FROM lesson WHERE id = %s", (payload.lesson_id,))
# #             if not await cur.fetchone():
# #                 raise HTTPException(status_code=404, detail="Lesson not found")
# #             q = """INSERT INTO problem (lesson_id, prompt_text, answer_text)
# #                    VALUES (%s, %s, %s)
# #                    RETURNING id, lesson_id, prompt_text, answer_text"""
# #             await cur.execute(q, (payload.lesson_id, payload.prompt_text, payload.answer_text))
# #             row = await cur.fetchone()
# #     return ProblemOut(id=row[0], lesson_id=row[1], prompt_text=row[2], answer_text=row[3])

# # @app.get("/lessons/{lesson_id}/problems", response_model=List[ProblemOut])
# # async def list_problems(lesson_id: int):
# #     q = """SELECT id, lesson_id, prompt_text, answer_text
# #            FROM problem WHERE lesson_id = %s ORDER BY id"""
# #     async with pool.connection() as con:
# #         async with con.cursor() as cur:
# #             await cur.execute(q, (lesson_id,))
# #             rows = await cur.fetchall()
# #     return [ProblemOut(id=r[0], lesson_id=r[1], prompt_text=r[2], answer_text=r[3]) for r in rows]

# # @app.get("/lessons")
# # async def list_lessons():
# #     q = "SELECT id, title, body_md FROM lesson ORDER BY id"
# #     async with pool.connection() as con:
# #         async with con.cursor() as cur:
# #             await cur.execute(q)
# #             rows = await cur.fetchall()
# #     return [{"id": r[0], "title": r[1], "body_md": r[2]} for r in rows]


# # @app.delete("/problems/{problem_id}")
# # async def delete_problem(problem_id: int):
# #     q = "DELETE FROM problem WHERE id = %s RETURNING id"
# #     async with pool.connection() as con:
# #         async with con.cursor() as cur:
# #             await cur.execute(q, (problem_id,))
# #             row = await cur.fetchone()
# #             if not row:
# #                 raise HTTPException(status_code=404, detail="Problem not found")
# #     return {"deleted_id": row[0]}


# # class ValidateReq(BaseModel):
# #     problem_id: int
# #     submission: str

# # @app.post("/validate")
# # async def validate(req: ValidateReq):
# #     # 1) Load problem + lesson to decide validator strategy
# #     q = """SELECT p.id, p.prompt_text, p.answer_text,
# #                   l.validator_default, l.validator_spec,
# #                   p.validator_kind, p.validator_spec
# #            FROM problem p
# #            JOIN lesson l ON l.id = p.lesson_id
# #            WHERE p.id = %s"""
# #     async with pool.connection() as con:
# #         async with con.cursor() as cur:
# #             await cur.execute(q, (req.problem_id,))
# #             row = await cur.fetchone()
# #             if not row:
# #                 raise HTTPException(404, "Problem not found")
# #     (_pid, prompt, answer, l_def, l_spec, p_kind, p_spec) = row

# #     # Defaults if you haven't added these columns yet:
# #     l_def = l_def or "cfg"
# #     l_spec = l_spec or {}
# #     p_spec = p_spec or {}
# #     kind = p_kind or l_def

# #     # If CFG, do a simple strict match on backend as a fallback (you already do it client-side)
# #     if kind == "cfg":
# #         ok = (req.submission.strip() == answer.strip())
# #         return {"ok": bool(ok), "stage": "cfg",
# #                 "error": None if ok else "answer mismatch",
# #                 "details": {"expected": answer}}

# #     # Otherwise, call racket runner
# #     if kind == "racket":
# #         # Merge spec (lesson default < problem override)
# #         def merge(a, b):
# #             aa = a or {}
# #             bb = b or {}
# #             out = dict(aa)
# #             out.update(bb)
# #             return out

# #         spec = merge(l_spec, p_spec)
# #         payload = {
# #             "submission": req.submission,
# #             "mode": spec.get("mode", "parse"),
# #             "lang": spec.get("lang", "racket/base"),
# #             "time_ms": spec.get("time_ms", 200),
# #             "mem_mb": spec.get("mem_mb", 64),
# #             "tests": spec.get("tests", [])
# #         }
# #         try:
# #             async with httpx.AsyncClient(timeout=3.0) as client:
# #                 r = await client.post(f"{settings.RACKET_RUNNER_URL}/validate",
# #                                       content=json.dumps(payload),
# #                                       headers={"Content-Type": "application/json"})


# #             r.raise_for_status()
# #             data = r.json()
# #             if isinstance(data.get("details"), str):
# #                 data["details"] = {"message": data["details"]}
# #             return data
# #         except Exception as e:
# #             raise HTTPException(400, f"racket runner error: {e}")

# #     raise HTTPException(400, f"Unknown validator kind: {kind}")

# # # app.py (add near other models)
# # from typing import Optional, Any, Dict
# # from pydantic import BaseModel

# # class AttemptIn(BaseModel):
# #     problem_id: int
# #     submitted_text: str
# #     is_correct: bool
# #     stage: Optional[str] = None
# #     error_reason: Optional[str] = None
# #     details: Optional[Dict[str, Any]] = None

# # @app.post("/attempts")
# # async def create_attempt(a: AttemptIn):
# #     q = """INSERT INTO attempt (problem_id, submitted_text, is_correct, stage, error_reason, details_json)
# #            VALUES (%s, %s, %s, %s, %s, %s)
# #            RETURNING id, created_at"""
# #     async with pool.connection() as con:
# #         async with con.cursor() as cur:
# #             await cur.execute(q, (
# #                 a.problem_id, a.submitted_text, a.is_correct,
# #                 a.stage, a.error_reason, json.dumps(a.details) if a.details else None
# #             ))
# #             row = await cur.fetchone()
# #     return {"id": row[0], "created_at": row[1]}


# from typing import List, Optional, Any, Dict, Union
# from fastapi import FastAPI, HTTPException
# from fastapi.middleware.cors import CORSMiddleware
# from pydantic import BaseModel
# from pydantic_settings import BaseSettings
# from psycopg_pool import AsyncConnectionPool
# import httpx
# import json

# # --- settings ---
# class Settings(BaseSettings):
#     DATABASE_URL: str
#     RACKET_RUNNER_URL: str
#     class Config:
#         env_file = ".env"

# settings = Settings()

# # Global async connection pool
# pool = AsyncConnectionPool(settings.DATABASE_URL, min_size=1, max_size=10, open=False)

# # --- app ---
# app = FastAPI(title="S-Expression Lessons API", version="0.1.0")
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],  # tighten in prod
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# # --- pydantic models ---
# class LessonCreate(BaseModel):
#     title: str
#     body_md: str

# class LessonOut(LessonCreate):
#     id: int

# class ProblemCreate(BaseModel):
#     lesson_id: int
#     prompt_text: str
#     answer_text: str

# class ProblemOut(ProblemCreate):
#     id: int

# class ValidateReq(BaseModel):
#     problem_id: int
#     submission: str

# class AttemptIn(BaseModel):
#     problem_id: int
#     submitted_text: str
#     is_correct: bool
#     stage: Optional[str] = None
#     error_reason: Optional[str] = None
#     details: Optional[Dict[str, Any]] = None

# class UserCreate(BaseModel):
#     # Optional override; if omitted we pick the first lesson
#     active_lesson: Optional[int] = None

# class UserOut(BaseModel):
#     user_id: int
#     active_lesson: Optional[int]
#     lessons: List[int]

# # --- lifecycle ---
# @app.on_event("startup")
# async def on_startup():
#     await pool.open()

#     # DDL: lessons, problems, attempts, users
#     ddl = """
#     -- LESSON
#     CREATE TABLE IF NOT EXISTS lesson (
#       id BIGSERIAL PRIMARY KEY,
#       title TEXT NOT NULL UNIQUE,
#       body_md TEXT NOT NULL,
#       created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
#       -- validator defaults (used by /validate)
#       validator_default TEXT NOT NULL DEFAULT 'cfg',
#       validator_spec JSONB NOT NULL DEFAULT '{}'::jsonb
#     );

#     -- PROBLEM
#     CREATE TABLE IF NOT EXISTS problem (
#       id BIGSERIAL PRIMARY KEY,
#       lesson_id BIGINT NOT NULL REFERENCES lesson(id) ON DELETE CASCADE,
#       prompt_text TEXT NOT NULL,
#       answer_text TEXT NOT NULL,
#       created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
#       validator_kind TEXT NULL,
#       validator_spec JSONB NULL
#     );
#     CREATE INDEX IF NOT EXISTS idx_problem_lesson_id ON problem(lesson_id);

#     -- ATTEMPT
#     CREATE TABLE IF NOT EXISTS attempt (
#       id BIGSERIAL PRIMARY KEY,
#       problem_id BIGINT NOT NULL REFERENCES problem(id) ON DELETE CASCADE,
#       submitted_text TEXT NOT NULL,
#       is_correct BOOLEAN NOT NULL,
#       stage TEXT NULL,
#       error_reason TEXT NULL,
#       details_json JSONB NULL,
#       created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
#     );
#     CREATE INDEX IF NOT EXISTS attempt_problem_id_created_at_idx
#       ON attempt (problem_id, created_at DESC);

#     -- USER (array-based lessons)
#     CREATE TABLE IF NOT EXISTS public."user" (
#       user_id        BIGSERIAL PRIMARY KEY,
#       active_lesson  BIGINT NULL REFERENCES lesson(id) ON DELETE SET NULL,
#       lessons        BIGINT[] NOT NULL DEFAULT '{}',
#       created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
#       CONSTRAINT user_active_in_lessons_chk
#         CHECK (active_lesson IS NULL OR active_lesson = ANY (lessons))
#     );
#     CREATE INDEX IF NOT EXISTS idx_user_active_lesson ON public."user"(active_lesson);
#     CREATE INDEX IF NOT EXISTS idx_user_lessons_gin ON public."user" USING GIN (lessons);
#     """
#     async with pool.connection() as con:
#         async with con.cursor() as cur:
#             await cur.execute(ddl)
#         await con.commit()

# @app.on_event("shutdown")
# async def on_shutdown():
#     await pool.close()

# # --- health ---
# @app.get("/health")
# async def health():
#     return {"status": "ok"}

# # --- lesson endpoints ---
# @app.post("/lessons", response_model=LessonOut)
# async def create_lesson(payload: LessonCreate):
#     q = "INSERT INTO lesson (title, body_md) VALUES (%s, %s) RETURNING id, title, body_md"
#     async with pool.connection() as con:
#         async with con.cursor() as cur:
#             try:
#                 await cur.execute(q, (payload.title, payload.body_md))
#                 row = await cur.fetchone()
#             except Exception as e:
#                 raise HTTPException(status_code=400, detail=str(e))
#         await con.commit()
#     return LessonOut(id=row[0], title=row[1], body_md=row[2])

# @app.get("/lessons/{lesson_id}", response_model=LessonOut)
# async def get_lesson(lesson_id: int):
#     q = "SELECT id, title, body_md FROM lesson WHERE id = %s"
#     async with pool.connection() as con:
#         async with con.cursor() as cur:
#             await cur.execute(q, (lesson_id,))
#             row = await cur.fetchone()
#             if not row:
#                 raise HTTPException(status_code=404, detail="Lesson not found")
#     return LessonOut(id=row[0], title=row[1], body_md=row[2])

# @app.get("/lessons")
# async def list_lessons():
#     q = "SELECT id, title, body_md FROM lesson ORDER BY id"
#     async with pool.connection() as con:
#         async with con.cursor() as cur:
#             await cur.execute(q)
#             rows = await cur.fetchall()
#     return [{"id": r[0], "title": r[1], "body_md": r[2]} for r in rows]

# # --- problem endpoints ---
# @app.post("/problems", response_model=ProblemOut)
# async def create_problem(payload: ProblemCreate):
#     async with pool.connection() as con:
#         async with con.cursor() as cur:
#             # ensure lesson exists
#             await cur.execute("SELECT 1 FROM lesson WHERE id = %s", (payload.lesson_id,))
#             if not await cur.fetchone():
#                 raise HTTPException(status_code=404, detail="Lesson not found")
#             q = """INSERT INTO problem (lesson_id, prompt_text, answer_text)
#                    VALUES (%s, %s, %s)
#                    RETURNING id, lesson_id, prompt_text, answer_text"""
#             await cur.execute(q, (payload.lesson_id, payload.prompt_text, payload.answer_text))
#             row = await cur.fetchone()
#         await con.commit()
#     return ProblemOut(id=row[0], lesson_id=row[1], prompt_text=row[2], answer_text=row[3])

# @app.get("/lessons/{lesson_id}/problems", response_model=List[ProblemOut])
# async def list_problems(lesson_id: int):
#     q = """SELECT id, lesson_id, prompt_text, answer_text
#            FROM problem WHERE lesson_id = %s ORDER BY id"""
#     async with pool.connection() as con:
#         async with con.cursor() as cur:
#             await cur.execute(q, (lesson_id,))
#             rows = await cur.fetchall()
#     return [ProblemOut(id=r[0], lesson_id=r[1], prompt_text=r[2], answer_text=r[3]) for r in rows]

# @app.delete("/problems/{problem_id}")
# async def delete_problem(problem_id: int):
#     q = "DELETE FROM problem WHERE id = %s RETURNING id"
#     async with pool.connection() as con:
#         async with con.cursor() as cur:
#             await cur.execute(q, (problem_id,))
#             row = await cur.fetchone()
#             if not row:
#                 raise HTTPException(status_code=404, detail="Problem not found")
#         await con.commit()
#     return {"deleted_id": row[0]}

# # --- validate endpoint ---
# @app.post("/validate")
# async def validate(req: ValidateReq):
#     # 1) Load problem + lesson to decide validator strategy
#     q = """SELECT p.id, p.prompt_text, p.answer_text,
#                   l.validator_default, l.validator_spec,
#                   p.validator_kind, p.validator_spec
#            FROM problem p
#            JOIN lesson l ON l.id = p.lesson_id
#            WHERE p.id = %s"""
#     async with pool.connection() as con:
#         async with con.cursor() as cur:
#             await cur.execute(q, (req.problem_id,))
#             row = await cur.fetchone()
#             if not row:
#                 raise HTTPException(404, "Problem not found")

#     (_pid, prompt, answer, l_def, l_spec, p_kind, p_spec) = row
#     l_def = l_def or "cfg"
#     l_spec = l_spec or {}
#     p_spec = p_spec or {}
#     kind = p_kind or l_def

#     # Simple builtin "cfg": strict text match
#     if kind == "cfg":
#         ok = (req.submission.strip() == answer.strip())
#         return {"ok": bool(ok), "stage": "cfg",
#                 "error": None if ok else "answer mismatch",
#                 "details": {"expected": answer}}

#     # External "racket" runner
#     if kind == "racket":
#         def merge(a, b):
#             aa = a or {}
#             bb = b or {}
#             out = dict(aa)
#             out.update(bb)
#             return out

#         spec = merge(l_spec, p_spec)
#         payload = {
#             "submission": req.submission,
#             "mode": spec.get("mode", "parse"),
#             "lang": spec.get("lang", "racket/base"),
#             "time_ms": spec.get("time_ms", 200),
#             "mem_mb": spec.get("mem_mb", 64),
#             "tests": spec.get("tests", [])
#         }
#         try:
#             async with httpx.AsyncClient(timeout=3.0) as client:
#                 r = await client.post(
#                     f"{settings.RACKET_RUNNER_URL}/validate",
#                     content=json.dumps(payload),
#                     headers={"Content-Type": "application/json"},
#                 )
#             r.raise_for_status()
#             data = r.json()
#             if isinstance(data.get("details"), str):
#                 data["details"] = {"message": data["details"]}
#             return data
#         except Exception as e:
#             raise HTTPException(400, f"racket runner error: {e}")

#     raise HTTPException(400, f"Unknown validator kind: {kind}")

# # --- attempts endpoint ---
# @app.post("/attempts")
# async def create_attempt(a: AttemptIn):
#     q = """INSERT INTO attempt (problem_id, submitted_text, is_correct, stage, error_reason, details_json)
#            VALUES (%s, %s, %s, %s, %s, %s)
#            RETURNING id, created_at"""
#     async with pool.connection() as con:
#         async with con.cursor() as cur:
#             await cur.execute(q, (
#                 a.problem_id,
#                 a.submitted_text,
#                 a.is_correct,
#                 a.stage,
#                 a.error_reason,
#                 json.dumps(a.details) if a.details is not None else None
#             ))
#             row = await cur.fetchone()
#         await con.commit()
#     return {"id": row[0], "created_at": row[1]}

# # --- user endpoints ---
# @app.post("/users", response_model=UserOut)
# async def create_user(payload: Optional[UserCreate] = None):
#     """
#     Create a user with:
#       - active_lesson = provided lesson if valid, else earliest (created_at, then id)
#       - lessons = [active_lesson]
#     """
#     async with pool.connection() as con:
#         async with con.cursor() as cur:
#             if payload and payload.active_lesson is not None:
#                 await cur.execute("SELECT id FROM lesson WHERE id = %s", (payload.active_lesson,))
#                 row = await cur.fetchone()
#                 if not row:
#                     raise HTTPException(status_code=404, detail="active_lesson not found")
#                 active = payload.active_lesson
#             else:
#                 await cur.execute("""
#                     SELECT id
#                     FROM lesson
#                     ORDER BY created_at ASC, id ASC
#                     LIMIT 1
#                 """)
#                 row = await cur.fetchone()
#                 if not row:
#                     raise HTTPException(status_code=400, detail="No lessons exist yet")
#                 active = row[0]

#             await cur.execute("""
#                 INSERT INTO public."user" (active_lesson, lessons)
#                 VALUES (%s, ARRAY[%s]::bigint[])
#                 RETURNING user_id, active_lesson, lessons
#             """, (active, active))
#             uid, a, ls = await cur.fetchone()
#         await con.commit()

#     return UserOut(user_id=uid, active_lesson=a, lessons=ls)

# @app.get("/users/{user_id}", response_model=UserOut)
# async def get_user(user_id: int):
#     q = """SELECT user_id, active_lesson, lessons
#            FROM public."user"
#            WHERE user_id = %s"""
#     async with pool.connection() as con:
#         async with con.cursor() as cur:
#             await cur.execute(q, (user_id,))
#             row = await cur.fetchone()
#             if not row:
#                 raise HTTPException(status_code=404, detail="User not found")
#     return UserOut(user_id=row[0], active_lesson=row[1], lessons=row[2])

# @app.get("/users")
# async def list_users():
#     q = 'SELECT user_id, active_lesson, lessons FROM public."user" ORDER BY user_id'
#     async with pool.connection() as con:
#         async with con.cursor() as cur:
#             await cur.execute(q)
#             rows = await cur.fetchall()
#     return [{"user_id": r[0], "active_lesson": r[1], "lessons": r[2]} for r in rows]
from typing import List, Optional, Any, Dict, Union
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pydantic_settings import BaseSettings
from psycopg_pool import AsyncConnectionPool
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

# --- app ---
app = FastAPI(title="S-Expression Lessons API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

class ValidateReq(BaseModel):
    problem_id: int
    submission: str

class AttemptIn(BaseModel):
    user_id: Optional[int] = None   # NEW: tie attempts to a user
    problem_id: int
    submitted_text: str
    is_correct: bool
    stage: Optional[str] = None
    error_reason: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

class UserCreate(BaseModel):
    active_lesson: Optional[int] = None

class UserOut(BaseModel):
    user_id: int
    active_lesson: Optional[int]
    lessons: List[int]

# --- lifecycle ---
@app.on_event("startup")
async def on_startup():
    await pool.open()
    ddl = """
    -- LESSON
    CREATE TABLE IF NOT EXISTS lesson (
      id BIGSERIAL PRIMARY KEY,
      title TEXT NOT NULL UNIQUE,
      body_md TEXT NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      validator_default TEXT NOT NULL DEFAULT 'cfg',
      validator_spec JSONB NOT NULL DEFAULT '{}'::jsonb
    );

    -- PROBLEM
    CREATE TABLE IF NOT EXISTS problem (
      id BIGSERIAL PRIMARY KEY,
      lesson_id BIGINT NOT NULL REFERENCES lesson(id) ON DELETE CASCADE,
      prompt_text TEXT NOT NULL,
      answer_text TEXT NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      validator_kind TEXT NULL,
      validator_spec JSONB NULL
    );
    CREATE INDEX IF NOT EXISTS idx_problem_lesson_id ON problem(lesson_id);

    -- USER (array-based)
    CREATE TABLE IF NOT EXISTS public."user" (
      user_id        BIGSERIAL PRIMARY KEY,
      active_lesson  BIGINT NULL REFERENCES lesson(id) ON DELETE SET NULL,
      lessons        BIGINT[] NOT NULL DEFAULT '{}',
      created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      CONSTRAINT user_active_in_lessons_chk
        CHECK (active_lesson IS NULL OR active_lesson = ANY (lessons))
    );
    CREATE INDEX IF NOT EXISTS idx_user_active_lesson ON public."user"(active_lesson);
    CREATE INDEX IF NOT EXISTS idx_user_lessons_gin ON public."user" USING GIN (lessons);

    -- ATTEMPT
    CREATE TABLE IF NOT EXISTS attempt (
      id BIGSERIAL PRIMARY KEY,
      problem_id BIGINT NOT NULL REFERENCES problem(id) ON DELETE CASCADE,
      submitted_text TEXT NOT NULL,
      is_correct BOOLEAN NOT NULL,
      stage TEXT NULL,
      error_reason TEXT NULL,
      details_json JSONB NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS attempt_problem_id_created_at_idx
      ON attempt (problem_id, created_at DESC);

    -- NEW: tie attempts to users (nullable for backward compatibility)
    ALTER TABLE attempt
      ADD COLUMN IF NOT EXISTS user_id BIGINT
        REFERENCES public."user"(user_id) ON DELETE CASCADE;

    CREATE INDEX IF NOT EXISTS attempt_user_created_at_idx
      ON attempt (user_id, created_at DESC);
    """
    async with pool.connection() as con:
        async with con.cursor() as cur:
            await cur.execute(ddl)
        await con.commit()

@app.on_event("shutdown")
async def on_shutdown():
    await pool.close()

# --- health ---
@app.get("/health")
async def health():
    return {"status": "ok"}

# --- lessons ---
@app.post("/lessons", response_model=LessonOut)
async def create_lesson(payload: LessonCreate):
    q = "INSERT INTO lesson (title, body_md) VALUES (%s, %s) RETURNING id, title, body_md"
    async with pool.connection() as con:
        async with con.cursor() as cur:
            try:
                await cur.execute(q, (payload.title, payload.body_md))
                row = await cur.fetchone()
            except Exception as e:
                raise HTTPException(400, str(e))
        await con.commit()
    return LessonOut(id=row[0], title=row[1], body_md=row[2])

@app.get("/lessons/{lesson_id}", response_model=LessonOut)
async def get_lesson(lesson_id: int):
    q = "SELECT id, title, body_md FROM lesson WHERE id = %s"
    async with pool.connection() as con:
        async with con.cursor() as cur:
            await cur.execute(q, (lesson_id,))
            row = await cur.fetchone()
            if not row:
                raise HTTPException(404, "Lesson not found")
    return LessonOut(id=row[0], title=row[1], body_md=row[2])

@app.get("/lessons")
async def list_lessons():
    q = "SELECT id, title, body_md FROM lesson ORDER BY created_at ASC, id ASC"
    async with pool.connection() as con:
        async with con.cursor() as cur:
            await cur.execute(q)
            rows = await cur.fetchall()
    return [{"id": r[0], "title": r[1], "body_md": r[2]} for r in rows]

# --- problems ---
@app.post("/problems", response_model=ProblemOut)
async def create_problem(payload: ProblemCreate):
    async with pool.connection() as con:
        async with con.cursor() as cur:
            await cur.execute("SELECT 1 FROM lesson WHERE id = %s", (payload.lesson_id,))
            if not await cur.fetchone():
                raise HTTPException(404, "Lesson not found")
            q = """INSERT INTO problem (lesson_id, prompt_text, answer_text)
                   VALUES (%s, %s, %s)
                   RETURNING id, lesson_id, prompt_text, answer_text"""
            await cur.execute(q, (payload.lesson_id, payload.prompt_text, payload.answer_text))
            row = await cur.fetchone()
        await con.commit()
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

@app.delete("/problems/{problem_id}")
async def delete_problem(problem_id: int):
    q = "DELETE FROM problem WHERE id = %s RETURNING id"
    async with pool.connection() as con:
        async with con.cursor() as cur:
            await cur.execute(q, (problem_id,))
            row = await cur.fetchone()
            if not row:
                raise HTTPException(404, "Problem not found")
        await con.commit()
    return {"deleted_id": row[0]}

# --- validate ---
@app.post("/validate")
async def validate(req: ValidateReq):
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

    (_pid, _prompt, answer, l_def, l_spec, p_kind, p_spec) = row
    l_def = l_def or "cfg"
    l_spec = l_spec or {}
    p_spec = p_spec or {}
    kind = p_kind or l_def

    if kind == "cfg":
        ok = (req.submission.strip() == answer.strip())
        return {"ok": bool(ok), "stage": "cfg",
                "error": None if ok else "answer mismatch",
                "details": {"expected": answer}}

    if kind == "racket":
        def merge(a, b):
            aa = a or {}
            bb = b or {}
            out = dict(aa); out.update(bb); return out
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
                r = await client.post(
                    f"{settings.RACKET_RUNNER_URL}/validate",
                    content=json.dumps(payload),
                    headers={"Content-Type": "application/json"},
                )
            r.raise_for_status()
            data = r.json()
            if isinstance(data.get("details"), str):
                data["details"] = {"message": data["details"]}
            return data
        except Exception as e:
            raise HTTPException(400, f"racket runner error: {e}")

    raise HTTPException(400, f"Unknown validator kind: {kind}")

# --- attempts ---
@app.post("/attempts")
async def create_attempt(a: AttemptIn):
    q = """INSERT INTO attempt (user_id, problem_id, submitted_text, is_correct, stage, error_reason, details_json)
           VALUES (%s, %s, %s, %s, %s, %s, %s)
           RETURNING id, created_at"""
    async with pool.connection() as con:
        async with con.cursor() as cur:
            await cur.execute(q, (
                a.user_id, a.problem_id, a.submitted_text, a.is_correct,
                a.stage, a.error_reason, json.dumps(a.details) if a.details is not None else None
            ))
            row = await cur.fetchone()
        await con.commit()
    return {"id": row[0], "created_at": row[1]}

# --- users ---
@app.post("/users", response_model=UserOut)
async def create_user(payload: Optional[UserCreate] = None):
    async with pool.connection() as con:
        async with con.cursor() as cur:
            if payload and payload.active_lesson is not None:
                await cur.execute("SELECT id FROM lesson WHERE id = %s", (payload.active_lesson,))
                r = await cur.fetchone()
                if not r:
                    raise HTTPException(404, "active_lesson not found")
                active = payload.active_lesson
            else:
                await cur.execute("""SELECT id FROM lesson ORDER BY created_at ASC, id ASC LIMIT 1""")
                r = await cur.fetchone()
                if not r:
                    raise HTTPException(400, "No lessons exist yet")
                active = r[0]

            await cur.execute("""
                INSERT INTO public."user" (active_lesson, lessons)
                VALUES (%s, ARRAY[%s]::bigint[])
                RETURNING user_id, active_lesson, lessons
            """, (active, active))
            uid, a, ls = await cur.fetchone()
        await con.commit()
    return UserOut(user_id=uid, active_lesson=a, lessons=ls)

@app.get("/users/{user_id}", response_model=UserOut)
async def get_user(user_id: int):
    q = 'SELECT user_id, active_lesson, lessons FROM public."user" WHERE user_id = %s'
    async with pool.connection() as con:
        async with con.cursor() as cur:
            await cur.execute(q, (user_id,))
            row = await cur.fetchone()
            if not row:
                raise HTTPException(404, "User not found")
    return UserOut(user_id=row[0], active_lesson=row[1], lessons=row[2])

# --- NEW: advance user to next lesson IF 3-in-a-row correct on active lesson ---
@app.post("/users/{user_id}/advance", response_model=UserOut)
async def advance_user_to_next_lesson(user_id: int):
    async with pool.connection() as con:
        async with con.cursor() as cur:
            # Load user
            await cur.execute('SELECT user_id, active_lesson, lessons FROM public."user" WHERE user_id = %s', (user_id,))
            user = await cur.fetchone()
            if not user:
                raise HTTPException(404, "User not found")
            _uid, active_lesson, lessons = user
            if active_lesson is None:
                raise HTTPException(400, "User has no active lesson")

            # Verify 3-in-a-row on active lesson (server-authoritative)
            await cur.execute("""
              SELECT a.is_correct
              FROM attempt a
              JOIN problem p ON p.id = a.problem_id
              WHERE a.user_id = %s AND p.lesson_id = %s
              ORDER BY a.created_at DESC, a.id DESC
              LIMIT 3
            """, (user_id, active_lesson))
            rows = await cur.fetchall()
            if len(rows) < 3 or not all(r[0] for r in rows):
                raise HTTPException(403, "Unlock requires 3 correct attempts in a row on the current lesson")

            # Determine "next" lesson in global order
            await cur.execute("""SELECT id FROM lesson ORDER BY created_at ASC, id ASC""")
            all_lessons = [r[0] for r in await cur.fetchall()]
            if active_lesson not in all_lessons:
                raise HTTPException(400, "Active lesson not found in lesson list")
            idx = all_lessons.index(active_lesson)
            if idx == len(all_lessons) - 1:
                raise HTTPException(400, "No next lesson to advance to")

            next_lesson = all_lessons[idx + 1]

            # Update user: set active_lesson and append to lessons[] if missing
            await cur.execute("""
              UPDATE public."user"
              SET active_lesson = %s,
                  lessons = CASE
                      WHEN NOT (%s = ANY(lessons)) THEN array_append(lessons, %s)
                      ELSE lessons
                  END
              WHERE user_id = %s
              RETURNING user_id, active_lesson, lessons
            """, (next_lesson, next_lesson, next_lesson, user_id))
            updated = await cur.fetchone()
        await con.commit()

    return UserOut(user_id=updated[0], active_lesson=updated[1], lessons=updated[2])
