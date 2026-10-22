"""Регистрация, вход и выход. Почему сессии, а не JWT, — в app/auth.py."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app import auth
from app.db import get_session
from app.models import User
from app.rate_limit import limit_auth
from app.schemas import CredentialsIn, UserOut

router = APIRouter(prefix="/api/auth", tags=["Пользователи"])


@router.post("/register", status_code=201, response_model=UserOut, dependencies=[Depends(limit_auth)])
def register(body: CredentialsIn, response: Response, session: Session = Depends(get_session)):
    try:
        user = auth.register(session, body.email, body.password)
    except auth.EmailTakenError:
        raise HTTPException(409, "Этот адрес уже зарегистрирован. Попробуйте войти.") from None
    auth.start_session(session, user, response)
    return UserOut(id=user.id, email=user.email)


@router.post("/login", response_model=UserOut, dependencies=[Depends(limit_auth)])
def login(body: CredentialsIn, response: Response, session: Session = Depends(get_session)):
    user = auth.authenticate(session, body.email, body.password)
    if user is None:
        # Одинаковый ответ для неизвестного адреса и неверного пароля
        raise HTTPException(401, "Неверная почта или пароль.")
    auth.start_session(session, user, response)
    return UserOut(id=user.id, email=user.email)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, session: Session = Depends(get_session)):
    auth.end_session(session, request, response)


@router.post("/logout-all", status_code=204)
def logout_everywhere(
    request: Request, response: Response, session: Session = Depends(get_session), _: User = Depends(auth.current_user)
):
    """Завершает все сессии пользователя, включая текущую."""
    auth.end_session(session, request, response, everywhere=True)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(auth.current_user)):
    return UserOut(id=user.id, email=user.email)
