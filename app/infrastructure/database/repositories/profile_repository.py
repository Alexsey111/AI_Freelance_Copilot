"""Репозиторий профилей исполнителя (ТЗ §6)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models.profile import Profile
from app.infrastructure.database.models import ProfileModel

DEFAULT_SKILLS = [
    "Python",
    "FastAPI",
    "PostgreSQL",
    "Docker",
    "LLM",
    "REST API",
    "AI automation",
    "SQLAlchemy",
    "Git",
    "Parsing",
]


def _to_domain(model: ProfileModel) -> Profile:
    return Profile(
        id=model.id,
        name=model.name,
        summary=model.summary or "",
        skills=list(model.skills or []),
        experience=model.experience or "",
        portfolio=list(model.portfolio or []),
        preferences=dict(model.preferences or {}),
        is_active=bool(model.is_active),
    )


class ProfileRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, profile: Profile) -> Profile:
        model = ProfileModel(
            name=profile.name,
            summary=profile.summary,
            skills=profile.skills,
            experience=profile.experience,
            portfolio=profile.portfolio,
            preferences=profile.preferences,
            is_active=profile.is_active,
        )
        self.session.add(model)
        self.session.flush()
        self.session.refresh(model)
        return _to_domain(model)

    def get(self, profile_id: int) -> Profile | None:
        model = self.session.get(ProfileModel, profile_id)
        return _to_domain(model) if model else None

    def get_active(self) -> Profile | None:
        stmt = select(ProfileModel).where(ProfileModel.is_active.is_(True)).order_by(ProfileModel.id)
        model = self.session.execute(stmt).scalars().first()
        return _to_domain(model) if model else None

    def list(self) -> list[Profile]:
        stmt = select(ProfileModel).order_by(ProfileModel.id)
        return [_to_domain(model) for model in self.session.execute(stmt).scalars().all()]

    def update_skills(self, profile_id: int, skills: list[str]) -> Profile | None:
        """Заменить список навыков профиля (демонстрация изменения match score)."""
        model = self.session.get(ProfileModel, profile_id)
        if model is None:
            return None
        model.skills = [skill.strip() for skill in skills if skill and skill.strip()]
        self.session.flush()
        self.session.refresh(model)
        return _to_domain(model)

    def update_profile(self, profile_id: int, changes: dict) -> Profile | None:
        """Обновить переданные поля профиля. Не переданное — не трогаем."""
        model = self.session.get(ProfileModel, profile_id)
        if model is None:
            return None
        if "name" in changes and changes["name"] is not None:
            model.name = changes["name"].strip()
        if "summary" in changes and changes["summary"] is not None:
            model.summary = changes["summary"].strip()
        if "skills" in changes and changes["skills"] is not None:
            model.skills = [skill.strip() for skill in changes["skills"] if skill and skill.strip()]
        if "experience" in changes and changes["experience"] is not None:
            model.experience = changes["experience"].strip()
        if "portfolio" in changes and changes["portfolio"] is not None:
            model.portfolio = list(changes["portfolio"])
        if "preferences" in changes and changes["preferences"] is not None:
            model.preferences = dict(changes["preferences"])
        self.session.flush()
        self.session.refresh(model)
        return _to_domain(model)

    def ensure_default(self) -> Profile:
        """Гарантировать наличие профиля по умолчанию (чтобы UI работал "из коробки")."""
        active = self.get_active()
        if active is not None:
            return active
        return self.add(
            Profile(
                name="Основной профиль",
                summary="Python-разработчик: backend, API, интеграции с LLM, автоматизация.",
                skills=list(DEFAULT_SKILLS),
                experience="Backend-разработка на Python, ИИ-интеграции, автоматизация процессов.",
                portfolio=[],
                preferences={"min_budget": 20000, "currency": "RUB", "no_rewrite_legacy": True},
            )
        )
