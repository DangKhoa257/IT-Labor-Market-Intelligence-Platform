from collections import defaultdict
from statistics import mean, median
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import InstrumentedAttribute

from ..models import Company, JobPosting, Skill, Source


class AnalyticsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def overview(self) -> dict[str, Any]:
        total = self.session.scalar(select(func.count(JobPosting.id))) or 0
        active = (
            self.session.scalar(
                select(func.count(JobPosting.id)).where(JobPosting.status == "ACTIVE")
            )
            or 0
        )
        disclosed = (
            self.session.scalar(
                select(func.count(JobPosting.id)).where(JobPosting.salary_disclosed.is_(True))
            )
            or 0
        )
        sources = self.session.execute(
            select(Source.name, func.count(JobPosting.id))
            .join(JobPosting)
            .group_by(Source.id)
            .order_by(Source.name)
        )
        return {
            "total_jobs": total,
            "active_jobs": active,
            "unique_companies": self.session.scalar(select(func.count(Company.id))) or 0,
            "unique_skills": self.session.scalar(select(func.count(Skill.id))) or 0,
            "salary_disclosed_rate": round(disclosed / total, 4) if total else 0.0,
            "source_coverage": [{"source": name, "count": count} for name, count in sources],
        }

    def grouped(self, column: InstrumentedAttribute[str | None]) -> list[dict[str, Any]]:
        rows = self.session.execute(
            select(column, func.count(JobPosting.id))
            .group_by(column)
            .order_by(func.count(JobPosting.id).desc(), column)
        )
        return [{"value": value, "count": count} for value, count in rows]

    def salaries(self) -> dict[str, Any]:
        rows = self.session.execute(
            select(
                JobPosting.salary_currency,
                JobPosting.salary_min,
                JobPosting.salary_max,
                JobPosting.primary_category,
                JobPosting.city,
            )
            .where(
                JobPosting.salary_min.is_not(None),
                JobPosting.salary_max.is_not(None),
                JobPosting.salary_currency.is_not(None),
            )
            .order_by(JobPosting.salary_currency, JobPosting.id)
        )
        currency_groups: dict[str, list[tuple[float, float]]] = defaultdict(list)
        category_groups: dict[tuple[str, str], list[float]] = defaultdict(list)
        city_groups: dict[tuple[str, str], list[float]] = defaultdict(list)
        for currency, minimum, maximum, category, city in rows:
            low, high = float(minimum), float(maximum)
            midpoint = (low + high) / 2
            currency_groups[str(currency)].append((low, high))
            category_groups[(str(currency), str(category or "Unclassified"))].append(midpoint)
            city_groups[(str(currency), str(city or "Unspecified"))].append(midpoint)
        return {
            "by_currency": [
                {
                    "currency": currency,
                    "sample_count": len(values),
                    "min": min(value[0] for value in values),
                    "max": max(value[1] for value in values),
                    "mean": mean((value[0] + value[1]) / 2 for value in values),
                    "median": median((value[0] + value[1]) / 2 for value in values),
                    "calculation_basis": "posting_range_midpoint",
                    "statistically_meaningful": len(values) > 1,
                    "interpretation": (
                        "Descriptive across multiple postings."
                        if len(values) > 1
                        else "Single-posting range midpoint; not a market mean or median."
                    ),
                }
                for currency, values in sorted(currency_groups.items())
            ],
            "by_category": [
                {
                    "currency": key[0],
                    "category": key[1],
                    "sample_count": len(values),
                    "mean": mean(values),
                    "median": median(values),
                }
                for key, values in sorted(category_groups.items())
            ],
            "by_city": [
                {
                    "currency": key[0],
                    "city": key[1],
                    "sample_count": len(values),
                    "mean": mean(values),
                    "median": median(values),
                }
                for key, values in sorted(city_groups.items())
            ],
            "calculation_metadata": {
                "observation_unit": "one midpoint per posting with numeric minimum and maximum",
                "midpoint_formula": "(salary_min + salary_max) / 2",
                "single_posting_limitation": (
                    "For a single-posting sample (sample_count=1), mean and median equal that "
                    "posting's midpoint and must not "
                    "be interpreted as a market statistic."
                ),
                "currencies_combined": False,
            },
        }
