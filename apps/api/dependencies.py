from collections.abc import Generator

from sqlalchemy.orm import Session

from it_labor_market_intelligence.database.session import create_database_engine, session_factory

from .settings import APISettings

_factory = None


def configure_database(url: str) -> None:
    global _factory
    _factory = session_factory(create_database_engine(url))


def get_session() -> Generator[Session, None, None]:
    global _factory
    if _factory is None:
        configure_database(APISettings().database_url)
    assert _factory is not None
    with _factory() as session:
        yield session
