from app.database import Base, Participant, SessionLocal, Task, engine


def test_database_insert_and_query():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        pid = "pytest_participant"
        existing = db.query(Participant).filter(Participant.participant_id == pid).first()
        if existing:
            db.delete(existing)
            db.commit()
        participant = Participant(participant_id=pid, group_id="control")
        task = Task(target_text="The test sentence is clear.", focus_words="[]")
        db.add(participant)
        db.add(task)
        db.commit()
        assert db.query(Participant).filter(Participant.participant_id == pid).first() is not None
    finally:
        db.close()
