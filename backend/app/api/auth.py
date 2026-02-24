import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.config import get_settings
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
GOOGLE_OAUTH_STATE_PURPOSE = "google_oauth"


def to_user_out(user: User) -> UserOut:
    return UserOut(id=str(user.id), email=user.email, name=user.name)


def _oauth_fallback_name(email: str) -> str:
    base = email.split("@", 1)[0].strip()
    if len(base) >= 2:
        return base[:100]
    return "Пользователь"


def _require_google_oauth_settings() -> tuple[str, str, str]:
    settings = get_settings()
    client_id = (settings.google_oauth_client_id or "").strip()
    client_secret = (settings.google_oauth_client_secret or "").strip()
    redirect_uri = settings.google_oauth_redirect_uri.strip()
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OAuth временно недоступен: не настроены GOOGLE_OAUTH_CLIENT_ID и GOOGLE_OAUTH_CLIENT_SECRET",
        )
    return client_id, client_secret, redirect_uri


def _create_google_oauth_state() -> str:
    settings = get_settings()
    payload = {
        "purpose": GOOGLE_OAUTH_STATE_PURPOSE,
        "nonce": secrets.token_urlsafe(16),
        "exp": datetime.now(UTC) + timedelta(minutes=10),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _verify_google_oauth_state(state: str) -> bool:
    settings = get_settings()
    try:
        payload = jwt.decode(state, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return False
    return payload.get("purpose") == GOOGLE_OAUTH_STATE_PURPOSE


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    email = payload.email.lower().strip()
    existing = await db.scalar(select(User).where(func.lower(User.email) == email))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Этот email уже зарегистрирован")

    user = User(
        email=email,
        name=payload.name.strip(),
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = create_access_token(str(user.id))
    return TokenResponse(access_token=token, user=to_user_out(user))


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    email = payload.email.lower().strip()
    user = await db.scalar(select(User).where(func.lower(User.email) == email))
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный email или пароль")

    token = create_access_token(str(user.id))
    return TokenResponse(access_token=token, user=to_user_out(user))


@router.get("/oauth/google/start")
async def oauth_google_start() -> RedirectResponse:
    client_id, _, redirect_uri = _require_google_oauth_settings()
    state = _create_google_oauth_state()
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    }
    return RedirectResponse(url=f"{GOOGLE_AUTH_URL}?{urlencode(params)}", status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.get("/oauth/google/callback")
async def oauth_google_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    if error:
        message = error_description or error
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"OAuth отменён: {message}")
    if not code or not state:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OAuth вернул неполные данные")
    if not _verify_google_oauth_state(state):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный OAuth state")

    client_id, client_secret, redirect_uri = _require_google_oauth_settings()

    async with httpx.AsyncClient(timeout=20.0) as client:
        token_response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            headers={"Accept": "application/json"},
        )

    if token_response.status_code >= 400:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Не удалось завершить OAuth вход")

    try:
        token_payload = token_response.json()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OAuth вернул некорректный ответ") from exc

    access_token = token_payload.get("access_token")
    if not isinstance(access_token, str) or not access_token.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OAuth не вернул access token")

    async with httpx.AsyncClient(timeout=20.0) as client:
        profile_response = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        )

    if profile_response.status_code >= 400:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Не удалось получить профиль Google")

    try:
        profile = profile_response.json()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Google вернул некорректный профиль") from exc

    email = str(profile.get("email") or "").lower().strip()
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Google не вернул email")
    if profile.get("email_verified") is False:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Google email не подтверждён")

    provided_name = str(profile.get("name") or profile.get("given_name") or "").strip()
    resolved_name = (provided_name if len(provided_name) >= 2 else _oauth_fallback_name(email))[:100]

    user = await db.scalar(select(User).where(func.lower(User.email) == email))
    if user is None:
        user = User(
            email=email,
            name=resolved_name,
            hashed_password=hash_password(secrets.token_urlsafe(32)),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    elif resolved_name and user.name != resolved_name:
        user.name = resolved_name
        await db.commit()

    frontend_target = get_settings().frontend_url.rstrip("/")
    app_token = create_access_token(str(user.id))
    fragment = urlencode(
        {
            "access_token": app_token,
            "user_id": str(user.id),
            "user_email": user.email,
            "user_name": user.name,
        }
    )
    return RedirectResponse(url=f"{frontend_target}/auth/oauth/callback#{fragment}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)) -> UserOut:
    return to_user_out(current_user)
