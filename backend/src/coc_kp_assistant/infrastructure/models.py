from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def new_uuid() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class CampaignRecord(Base):
    __tablename__ = "campaigns"
    __table_args__ = (
        CheckConstraint("ruleset = 'coc7e'", name="ck_campaign_ruleset_coc7e"),
        CheckConstraint("version >= 1", name="ck_campaign_version_positive"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    ruleset: Mapped[str] = mapped_column(String(20), nullable=False, default="coc7e")
    era: Mapped[str] = mapped_column(String(40), nullable=False, default="1920s")
    custom_era_label: Mapped[str | None] = mapped_column(String(100))
    in_world_date: Mapped[str | None] = mapped_column(String(100))
    starting_location: Mapped[str | None] = mapped_column(String(200))
    enabled_source_pack_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    house_rules: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    keeper_notes: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    investigators: Mapped[list["InvestigatorRecord"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )


class InvestigatorRecord(Base):
    __tablename__ = "investigators"
    __table_args__ = (
        CheckConstraint("age >= 15", name="ck_investigator_age"),
        CheckConstraint("hit_points >= 0", name="ck_investigator_hp"),
        CheckConstraint("magic_points >= 0", name="ck_investigator_mp"),
        CheckConstraint("sanity >= 0 AND sanity <= 100", name="ck_investigator_sanity"),
        CheckConstraint("luck >= 0 AND luck <= 100", name="ck_investigator_luck"),
        CheckConstraint("mythos >= 0 AND mythos <= 100", name="ck_investigator_mythos"),
        CheckConstraint("version >= 1", name="ck_investigator_version_positive"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    player_name: Mapped[str | None] = mapped_column(String(160))
    occupation: Mapped[str] = mapped_column(String(160), nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    gender: Mapped[str | None] = mapped_column(String(80))
    residence: Mapped[str | None] = mapped_column(String(200))
    birthplace: Mapped[str | None] = mapped_column(String(200))
    era: Mapped[str] = mapped_column(String(80), nullable=False)

    strength: Mapped[int] = mapped_column(Integer, nullable=False)
    constitution: Mapped[int] = mapped_column(Integer, nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    dexterity: Mapped[int] = mapped_column(Integer, nullable=False)
    appearance: Mapped[int] = mapped_column(Integer, nullable=False)
    intelligence: Mapped[int] = mapped_column(Integer, nullable=False)
    power: Mapped[int] = mapped_column(Integer, nullable=False)
    education: Mapped[int] = mapped_column(Integer, nullable=False)

    hit_points: Mapped[int] = mapped_column(Integer, nullable=False)
    magic_points: Mapped[int] = mapped_column(Integer, nullable=False)
    sanity: Mapped[int] = mapped_column(Integer, nullable=False)
    luck: Mapped[int] = mapped_column(Integer, nullable=False)
    mythos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    move_rate: Mapped[int] = mapped_column(Integer, nullable=False)
    damage_bonus: Mapped[str] = mapped_column(String(40), nullable=False)
    build: Mapped[int] = mapped_column(Integer, nullable=False)
    credit_rating: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    spending_level: Mapped[str | None] = mapped_column(String(120))
    cash: Mapped[str | None] = mapped_column(String(120))
    assets: Mapped[str | None] = mapped_column(Text)
    conditions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    campaign: Mapped[CampaignRecord] = relationship(back_populates="investigators")
    skills: Mapped[list["InvestigatorSkillRecord"]] = relationship(
        back_populates="investigator", cascade="all, delete-orphan"
    )
    backstory: Mapped["InvestigatorBackstoryRecord | None"] = relationship(
        back_populates="investigator", cascade="all, delete-orphan", uselist=False
    )


class InvestigatorSkillRecord(Base):
    __tablename__ = "investigator_skills"
    __table_args__ = (
        UniqueConstraint(
            "investigator_id",
            "skill_key",
            "specialization_key",
            name="uq_investigator_skill_identity",
        ),
        CheckConstraint("base_value >= 0 AND base_value <= 100", name="ck_skill_base"),
        CheckConstraint("current_value >= 0 AND current_value <= 100", name="ck_skill_current"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    investigator_id: Mapped[str] = mapped_column(
        ForeignKey("investigators.id", ondelete="CASCADE"), nullable=False, index=True
    )
    skill_key: Mapped[str] = mapped_column(String(80), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    specialization: Mapped[str | None] = mapped_column(String(100))
    specialization_key: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    base_value: Mapped[int] = mapped_column(Integer, nullable=False)
    current_value: Mapped[int] = mapped_column(Integer, nullable=False)
    improvement_mark: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_pack_id: Mapped[str | None] = mapped_column(String(80))

    investigator: Mapped[InvestigatorRecord] = relationship(back_populates="skills")


class InvestigatorBackstoryRecord(Base):
    __tablename__ = "investigator_backstories"

    investigator_id: Mapped[str] = mapped_column(
        ForeignKey("investigators.id", ondelete="CASCADE"), primary_key=True
    )
    personal_description: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    ideology_and_beliefs: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    significant_people: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    meaningful_locations: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    treasured_possessions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    traits: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    injuries_and_scars: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    phobias_and_manias: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    mythos_tomes_spells_artifacts: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    strange_encounters: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    investigator: Mapped[InvestigatorRecord] = relationship(back_populates="backstory")


class SourcePackRecord(Base):
    __tablename__ = "source_packs"
    __table_args__ = (
        CheckConstraint("ruleset = 'coc7e'", name="ck_source_pack_ruleset_coc7e"),
        UniqueConstraint("pack_id", "version", name="uq_source_pack_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    pack_id: Mapped[str] = mapped_column(String(80), nullable=False)
    ruleset: Mapped[str] = mapped_column(String(20), nullable=False, default="coc7e")
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    edition: Mapped[str] = mapped_column(String(40), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    default_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    eras: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    files: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RollRecord(Base):
    __tablename__ = "roll_records"
    __table_args__ = (
        CheckConstraint("ruleset = 'coc7e'", name="ck_roll_record_ruleset_coc7e"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    case_session_id: Mapped[str | None] = mapped_column(
        ForeignKey("case_sessions.id", ondelete="SET NULL"), index=True
    )
    investigator_id: Mapped[str | None] = mapped_column(
        ForeignKey("investigators.id", ondelete="SET NULL"), index=True
    )
    ruleset: Mapped[str] = mapped_column(String(20), nullable=False, default="coc7e")
    skill_key: Mapped[str | None] = mapped_column(String(80))
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    request_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    resolution_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )


class StateAuditRecord(Base):
    __tablename__ = "state_audits"
    __table_args__ = (
        CheckConstraint("ruleset = 'coc7e'", name="ck_state_audit_ruleset_coc7e"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    campaign_id: Mapped[str | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="SET NULL"), index=True
    )
    ruleset: Mapped[str] = mapped_column(String(20), nullable=False, default="coc7e")
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    expected_version: Mapped[int | None] = mapped_column(Integer)
    before_data: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    after_data: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )


class RuleOperationRecord(Base):
    __tablename__ = "rule_operation_logs"
    __table_args__ = (
        CheckConstraint("ruleset = 'coc7e'", name="ck_rule_operation_ruleset_coc7e"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subject_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    case_session_id: Mapped[str | None] = mapped_column(
        ForeignKey("case_sessions.id", ondelete="SET NULL"), index=True
    )
    session_key: Mapped[str | None] = mapped_column(String(120), index=True)
    ruleset: Mapped[str] = mapped_column(String(20), nullable=False, default="coc7e")
    operation_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    input_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    output_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    citation_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )


class ChaseRecord(Base):
    __tablename__ = "chases"
    __table_args__ = (
        CheckConstraint("ruleset = 'coc7e'", name="ck_chase_ruleset_coc7e"),
        CheckConstraint("version >= 1", name="ck_chase_version_positive"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    case_session_id: Mapped[str | None] = mapped_column(
        ForeignKey("case_sessions.id", ondelete="SET NULL"), index=True
    )
    session_key: Mapped[str | None] = mapped_column(String(120), index=True)
    ruleset: Mapped[str] = mapped_column(String(20), nullable=False, default="coc7e")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active")
    participants: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class CaseSessionRecord(Base):
    __tablename__ = "case_sessions"
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_case_session_version_positive"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    player_visible_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    keeper_truth: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="planned")
    time_label: Mapped[str | None] = mapped_column(String(120))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class CasePersonRecord(Base):
    __tablename__ = "case_people"
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_case_person_version_positive"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str | None] = mapped_column(String(120))
    player_visible_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    keeper_truth: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class CaseLocationRecord(Base):
    __tablename__ = "case_locations"
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_case_location_version_positive"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    player_visible_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    keeper_truth: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class CaseSceneRecord(Base):
    __tablename__ = "case_scenes"
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_case_scene_version_positive"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id: Mapped[str | None] = mapped_column(
        ForeignKey("case_sessions.id", ondelete="SET NULL"), index=True
    )
    location_id: Mapped[str | None] = mapped_column(
        ForeignKey("case_locations.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    player_visible_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    keeper_truth: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="planned")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class CaseClueRecord(Base):
    __tablename__ = "case_clues"
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_case_clue_version_positive"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scene_id: Mapped[str | None] = mapped_column(
        ForeignKey("case_scenes.id", ondelete="SET NULL"), index=True
    )
    person_id: Mapped[str | None] = mapped_column(
        ForeignKey("case_people.id", ondelete="SET NULL"), index=True
    )
    location_id: Mapped[str | None] = mapped_column(
        ForeignKey("case_locations.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    player_visible_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    keeper_truth: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active")
    discovered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class CaseRelationshipRecord(Base):
    __tablename__ = "case_relationships"
    __table_args__ = (
        CheckConstraint("source_clue_id <> target_clue_id", name="ck_clue_link_distinct"),
        CheckConstraint("version >= 1", name="ck_case_relationship_version_positive"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_clue_id: Mapped[str] = mapped_column(
        ForeignKey("case_clues.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_clue_id: Mapped[str] = mapped_column(
        ForeignKey("case_clues.id", ondelete="CASCADE"), nullable=False, index=True
    )
    relationship_type: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    player_visible_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    keeper_truth: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class CaseHandoutRecord(Base):
    __tablename__ = "case_handouts"
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_case_handout_version_positive"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    clue_id: Mapped[str | None] = mapped_column(
        ForeignKey("case_clues.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    player_visible_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    keeper_truth: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft")
    revealed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class CaseTimelineEventRecord(Base):
    __tablename__ = "case_timeline_events"
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_case_timeline_version_positive"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id: Mapped[str | None] = mapped_column(
        ForeignKey("case_sessions.id", ondelete="SET NULL"), index=True
    )
    scene_id: Mapped[str | None] = mapped_column(
        ForeignKey("case_scenes.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    player_visible_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    keeper_truth: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="planned")
    time_label: Mapped[str | None] = mapped_column(String(120))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
