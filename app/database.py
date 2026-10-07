"""SQLAlchemy engine, session factory and FastAPI database dependencies."""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    """Base class for all ORM models."""


# SQLite objects are bound to the creating thread by default. FastAPI runs sync
# endpoints and background tasks in a thread pool, so we relax that check.
# Every request/task still gets its own Session, so sessions are never shared.
_connect_args = (
    {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
)

engine = create_engine(settings.database_url, connect_args=_connect_args)

# expire_on_commit=False keeps loaded objects readable after commit, which avoids
# surprise extra queries in the background worker loop.
SessionLocal = sessionmaker(
    bind=engine, autoflush=False, expire_on_commit=False
)


def get_db() -> Iterator[Session]:
    """Request-scoped session; always closed, even if the endpoint raises."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_session_factory() -> sessionmaker:
    """Dependency that hands the *factory* to code that outlives the request.

    The background task runs after the response is sent, when the request's
    session is already closed, so it needs to open its own session.
    """
    return SessionLocal


def init_db() -> None:
    """Create tables if they do not exist yet (simple 'migration' for SQLite)."""
    from app import models  # noqa: F401  (import registers the tables on Base)

    Base.metadata.create_all(bind=engine)