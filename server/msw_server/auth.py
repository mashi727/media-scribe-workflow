"""Cloudflare Access の JWT を検証して、利用者のメールアドレスを得る

Google ログインそのものは Cloudflare Access（IdP = Google）が行う。
Access を通ったリクエストには Cf-Access-Jwt-Assertion ヘッダが付くので、
ここでは

    1. 署名（チームの公開鍵 /cdn-cgi/access/certs）
    2. aud（このアプリケーションの AUD タグ）と iss（チームドメイン）
    3. email が許可リストにあること

を確かめる。API は 127.0.0.1 でしか待たないので Tunnel 以外からは届かないが、
Access の設定ミスに備えてアプリ側でも検証する（多層防御）。
"""
from __future__ import annotations

from functools import lru_cache

import jwt
from fastapi import HTTPException, Request

from .config import Settings

HEADER = "Cf-Access-Jwt-Assertion"
COOKIE = "CF_Authorization"


@lru_cache(maxsize=4)
def _jwks_client(team_domain: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"https://{team_domain}/cdn-cgi/access/certs", cache_keys=True)


def verify_token(token: str, settings: Settings, jwks: jwt.PyJWKClient | None = None) -> str:
    """検証済みの email（小文字）を返す。失敗は HTTPException"""
    if not settings.cf_team_domain or not settings.cf_aud:
        raise HTTPException(500, "Cloudflare Access が未設定です（MSW_CF_TEAM_DOMAIN / MSW_CF_AUD）")
    client = jwks or _jwks_client(settings.cf_team_domain)
    try:
        key = client.get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token, key, algorithms=["RS256"], audience=settings.cf_aud,
            issuer=f"https://{settings.cf_team_domain}",
            options={"require": ["exp", "iat", "aud", "iss"]})
    except jwt.PyJWTError as e:
        raise HTTPException(401, f"認証トークンが無効です: {e}") from e
    email = str(claims.get("email", "")).lower()
    if not email:
        raise HTTPException(401, "トークンに email がありません（サービストークンは不可）")
    if email not in settings.allowed_emails:
        raise HTTPException(403, "このアカウントには利用権限がありません")
    return email


def current_email(request: Request, settings: Settings) -> str:
    # 開発用の認証省略は Access 未設定（AUD 無し）のときだけ効く。本番で誤って残っても無視される
    if settings.dev_email and not settings.cf_aud:
        return settings.dev_email.lower()
    token = request.headers.get(HEADER) or request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, "ログインしてください")
    return verify_token(token, settings)
