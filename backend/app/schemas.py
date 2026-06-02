from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class ParticipantCreate(BaseModel):
    participant_id: str
    group_id: str
    session_id: Optional[str] = ""


class ParticipantRead(ParticipantCreate):
    created_at: datetime

    class Config:
        from_attributes = True


class TaskBase(BaseModel):
    target_text: str
    focus_words: List[str] = []
    speaking_target: str = ""
    difficulty: str = "medium"
    model_audio_path: str = ""


class TaskCreate(TaskBase):
    pass


class TaskRead(TaskBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class AttemptRead(BaseModel):
    id: int
    participant_id: str
    task_id: int
    group_id: str
    attempt_number: int
    audio_path: str
    asr_transcript: str
    duration_seconds: float
    speech_rate_wpm: float
    word_match_score: float
    missing_words: List[str]
    substitutions: List[Dict[str, str]]
    long_pause_count: int
    feedback_type: str
    feedback: Dict[str, Any]
    created_at: datetime
    target_text: Optional[str] = None
    score: Optional[float] = None
    improvement: Optional[float] = None


class DashboardSummary(BaseModel):
    participants: int
    attempts: int
    average_attempts_per_task: float
    average_word_match_score: float
    average_speech_rate_wpm: float
    common_missing_words: List[Dict[str, Any]]
    common_substitutions: List[Dict[str, Any]]
    average_improvement_first_to_latest: float
    feedback_views: int
    revision_events: int
