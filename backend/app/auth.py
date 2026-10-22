"""Пользователи и сессии: хеширование паролей, вход, выход, текущий пользователь.

Почему сессии в базе, а не JWT: выход и «выйти на всех устройствах» должны работать сразу,
а JWT нельзя отозвать до истечения срока без того же хранилища на сервере. Фронтенд и API
открываются с одного адреса (nginx), поэтому токен хранится в httpOnly-cookie: скрипты
на странице его не видят, а браузер отправляет его сам.

От CSRF защищает SameSite=Lax: с чужого сайта браузер не отправит cookie в POST-запросе.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_session
from app.models import User, UserSession

COOKIE_NAME = "session"
# Параметры argon2id по умолчанию (рекомендация RFC 9106 для серверов)
hasher = PasswordHasher()
# Проверка пароля для несуществующего адреса идёт по этому хешу: время ответа одинаковое,
# и по нему нельзя узнать, зарегистрирован ли адрес
_DUMMY_HASH = hasher.hash("dummy-password")


class EmailTakenError(Exception):
    pass


def _token_hash(token: str) -> str:
    # Токен — 32 случайных байта, перебрать его нельзя, поэтому достаточно быстрого SHA-256
    return hashlib.sha256(token.encode()).hexdigest()


def register(session: Session, email: str, password: str) -> User:
    user = User(email=email.lower(), password_hash=hasher.hash(password))
    session.add(user)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise EmailTakenError from None
    return user


def authenticate(session: Session, email: str, password: str) -> User | None:
    user = session.scalar(select(User).where(User.email == email.lower()))
    try:
        hasher.verify(user.password_hash if user else _DUMMY_HASH, password)
    except VerificationError:
        return None
    if user is None:
        return None
    # Параметры хеширования могли стать строже — пересчитываем хеш, пока знаем пароль
    if hasher.check_needs_rehash(user.password_hash):
        user.password_hash = hasher.hash(password)
        session.commit()
    return user


def start_session(session: Session, user: User, response: Response) -> None:
    """Создаёт сессию и ставит cookie. Заодно удаляет истёкшие сессии пользователя."""
    now = datetime.now(UTC)
    session.execute(delete(UserSession).where(UserSession.user_id == user.id, UserSession.expires_at <= now))
    token = secrets.token_urlsafe(32)
    ttl = timedelta(days=settings.session_ttl_days)
    session.add(UserSession(user_id=user.id, token_hash=_token_hash(token), expires_at=now + ttl))
    session.commit()
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=int(ttl.total_seconds()),
        path="/api",
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )


def end_session(session: Session, request: Request, response: Response, *, everywhere: bool = False) -> None:
    current = _find_session(session, request)
    if current is not None:
        condition = UserSession.user_id == current.user_id if everywhere else UserSession.id == current.id
        session.execute(delete(UserSession).where(condition))
        session.commit()
    response.delete_cookie(COOKIE_NAME, path="/api", httponly=True, secure=settings.cookie_secure, samesite="lax")


def _find_session(session: Session, request: Request) -> UserSession | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    return session.scalar(
        select(UserSession).where(
            UserSession.token_hash == _token_hash(token), UserSession.expires_at > datetime.now(UTC)
        )
    )


def optional_user(request: Request, session: Session = Depends(get_session)) -> User | None:
    """Зависимость FastAPI: вошедший пользователь или None."""
    current = _find_session(session, request)
    return current.user if current else None


def current_user(user: User | None = Depends(optional_user)) -> User:
    """Зависимость FastAPI для эндпоинтов, где вход обязателен."""
    if user is None:
        raise HTTPException(401, "Нужно войти в аккаунт.")
    return user
