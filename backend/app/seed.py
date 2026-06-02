import json

from .database import Condition, FeedbackTemplate, Participant, Study, SystemVersion, Task


CONDITIONS = [
    ("G0", "G0 Practice-only", True, False, False, False, False, False, False, True),
    ("G1", "G1 Score-only feedback", True, True, False, False, False, False, False, True),
    ("G2", "G2 Comment-only feedback", True, False, True, True, True, False, False, True),
    ("G3", "G3 Score + Comment feedback", True, True, True, True, True, False, False, True),
]

PRACTICE_BASE = [
    ("The thin path winds through three quiet fields.", ["theta_words", "rhythm"], ["thin", "through", "three"], ["th"], {"thin": ["th"], "through": ["th"], "three": ["th"]}),
    ("Ray left a red ribbon near the library rail.", ["r_l_contrast"], ["ray", "red", "library"], ["r", "l"], {"ray": ["r"], "red": ["r"], "library": ["l", "r"]}),
    ("Please keep the final sound in kept, asked, and missed.", ["final_consonants"], ["kept", "asked", "missed"], ["final_t", "final_d"], {"kept": ["final_t"], "asked": ["final_t"], "missed": ["final_t"]}),
    ("A small blue clock stood beside the glass plant.", ["consonant_clusters"], ["small", "clock", "glass"], ["clusters"], {"small": ["clusters"], "clock": ["clusters"], "glass": ["clusters"]}),
    ("She thought the weather would improve by Thursday.", ["theta_words"], ["thought", "weather", "Thursday"], ["th"], {"thought": ["th"], "weather": ["th"], "Thursday": ["th"]}),
    ("Mark brought fresh fruit for breakfast before class.", ["consonant_clusters", "word_stress"], ["brought", "fresh", "breakfast"], ["clusters"], {"brought": ["clusters"], "fresh": ["clusters"], "breakfast": ["clusters"]}),
    ("The light rain fell slowly on the river road.", ["r_l_contrast", "rhythm"], ["light", "rain", "river"], ["r", "l"], {"light": ["l"], "rain": ["r"], "river": ["r"]}),
    ("We watched the brave child climb the steep steps.", ["final_consonants", "consonant_clusters"], ["watched", "climb", "steps"], ["final_t", "clusters"], {"watched": ["final_t"], "climb": ["clusters"], "steps": ["clusters"]}),
    ("Laura rarely arrives late for reading lessons.", ["r_l_contrast"], ["Laura", "rarely", "late"], ["r", "l"], {"Laura": ["l", "r"], "rarely": ["r", "l"], "late": ["l"]}),
    ("The student explained the problem in a clear voice.", ["word_stress", "rhythm"], ["student", "explained", "clear"], ["stress"], {"student": ["stress"], "explained": ["stress"], "clear": ["clusters"]}),
]

ASSESSMENT_SENTENCES = [
    "The brave traveler crossed the narrow bridge at sunrise.",
    "Three children found fresh shells beside the stream.",
    "Please describe the red flowers near the glass door.",
    "The speaker read each phrase with steady rhythm.",
    "A quiet learner repeated the final consonant clearly.",
    "The old clock struck twelve during the reading test.",
    "Rain fell across the river road after lunch.",
    "She placed the small spoon next to the green cup.",
    "The thoughtful clerk wrote the price on a card.",
    "Students should breathe slowly before difficult phrases.",
]

TEMPLATES = {
    "theta_words": ("The word '{word}' may need clearer /th/ articulation.", "The /th/ sound can change word identity if it is replaced by /t/, /d/, /s/, or /z/.", "Practise '{word}' slowly, then put it back into the full sentence."),
    "r_l_contrast": ("The word '{word}' may show an /r/ and /l/ contrast issue.", "Listeners may confuse words when /r/ and /l/ are not separated clearly.", "Repeat the focus word three times with careful tongue position."),
    "final_consonants": ("The final sound in '{word}' may be missing or unclear.", "Final consonants often carry grammar and meaning in English.", "Hold the final consonant lightly before moving to the next word."),
    "consonant_clusters": ("The cluster in '{word}' may be simplified.", "Consonant clusters help listeners identify the intended word.", "Break the cluster into sounds, then blend it into the word."),
    "speech_rate_fast": ("The reading may be too fast.", "Fast speech can blur important sounds.", "Slow down slightly and mark natural phrase boundaries."),
    "speech_rate_slow": ("The reading may be too slow.", "Very slow reading can reduce fluency and sentence rhythm.", "Practise in short chunks, then connect the chunks smoothly."),
    "long_pause": ("There may be a long pause in the sentence.", "Long pauses can interrupt comprehensibility.", "Plan one or two phrase groups before re-recording."),
    "word_stress": ("One or more focus words may need stronger stress.", "Word stress helps listeners identify important information.", "Say the focus word with a clearer stressed syllable."),
    "rhythm": ("The sentence rhythm may need more even grouping.", "Rhythm supports fluency and comprehensibility.", "Read the sentence in meaning-based chunks."),
    "generic_unclear_word": ("The word '{word}' may not have been clearly recognized.", "Unclear key words can make the message harder to understand.", "Practise the word, then re-record the whole sentence."),
}


