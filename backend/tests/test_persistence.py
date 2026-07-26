from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from coc_kp_assistant.infrastructure.models import Base, CampaignRecord


def test_native_schema_round_trip() -> None:
    from coc_kp_assistant.infrastructure.database import create_database_engine

    engine = create_database_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        campaign = CampaignRecord(title="雾港疑案", era="1920s")
        session.add(campaign)
        session.commit()
        loaded = session.scalar(select(CampaignRecord).where(CampaignRecord.id == campaign.id))

    assert loaded is not None
    assert loaded.ruleset == "coc7e"
    assert {"campaigns", "investigators", "investigator_skills", "source_packs"} <= set(
        inspect(engine).get_table_names()
    )
    engine.dispose()

