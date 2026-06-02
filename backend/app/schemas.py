from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict


class ParticipantCreate(BaseModel):
    participant_id: str
    group_id: str = "explainable"
    study_id: int = 1
    condition_id: int = 4
    session_id: Optional[str] = ""


class ParticipantRead(ParticipantCreate):
    created_at: datetime

    class Config:
        from_attributes = True


class TaskBase(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    task_code: str = ""
    task_type: str = "practice"
    target_text: str
    issue_types: List[str] = []
    focus_words: List[str] = []
    focus_phonemes: List[str] = []
    word_phoneme_map: Dict[str, List[str]] = {}
    speaking_target: str = ""
    difficulty: str = "medium"
    model_audio_path: str = ""
    model_audio_source: str = "tts"
    tts_sentence_audio_path: str = ""
    tts_focus_word_audio_json: Dict[str, str] = {}
    uploaded_sentence_audio_path_optional: str = ""
    uploaded_focus_word_audio_json_optional: Dict[str, str] = {}
    tts_voice: str = "browser-default"
    tts_status: str = "browser_only"
    feedback_allowed: bool = True
    revision_allowed: bool = True
    active: bool = True


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


class AnnotationCreate(BaseModel):
    annotator_id: str = ""
    attempt_id: int
    transcript_acceptable: bool = True
    human_missing_words: List[str] = []
    human_unclear_words: List[str] = []
    human_substitutions: List[Dict[str, str]] = []
    human_long_pause_count: int = 0
    pronunciation_rating: float = 0
    fluency_rating: float = 0
    comprehensibility_rating: float = 0
    feedback_appropriate: bool = True
    notes: str = ""