def seed_database(db):
    if db.query(Study).count() == 0:
        db.add(Study(id=1, study_name="Default Speech-AI Feedback Study", description="Default controlled experiment setup.", active=True))
        db.commit()

    for idx, item in enumerate(CONDITIONS, start=1):
        code, name, transcript, score, comment, word_focus, sound_focus, teacher, peer, revision = item
        condition = db.query(Condition).filter(Condition.condition_code == code).first()
        if not condition:
            condition = db.query(Condition).filter(Condition.id == idx).first()
        if not condition:
            condition = Condition(id=idx, study_id=1, condition_code=code, condition_name=name)
            db.add(condition)
        condition.condition_code = code
        condition.condition_name = name
        condition.show_transcript = transcript
        condition.show_score = score
        condition.show_comment = comment
        condition.show_word_focus = word_focus
        condition.show_sound_focus = sound_focus
        condition.show_practice_suggestion = comment
        condition.show_diagnosis = comment
        condition.show_explanation = False
        condition.show_action_guidance = comment
        condition.adaptive_feedback = False
        condition.human_validation_required = False
        condition.llm_verbalization_enabled = False
        condition.enable_teacher_feedback = teacher
        condition.enable_peer_feedback = peer
        condition.allow_revision = revision
        condition.revision_allowed = revision
    db.commit()

    if db.query(Task).count() < 70:
        db.query(Task).delete()
        for idx in range(40):
            text, issues, focus, phonemes, word_map = PRACTICE_BASE[idx % len(PRACTICE_BASE)]
            db.add(Task(
                task_code="P%03d" % (idx + 1),
                task_type="practice",
                target_text=text,
                issue_types_json=json.dumps(issues),
                focus_words=json.dumps(focus),
                focus_phonemes_json=json.dumps(phonemes),
                word_phoneme_map_json=json.dumps({k.lower(): v for k, v in word_map.items()}),
                speaking_target="pronunciation clarity and comprehensibility",
                difficulty=["easy", "medium", "hard"][idx % 3],
                feedback_allowed=True,
                revision_allowed=True,
                active=True,
            ))
        assessment_types = ["pretest", "posttest", "delayed"]
        for idx in range(30):
            task_type = assessment_types[idx // 10]
            db.add(Task(
                task_code="%s%03d" % (task_type[:2].upper(), idx + 1),
                task_type=task_type,
                target_text=ASSESSMENT_SENTENCES[idx % len(ASSESSMENT_SENTENCES)],
                issue_types_json=json.dumps(["final_consonants", "consonant_clusters", "rhythm"]),
                focus_words=json.dumps([]),
                speaking_target="assessment of intelligibility and fluency",
                difficulty="medium",
                feedback_allowed=False,
                revision_allowed=False,
                active=True,
            ))
        db.commit()
    else:
        practice_tasks = db.query(Task).filter(Task.task_type == "practice").order_by(Task.id.asc()).all()
        changed = False
        for idx, task in enumerate(practice_tasks):
            if (
                not task.focus_words or task.focus_words == "[]"
                or not task.issue_types_json or task.issue_types_json == "[]"
                or not task.focus_phonemes_json or task.focus_phonemes_json == "[]"
                or not task.word_phoneme_map_json or task.word_phoneme_map_json == "{}"
            ):
                _, issues, focus, phonemes, word_map = PRACTICE_BASE[idx % len(PRACTICE_BASE)]
                task.issue_types_json = json.dumps(issues)
                task.focus_words = json.dumps(focus)
                task.focus_phonemes_json = json.dumps(phonemes)
                task.word_phoneme_map_json = json.dumps({k.lower(): v for k, v in word_map.items()})
                task.speaking_target = task.speaking_target or "pronunciation_clarity"
                changed = True
        if changed:
            db.commit()

    if db.query(FeedbackTemplate).count() == 0:
        for issue_type, parts in TEMPLATES.items():
            diagnosis, explanation, action = parts
            db.add(FeedbackTemplate(
                issue_type=issue_type,
                feedback_level="standard",
                condition="G3",
                diagnosis_template=diagnosis,
                explanation_template=explanation,
                action_template=action,
                revision_goal_template="In your next recording, check whether this issue is reduced.",
                metacognitive_prompt_template="What changed between this attempt and your next attempt?",
                expert_review_status="seeded",
            ))
        db.commit()

    if db.query(Participant).filter(Participant.participant_id == "sample001").count() == 0:
        db.add(Participant(
            participant_id="sample001",
            participant_code="sample001",
            study_id=1,
            condition_id=4,
            group_id="G3",
            group_label="G3 Score + Comment feedback",
            session_id="demo",
        ))
        db.add(Participant(
            participant_id="sample002",
            participant_code="sample002",
            study_id=1,
            condition_id=2,
            group_id="G1",
            group_label="G1 Score-only feedback",
            session_id="demo",
        ))
        db.commit()

    if db.query(SystemVersion).count() == 0:
        db.add(SystemVersion())
        db.commit()
