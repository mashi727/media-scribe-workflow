"""API（Cloudflare Tunnel → 127.0.0.1:8787）

フロント（differance-lab.tokyo の固定ページ）から fetch(credentials: 'include') で呼ぶ。
api.differance-lab.tokyo は同じサイト（registrable domain）なので、Access の
CF_Authorization Cookie は SameSite=Lax のままで送られる。オリジンは違うので CORS は要る。

アップロードは Cloudflare の本体サイズ上限（100MB）を避けるため、
offset 付きの PUT を何回かに分けて受ける（途中から再開できる）。

    POST   /api/jobs                       ジョブを作る（前提情報・ファイル名・サイズ）
    PUT    /api/jobs/{id}/input?offset=N   音声を追記（N は現在の受信済みバイト数）
    PUT    /api/jobs/{id}/chapters         章立て .txt（任意）
    POST   /api/jobs/{id}/submit           受信完了 → queued
    GET    /api/jobs | /api/jobs/{id}      一覧・状態
    GET    /api/jobs/{id}/files/{name}     成果物
    DELETE /api/jobs/{id}                  ジョブと全ファイルを消す
"""
from __future__ import annotations

import re
import shutil
import time
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field

from . import auth
from .config import Settings, get_settings
from .db import JobStore

# 成果物として外へ出してよいファイル（ジョブディレクトリ内の名前）
DOWNLOADABLE = {
    "report.pdf": "application/pdf",
    "report.tex": "application/x-tex",
    "report.json": "application/json",
    "transcript.srt": "application/x-subrip",
}
AUDIO_EXT = re.compile(r"\.(wav|flac|m4a|mp3|aac|ogg|opus|mp4|mov|mkv|webm)$", re.IGNORECASE)

settings = get_settings()
_store: JobStore | None = None

app = FastAPI(title="media-scribe-workflow API", docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type"],
    max_age=600,
)


def get_store() -> JobStore:
    global _store
    if _store is None:
        _store = JobStore(settings.db_path)
    return _store


def get_cfg() -> Settings:
    return settings


def user(request: Request, cfg: Annotated[Settings, Depends(get_cfg)]) -> str:
    return auth.current_email(request, cfg)


Email = Annotated[str, Depends(user)]
Store = Annotated[JobStore, Depends(get_store)]
Cfg = Annotated[Settings, Depends(get_cfg)]


class JobCreate(BaseModel):
    filename: str = Field(max_length=255)
    size: int = Field(gt=0)
    title: str = Field(default="", max_length=200)
    date: str = Field(default="", max_length=40)
    ensemble: str = Field(default="", max_length=200)
    conductor: str = Field(default="", max_length=200)
    pieces: list[str] = Field(default_factory=list, max_length=40)
    concert: str = Field(default="", max_length=200)
    author: str = Field(default="", max_length=200)
    viewpoint: str = Field(default="", max_length=200)


def job_dir(cfg: Settings, job_id: str) -> Path:
    return cfg.jobs_dir / job_id


def own_job(store: JobStore, job_id: str, email: str) -> dict[str, Any]:
    job = store.get(job_id)
    # 他人のジョブは「存在しない」と同じに見せる
    if job is None or job["owner"] != email:
        raise HTTPException(404, "ジョブが見つかりません")
    return job


def public(job: dict[str, Any], cfg: Settings) -> dict[str, Any]:
    d = job_dir(cfg, job["id"])
    return {
        "id": job["id"],
        "status": job["status"],
        "stage": job["stage"],
        "error": job["error"],
        "meta": job["meta"],
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
        "received": (d / "input.bin").stat().st_size if (d / "input.bin").exists() else 0,
        "files": sorted(n for n in DOWNLOADABLE if (d / n).exists()),
    }


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "time": time.time()}


@app.get("/api/me")
def me(email: Email) -> dict[str, str]:
    return {"email": email}


@app.get("/login")
def login(email: Email, cfg: Cfg, next: str = "") -> RedirectResponse:
    """ブラウザで直接開く入口。Access のログイン（Google）を通ったらフロントへ戻す"""
    u = urlparse(next)
    origin = f"{u.scheme}://{u.netloc}"
    if origin not in cfg.allowed_origins:
        next = cfg.allowed_origins[0] if cfg.allowed_origins else "/api/me"
    return RedirectResponse(next, status_code=303)


