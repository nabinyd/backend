from sqlalchemy import Column, String, Float, Text, DateTime, Integer, Index
from sqlalchemy.sql import func
from app.db import Base


class InspectionRun(Base):
    __tablename__ = "inspection_runs"

    # UUID strings -> 36 chars
    id = Column(String(36), primary_key=True)  # run_id (uuid)

    # IDs / labels
    robot_id = Column(String(64), nullable=False, index=True)
    field_id = Column(String(64), nullable=False, index=True)

    # small enum-like string
    status = Column(String(32), nullable=False, default="pending")  # pending|processing|done|failed

    started_at_ts = Column(Float, nullable=False, index=True)
    ended_at_ts = Column(Float, nullable=True)

    total_frames = Column(Integer, nullable=False, default=0)
    done_frames = Column(Integer, nullable=False, default=0)
    failed_frames = Column(Integer, nullable=False, default=0)

    report_json = Column(Text, nullable=True)  # aggregated stats json
    report_text = Column(Text, nullable=True)  # llm json/text

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index("ix_runs_robot_field", "robot_id", "field_id"),
    )


class InspectionFrame(Base):
    __tablename__ = "inspection_frames"

    id = Column(String(36), primary_key=True)  # frame_id uuid
    run_id = Column(String(36), nullable=False, index=True)

    robot_id = Column(String(64), nullable=False, index=True)
    field_id = Column(String(64), nullable=False, index=True)
    ts = Column(Float, nullable=False, index=True)

    image_path = Column(String(255), nullable=False)  # file path length safe for MySQL
    status = Column(String(32), nullable=False, default="pending")  # pending|processing|done|failed

    meta_json = Column(Text, nullable=True)
    findings_json = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index("ix_frames_robot_field_ts", "robot_id", "field_id", "ts"),
        Index("ix_frames_run_ts", "run_id", "ts"),
    )
