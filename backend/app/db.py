"""Подключение к базе данных."""
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

# Без connect_timeout подключение к недоступной базе может висеть минутами
engine = create_engine(settings.database_url, connect_args={"connect_timeout": 5})

# expire_on_commit=False: объекты остаются читаемыми после закрытия сессии.
# Это нужно, потому что модули совместимости и подбора работают с уже загруженными деталями.
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_session() -> Iterator[Session]:
    """Зависимость FastAPI: одна сессия на запрос."""
    with SessionLocal() as session:
        yield session
