"""設定は環境変数だけで与える（systemd の EnvironmentFile から読む想定）

雛形の例は deploy/msw.env.example。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _list(name: str, default: str = "") -> list[str]:
    return [x.strip() for x in os.environ.get(name, default).split(",") if x.strip()]


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(
        os.environ.get("MSW_DATA_DIR", str(Path.home() / "msw-data"))))

    # Cloudflare Access（Zero Trust → Access → Applications の AUD タグとチームドメイン）
    cf_team_domain: str = field(default_factory=lambda: os.environ.get("MSW_CF_TEAM_DOMAIN", ""))
    cf_aud: str = field(default_factory=lambda: os.environ.get("MSW_CF_AUD", ""))

    # Access のポリシーと二重に掛ける許可リスト（空なら全拒否 = fail-closed）
    allowed_emails: list[str] = field(default_factory=lambda: [
        e.lower() for e in _list("MSW_ALLOWED_EMAILS")])
    allowed_origins: list[str] = field(default_factory=lambda: _list(
        "MSW_ALLOWED_ORIGINS", "https://differance-lab.tokyo"))

    # ローカル開発のみ: Access を通さずにこのメールとして扱う（MSW_CF_AUD が空のときだけ有効）
    dev_email: str = field(default_factory=lambda: os.environ.get("MSW_DEV_EMAIL", ""))

    # Cloudflare の無料/Pro プランはリクエスト本体 100MB まで。余裕をみて 32MB 刻みで受ける
    max_chunk_bytes: int = field(default_factory=lambda: int(
        os.environ.get("MSW_MAX_CHUNK_BYTES", str(32 * 1024 * 1024))))
    max_upload_bytes: int = field(default_factory=lambda: int(
        os.environ.get("MSW_MAX_UPLOAD_BYTES", str(8 * 1024 ** 3))))
    # 原本音声は処理後に消す（一次資料として残すのは words/meta/srt と成果物）
    delete_input_after_done: bool = field(default_factory=lambda: os.environ.get(
        "MSW_DELETE_INPUT", "1") == "1")

    # 配管の場所（bin/advanced/audio-transcribe など）
    repo_root: Path = field(default_factory=lambda: Path(
        os.environ.get("MSW_REPO_ROOT", str(REPO_ROOT))))
    transcribe_args: list[str] = field(default_factory=lambda: os.environ.get(
        "MSW_TRANSCRIBE_ARGS", "--device cuda").split())
    terms_file: str = field(default_factory=lambda: os.environ.get(
        "MSW_TERMS_FILE", str(REPO_ROOT / "examples" / "terms-orchestral.txt")))

    model: str = field(default_factory=lambda: os.environ.get("MSW_MODEL", "claude-opus-5-5"))
    effort: str = field(default_factory=lambda: os.environ.get("MSW_EFFORT", "high"))
    # 章立てが無いときの分割幅（分）。曲をまたいだ取り違えを減らすため長くしすぎない
    window_minutes: int = field(default_factory=lambda: int(
        os.environ.get("MSW_WINDOW_MINUTES", "20")))

    lualatex: str = field(default_factory=lambda: os.environ.get("MSW_LUALATEX", "lualatex"))
    tex_timeout: int = field(default_factory=lambda: int(os.environ.get("MSW_TEX_TIMEOUT", "300")))
    tex_jfont: str = field(default_factory=lambda: os.environ.get(
        "MSW_TEX_JFONT", "Noto Serif CJK JP"))

    poll_seconds: float = field(default_factory=lambda: float(
        os.environ.get("MSW_POLL_SECONDS", "5")))

    @property
    def db_path(self) -> Path:
        return self.data_dir / "jobs.sqlite3"

    @property
    def jobs_dir(self) -> Path:
        return self.data_dir / "jobs"


def get_settings() -> Settings:
    return Settings()
