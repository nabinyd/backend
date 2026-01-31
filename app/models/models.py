import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.db import Base

def _uuid():
    return str(uuid.uuid4())

class Mission(Base):
    __tablename__ = "missions"

    id = Column(String, primary_key=True, default=_uuid)
    crop = Column(String, nullable=False, default="unknown")
    field_name = Column(String, nullable=False, default="unknown")
    spray_type = Column(String, nullable=True)
    status = Column(String, nullable=False, default="created")  # created|running|completed
    created_at = Column(DateTime, default=datetime.utcnow)

    frames = relationship("Frame", back_populates="mission", cascade="all, delete-orphan")
    report = relationship("MissionReport", uselist=False, back_populates="mission", cascade="all, delete-orphan")

class Frame(Base):
    __tablename__ = "frames"

    id = Column(String, primary_key=True, default=_uuid)
    mission_id = Column(String, ForeignKey("missions.id"), nullable=False)

    image_path = Column(String, nullable=False)
    ts = Column(Float, nullable=False)  # epoch seconds

    # metadata
    row = Column(Integer, nullable=True)
    x = Column(Float, nullable=True)
    y = Column(Float, nullable=True)
    yaw = Column(Float, nullable=True)

    analyzed = Column(Integer, nullable=False, default=0)  # 0/1
    findings_json = Column(Text, nullable=True)            # stored JSON string

    created_at = Column(DateTime, default=datetime.utcnow)

    mission = relationship("Mission", back_populates="frames")

class MissionReport(Base):
    __tablename__ = "mission_reports"

    id = Column(String, primary_key=True, default=_uuid)
    mission_id = Column(String, ForeignKey("missions.id"), nullable=False)

    report_json = Column(Text, nullable=False)  # stored JSON string
    created_at = Column(DateTime, default=datetime.utcnow)

    mission = relationship("Mission", back_populates="report")
