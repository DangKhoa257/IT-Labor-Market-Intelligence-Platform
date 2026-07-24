"""Database-only query repositories."""

from .analytics import AnalyticsRepository
from .companies import CompanyRepository
from .duplicates import DuplicateRepository
from .jobs import JobRepository
from .quality import QualityRepository
from .skills import SkillRepository

__all__ = [
    "AnalyticsRepository",
    "CompanyRepository",
    "DuplicateRepository",
    "JobRepository",
    "QualityRepository",
    "SkillRepository",
]
