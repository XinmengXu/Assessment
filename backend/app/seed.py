import json

from .database import Participant, Task


TASKS = [
    ("The thin path winds through three quiet fields.", ["thin", "through", "three"], "theta and rhythm", "medium"),
    ("Ray left a red ribbon near the library rail.", ["ray", "red", "ribbon", "library"], "r and l contrast", "medium"),
    ("Please keep the final sound in kept, asked, and missed.", ["kept", "asked", "missed"], "final consonants", "hard"),
    ("A small blue clock stood beside the glass plant.", ["small", "blue", "clock", "glass"], "consonant clusters", "hard"),
    ("She thought the weather would improve by Thursday.", ["thought", "weather", "Thursday"], "th sounds", "hard"),
    ("Mark brought fresh fruit for breakfast before class.", ["brought", "fresh", "fruit", "breakfast"], "clusters and stress", "medium"),
    ("The light rain fell slowly on the river road.", ["light", "rain", "river", "road"], "l and r contrast", "easy"),
    ("We watched the brave child climb the steep steps.", ["watched", "brave", "child", "steep", "steps"], "final sounds and clusters", "hard"),
    ("Laura rarely arrives late for reading lessons.", ["Laura", "rarely", "late", "reading"], "r and l contrast", "medium"),
    ("The student explained the problem in a clear voice.", ["student", "explained", "problem", "clear"], "stress and clarity", "medium"),
    ("I placed the black cup next to the green plate.", ["placed", "black", "cup", "green", "plate"], "clusters", "medium"),
    ("Those three brothers breathe slowly before speaking.", ["those", "three", "brothers", "breathe"], "voiced and voiceless th", "hard"),
    ("The last train stopped at the old stone bridge.", ["last", "stopped", "old", "stone", "bridge"], "final consonants", "medium"),
    ("Fresh spring flowers grow beside the playground.", ["fresh", "spring", "flowers", "grow", "playground"], "clusters and rhythm", "hard"),
    ("Please read each phrase with strong sentence stress.", ["read", "phrase", "strong", "stress"], "stress", "medium"),
    ("The girl carried a round orange bag to school.", ["girl", "round", "orange", "school"], "r coloring and final sounds", "medium"),
    ("He found twelve clean spoons in the drawer.", ["found", "twelve", "clean", "spoons", "drawer"], "clusters", "hard"),
    ("The speaker paused briefly after each thought group.", ["speaker", "paused", "briefly", "thought", "group"], "pausing and thought groups", "medium"),
    ("A friendly clerk wrote the price on a card.", ["friendly", "clerk", "wrote", "price", "card"], "r and clusters", "medium"),
    ("Slow practice helps learners notice difficult sounds.", ["slow", "practice", "learners", "difficult", "sounds"], "metacognitive fluency", "easy"),
]


def seed_database(db):
    if db.query(Task).count() == 0:
        for target_text, focus_words, speaking_target, difficulty in TASKS:
            db.add(Task(
                target_text=target_text,
                focus_words=json.dumps(focus_words),
                speaking_target=speaking_target,
                difficulty=difficulty,
                model_audio_path="",
            ))
    if db.query(Participant).filter(Participant.participant_id == "sample001").count() == 0:
        db.add(Participant(participant_id="sample001", group_id="explainable", session_id="demo"))
    db.commit()
