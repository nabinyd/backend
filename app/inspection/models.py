# app/db/models.py (update your existing models)
from sqlalchemy import Column, String, Float, Text, DateTime, Integer, Index, Boolean
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.sql import func
from app.db import Base
import uuid


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

    report_json = Column(LONGTEXT, nullable=True)
    report_text = Column(LONGTEXT, nullable=True)


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

    image_path = Column(String(512), nullable=False)  # Increased length
    status = Column(String(32), nullable=False, default="pending")  # pending|processing|done|failed

    meta_json = Column(Text, nullable=True)
    findings_json = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index("ix_frames_robot_field_ts", "robot_id", "field_id", "ts"),
        Index("ix_frames_run_ts", "run_id", "ts"),
    )


class ActiveInspection(Base):
    """Track which inspection run is currently active"""
    __tablename__ = "active_inspections"

    id = Column(Integer, primary_key=True)
    robot_id = Column(String(64), nullable=False, unique=True, index=True)
    run_id = Column(String(36), nullable=False, index=True)
    field_id = Column(String(64), nullable=False)
    started_at = Column(Float, nullable=False)
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index("ix_active_robot", "robot_id"),
    )