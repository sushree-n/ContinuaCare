from sqlalchemy import Column, String, Integer, Float, DateTime, Enum, ForeignKey, Text, JSON, Boolean
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime
import enum
import uuid

# ── Enums ────────────────────────────────────────────────────────────────────

class EpisodeState(enum.Enum):
    DISCHARGE_DETECTED  = "discharge_detected"
    AWAITING_CALL       = "awaiting_call"
    CALL_IN_PROGRESS    = "call_in_progress"
    CALL_COMPLETE       = "call_complete"
    ESCALATED           = "escalated"
    VISIT_SCHEDULED     = "visit_scheduled"
    READY_TO_BILL       = "ready_to_bill"
    VOIDED              = "voided"

class ComplexityLevel(enum.Enum):
    HIGH     = "high"
    MODERATE = "moderate"

class CallStatus(enum.Enum):
    SCHEDULED   = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED   = "completed"
    NO_ANSWER   = "no_answer"
    FAILED      = "failed"

class EscalationStatus(enum.Enum):
    OPEN         = "open"
    RESOLVED     = "resolved"

# ── Tables ───────────────────────────────────────────────────────────────────

class Patient(Base):
    __tablename__ = "patients"
    id                  = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name                = Column(String, nullable=False)
    age                 = Column(Integer)
    phone               = Column(String, nullable=False)
    diagnosis           = Column(String, nullable=False)
    medications         = Column(JSON)
    created_at          = Column(DateTime, default=datetime.utcnow)

class TCMEpisode(Base):
    __tablename__ = "episodes"
    id                  = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    patient_id          = Column(String, ForeignKey("patients.id"))
    state               = Column(Enum(EpisodeState), default=EpisodeState.DISCHARGE_DETECTED)
    discharge_date      = Column(DateTime, nullable=False)
    discharge_notes     = Column(Text)
    structured_extract  = Column(JSON)
    complexity          = Column(Enum(ComplexityLevel))
    triage_rationale    = Column(Text)
    visit_window_days   = Column(Integer)
    contact_deadline    = Column(DateTime)
    visit_deadline      = Column(DateTime)
    billing_date        = Column(DateTime)
    face_to_face_date   = Column(DateTime)
    med_rec_completed   = Column(Boolean, default=False)
    med_rec_date        = Column(DateTime)
    cpt_code            = Column(String)
    billing_doc         = Column(Text)
    ready_to_bill       = Column(Boolean, default=False)
    created_at          = Column(DateTime, default=datetime.utcnow)
    updated_at          = Column(DateTime, onupdate=datetime.utcnow)

class Call(Base):
    __tablename__ = "calls"
    id              = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    episode_id      = Column(String, ForeignKey("episodes.id"))
    patient_id      = Column(String, ForeignKey("patients.id"))
    livekit_room    = Column(String)
    attempt_number  = Column(Integer, default=1)
    scheduled_at    = Column(DateTime)
    started_at      = Column(DateTime)
    ended_at        = Column(DateTime)
    status          = Column(Enum(CallStatus), default=CallStatus.SCHEDULED)
    transcript      = Column(Text)
    summary         = Column(Text)
    flags           = Column(JSON)
    structured_data = Column(JSON)

class Escalation(Base):
    __tablename__ = "escalations"
    id              = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    episode_id      = Column(String, ForeignKey("episodes.id"))
    call_id         = Column(String, ForeignKey("calls.id"), nullable=True)
    reason          = Column(Text, nullable=False)
    severity        = Column(String)
    status          = Column(Enum(EscalationStatus), default=EscalationStatus.OPEN)
    created_at      = Column(DateTime, default=datetime.utcnow)
    acknowledged_at = Column(DateTime)

class CallSchedule(Base):
    __tablename__ = "call_schedules"
    id              = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    episode_id      = Column(String, ForeignKey("episodes.id"))
    patient_id      = Column(String, ForeignKey("patients.id"))
    scheduled_for   = Column(DateTime, nullable=False)
    day_number      = Column(Integer)
    completed       = Column(Boolean, default=False)