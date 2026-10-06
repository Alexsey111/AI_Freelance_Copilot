"""Метрики проекта (ТЗ §34) и мини-экономика (ТЗ §33).

Принцип, который здесь соблюдается строго: метрика на пустом входе возвращает
"нет данных" (None), а не ноль. Ноль --- это утверждение "не было ни одного случая",
и он неотличим от успешного прохождения цели. Проценты при нулевом знаменателе
тоже не считаются.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Ставка для мини-экономики, руб/час. Значение по умолчанию --- оценка, а не факт;
# в отчёте его нужно заменить фактическим (ТЗ §33).
DEFAULT_HOURLY_RATE_RUB = 1500.0


@dataclass(slots=True)
class Metrics:
    """Снимок метрик MVP."""

    orders_total: int = 0
    orders_by_status: dict[str, int] = field(default_factory=dict)
    orders_recommended: int = 0
    orders_needs_review: int = 0

    analyses_total: int = 0
    analyses_needs_review: int = 0
    analyses_errors: int = 0
    analyses_by_recommendation: dict[str, int] = field(default_factory=dict)
    avg_match_score: float | None = None

    audit_total: int = 0
    audit_by_status: dict[str, int] = field(default_factory=dict)
    audit_by_action: dict[str, int] = field(default_factory=dict)
    audit_errors: int = 0
    avg_analyze_duration_ms: float | None = None
    max_analyze_duration_ms: int | None = None

    # --- производные (None = "нет данных") ---
    @property
    def json_valid_rate(self) -> float | None:
        """Доля корректных JSON: успешные анализы / все анализы (ТЗ §34)."""
        if self.analyses_total == 0:
            return None
        ok = self.analyses_total - self.analyses_errors
        return round(max(ok, 0) / self.analyses_total, 4)

    @property
    def review_share(self) -> float | None:
        """Доля заказов, ушедших на ручную проверку."""
        if self.analyses_total == 0:
            return None
        return round(self.analyses_needs_review / self.analyses_total, 4)

    @property
    def apply_share(self) -> float | None:
        """Доля заказов, которые система рекомендует к отклику."""
        if self.analyses_total == 0:
            return None
        apply_count = self.analyses_by_recommendation.get("apply", 0)
        return round(apply_count / self.analyses_total, 4)

    @property
    def manual_order_minutes(self) -> int:
        """Время ручного разбора заказа до автоматизации, мин (ТЗ §33)."""
        return 3 + 3 + 5 + 2

    @property
    def assisted_order_minutes(self) -> int:
        """Время работы человека с системой после автоматизации, мин (ТЗ §33)."""
        return 1 + 1 + 1

    def economy(self, hourly_rate_rub: float = DEFAULT_HOURLY_RATE_RUB) -> dict:
        """Мини-экономика "на салфетке": 100 операций до/после (ТЗ §33)."""
        manual_per_order = self.manual_order_minutes
        assisted_per_order = self.assisted_order_minutes
        manual_100_min = manual_per_order * 100
        assisted_100_min = assisted_per_order * 100
        saved_min = manual_100_min - assisted_100_min
        return {
            "hourly_rate_rub": hourly_rate_rub,
            "manual_order_minutes": manual_per_order,
            "assisted_order_minutes": assisted_per_order,
            "manual_100_minutes": manual_100_min,
            "assisted_100_minutes": assisted_100_min,
            "manual_100_hours": round(manual_100_min / 60, 2),
            "assisted_100_hours": round(assisted_100_min / 60, 2),
            "saved_minutes_per_100": saved_min,
            "saved_hours_per_100": round(saved_min / 60, 2),
            "saved_money_rub_per_100": round(saved_min / 60 * hourly_rate_rub, 2),
            "measured_avg_analysis_seconds": (
                round(self.avg_analyze_duration_ms / 1000, 2)
                if self.avg_analyze_duration_ms is not None
                else None
            ),
        }


class MetricsService:
    """Сбор метрик из репозиториев. Единственное место, где считаются KPI."""

    def __init__(self, order_repository, analysis_repository, audit_repository) -> None:
        self.orders = order_repository
        self.analyses = analysis_repository
        self.audit = audit_repository

    def collect(self) -> Metrics:
        return Metrics(
            orders_total=self.orders.count_all(),
            orders_by_status=self.orders.count_by_status(),
            orders_recommended=self.orders.count_recommended(),
            orders_needs_review=self.orders.count_needs_review()
            if hasattr(self.orders, "count_needs_review")
            else self.analyses.count_needs_review(),
            analyses_total=self.analyses.count_all(),
            analyses_needs_review=self.analyses.count_needs_review(),
            analyses_errors=self.analyses.count_errors(),
            analyses_by_recommendation=self.analyses.count_by_recommendation(),
            avg_match_score=self.analyses.avg_match_score(),
            audit_total=self.audit.count_all(),
            audit_by_status=self.audit.count_by_status(),
            audit_by_action=self.audit.count_by_action(),
            audit_errors=self.audit.count_errors(),
            avg_analyze_duration_ms=self.audit.avg_duration_ms("analyze_order"),
            max_analyze_duration_ms=self.audit.max_duration_ms("analyze_order"),
        )