@app.post("/api/jobs", status_code=201)
def create_job(body: JobCreate, email: Email, store: Store, cfg: Cfg) -> dict[str, Any]:
    if not AUDIO_EXT.search(body.filename):
        raise HTTPException(415, "音声（wav/flac/m4a/mp3 など）または動画ファイルを選んでください")
    if body.size > cfg.max_upload_bytes:
        raise HTTPException(413, f"ファイルが大きすぎます（上限 {cfg.max_upload_bytes // 1024 ** 3}GB）")
    job = store.create(email, body.model_dump())
    job_dir(cfg, job["id"]).mkdir(parents=True, exist_ok=True)
    return public(job, cfg) | {"chunk_bytes": cfg.max_chunk_bytes}


@app.put("/api/jobs/{job_id}/input")
async def upload_chunk(job_id: str, offset: int, request: Request,
                       email: Email, store: Store, cfg: Cfg) -> dict[str, int]:
    job = own_job(store, job_id, email)
    if job["status"] != "uploading":
        raise HTTPException(409, "アップロードは締め切られています")
    path = job_dir(cfg, job_id) / "input.bin"
    have = path.stat().st_size if path.exists() else 0
    if offset != have:
        # 再開時はクライアントがこの値から送り直す
        raise HTTPException(409, detail={"message": "offset が一致しません", "received": have})
    limit = min(cfg.max_chunk_bytes, job["meta"]["size"] - have)
    n = 0
    with path.open("ab") as f:
        async for part in request.stream():
            n += len(part)
            if n > limit:
                f.truncate(have)
                raise HTTPException(413, "チャンクが大きすぎます")
            f.write(part)
    return {"received": have + n}


@app.put("/api/jobs/{job_id}/chapters")
async def upload_chapters(job_id: str, request: Request,
                          email: Email, store: Store, cfg: Cfg) -> dict[str, int]:
    job = own_job(store, job_id, email)
    if job["status"] != "uploading":
        raise HTTPException(409, "アップロードは締め切られています")
    data = await request.body()
    if len(data) > 256 * 1024:
        raise HTTPException(413, "章立てファイルが大きすぎます")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as e:
        raise HTTPException(400, "章立ては UTF-8 のテキストにしてください") from e
    (job_dir(cfg, job_id) / "chapters.txt").write_text(text, encoding="utf-8")
    return {"bytes": len(data)}


@app.post("/api/jobs/{job_id}/submit")
def submit(job_id: str, email: Email, store: Store, cfg: Cfg) -> dict[str, Any]:
    job = own_job(store, job_id, email)
    if job["status"] != "uploading":
        raise HTTPException(409, "すでに受け付けています")
    path = job_dir(cfg, job_id) / "input.bin"
    have = path.stat().st_size if path.exists() else 0
    if have != job["meta"]["size"]:
        raise HTTPException(409, detail={"message": "受信が完了していません", "received": have})
    store.update(job_id, status="queued", stage="待機中")
    return public(store.get(job_id), cfg)  # type: ignore[arg-type]


@app.get("/api/jobs")
def list_jobs(email: Email, store: Store, cfg: Cfg) -> list[dict[str, Any]]:
    return [public(j, cfg) for j in store.list_for(email)]


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str, email: Email, store: Store, cfg: Cfg) -> dict[str, Any]:
    return public(own_job(store, job_id, email), cfg)


@app.get("/api/jobs/{job_id}/files/{name}")
def download(job_id: str, name: str, email: Email, store: Store, cfg: Cfg) -> FileResponse:
    job = own_job(store, job_id, email)
    path = job_dir(cfg, job_id) / name
    if name not in DOWNLOADABLE or not path.is_file():
        raise HTTPException(404, "ファイルがありません")
    stem = re.sub(r"[^\w\-]+", "_", job["meta"].get("title") or job["meta"].get("date") or job_id)
    return FileResponse(path, media_type=DOWNLOADABLE[name],
                        filename=f"{stem}_{name}",
                        headers={"Cache-Control": "private, no-store"})


@app.delete("/api/jobs/{job_id}", status_code=204)
def delete_job(job_id: str, email: Email, store: Store, cfg: Cfg) -> None:
    job = own_job(store, job_id, email)
    if job["status"] == "running":
        raise HTTPException(409, "処理中のジョブは消せません")
    shutil.rmtree(job_dir(cfg, job_id), ignore_errors=True)
    store.delete(job_id)
