import json


def precision_recall_f1(system_items, human_items):
    system = set(system_items or [])
    human = set(human_items or [])
    tp = len(system & human)
    precision = tp / len(system) if system else 0.0
    recall = tp / len(human) if human else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3)}


def annotation_agreement(attempt, annotation):
    system_missing = json.loads(attempt.missing_words_json or "[]")
    human_missing = json.loads(annotation.human_missing_words_json or "[]")
    return {
        "attempt_id": attempt.id,
        "missing_words": precision_recall_f1(system_missing, human_missing),
        "score": attempt.assessment_score,
        "human_pronunciation_rating": annotation.pronunciation_rating,
        "human_fluency_rating": annotation.fluency_rating,
        "human_comprehensibility_rating": annotation.comprehensibility_rating,
    }
