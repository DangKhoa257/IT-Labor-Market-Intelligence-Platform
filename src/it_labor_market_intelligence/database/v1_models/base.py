"""Declarative base for schema-qualified Database V1 models."""

from sqlalchemy.orm import DeclarativeBase


class V1Base(DeclarativeBase):
    """Metadata for the additive Database V1 schemas."""
