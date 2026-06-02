CONDITION_PRESETS = {
    "G0": {
        "condition_group": "G0",
        "condition_name": "G0 Practice-only",
        "friendly_label": "Practice",
        "show_transcript": True,
        "show_score": False,
        "show_comment": False,
        "show_word_focus": False,
        "show_sound_focus": False,
        "show_practice_suggestion": False,
        "allow_revision": True,
        "revision_allowed": True,
        "enable_teacher_feedback": False,
        "enable_peer_feedback": False,
        "feedback_type": "practice_only",
    },
    "G1": {
        "condition_group": "G1",
        "condition_name": "G1 Score-only feedback",
        "friendly_label": "Score feedback",
        "show_transcript": True,
        "show_score": True,
        "show_comment": False,
        "show_word_focus": False,
        "show_sound_focus": False,
        "show_practice_suggestion": False,
        "allow_revision": True,
        "revision_allowed": True,
        "enable_teacher_feedback": False,
        "enable_peer_feedback": False,
        "feedback_type": "score_only",
    },
    "G2": {
        "condition_group": "G2",
        "condition_name": "G2 Comment-only feedback",
        "friendly_label": "Comment feedback",
        "show_transcript": True,
        "show_score": False,
        "show_comment": True,
        "show_word_focus": True,
        "show_sound_focus": True,
        "show_practice_suggestion": True,
        "allow_revision": True,
        "revision_allowed": True,
        "enable_teacher_feedback": False,
        "enable_peer_feedback": False,
        "feedback_type": "comment_only",
    },
    "G3": {
        "condition_group": "G3",
        "condition_name": "G3 Score + Comment feedback",
        "friendly_label": "Score and comment feedback",
        "show_transcript": True,
        "show_score": True,
        "show_comment": True,
        "show_word_focus": True,
        "show_sound_focus": True,
        "show_practice_suggestion": True,
        "allow_revision": True,
        "revision_allowed": True,
        "enable_teacher_feedback": False,
        "enable_peer_feedback": False,
        "feedback_type": "score_plus_comment",
    },
}

OPTIONAL_WORKFLOWS = ["teacher_feedback", "peer_feedback", "teacher_moderated_peer_feedback"]


def normalize_condition(value):
    key = (value or "G3").strip()
    upper = key.upper()
    aliases = {
        "PRACTICE_ONLY": "G0",
        "PRACTICE": "G0",
        "ASSESSMENT_ONLY": "G0",
        "CONDITION_A": "G0",
        "SCORE_ONLY": "G1",
        "CONTROL": "G1",
        "CONDITION_C": "G1",
        "COMMENT_ONLY": "G2",
        "TRANSCRIPT_ONLY": "G2",
        "CONDITION_B": "G2",
        "SCORE_PLUS_COMMENT": "G3",
        "SCORE_COMMENT": "G3",
        "EXPLAINABLE": "G3",
        "EXPLAINABLE_WORD_SOUND_FEEDBACK": "G3",
        "ADAPTIVE": "G3",
        "ADAPTIVE_WORD_SOUND_FEEDBACK": "G3",
        "HUMAN_VALIDATED": "G3",
        "HUMAN_VALIDATED_FEEDBACK": "G3",
        "HUMAN_VALIDATED_PHONEME_FEEDBACK": "G3",
        "TEACHER_ORCHESTRATED_FEEDBACK": "G3",
        "AI_FEEDBACK": "G3",
        "AI_PLUS_TEACHER_FEEDBACK": "G3",
    }
    return aliases.get(upper, upper if upper in CONDITION_PRESETS else "G3")


def condition_policy(condition):
    return CONDITION_PRESETS[normalize_condition(condition)].copy()


def _comment_fields(structured_feedback):
    word = structured_feedback.get("word_label") or structured_feedback.get("word_to_practise") or "focus word"
    sound = structured_feedback.get("sound_focus_label") or structured_feedback.get("target_sound") or ""
    practice = structured_feedback.get("practice_suggestion") or structured_feedback.get("action_guidance") or structured_feedback.get("practice_path") or ""
    revision = structured_feedback.get("revision_goal") or structured_feedback.get("revision_instruction") or ""
    if not practice:
        if sound:
            practice = "Practise %s in '%s', then read the phrase, then read the full sentence again." % (sound, word)
        else:
            practice = "Listen to the model audio, repeat '%s', then re-record the sentence." % word
    if not revision:
        revision = "Try to make '%s' clearer in your next recording." % word if word != "focus word" else "Try to make the focus word easier to recognize."
    return {
        "word_to_practise": word,
        "target_sound": sound,
        "practice_suggestion": practice,
        "revision_goal": revision,
        "evidence_note": "AI cue based on speech recognition. Use it as practice support.",
    }


def filter_feedback_for_condition(condition, transcript, score, structured_feedback):
    policy = condition_policy(condition)
    show_score = policy["show_score"]
    show_comment = policy["show_comment"]
    result = {
        "condition_group": policy["condition_group"],
        "condition_label": policy["friendly_label"],
        "feedback_type": policy["feedback_type"],
        "show_transcript": policy["show_transcript"],
        "show_score": show_score,
        "show_comment": show_comment,
        "show_word_focus": policy["show_word_focus"],
        "show_sound_focus": policy["show_sound_focus"],
        "show_practice_suggestion": policy["show_practice_suggestion"],
        "show_diagnosis": show_comment,
        "show_explanation": False,
        "show_action_guidance": show_comment,
        "revision_allowed": policy["revision_allowed"],
        "allow_revision": policy["allow_revision"],
        "asr_transcript": transcript if policy["show_transcript"] else "",
        "overall_score": score if show_score else None,
        "practice_score": score if show_score else None,
        "score_value": score if show_score else None,
        "score_hidden": not show_score,
        "comment_hidden": not show_comment,
        "score_breakdown": structured_feedback.get("score_breakdown", {}) if show_score else {},
        "score_note": "Practice clarity score. This is not a speaking proficiency score.",
        "tts_required": True,
    }
    if show_comment:
        fields = _comment_fields(structured_feedback)
        result.update(fields)
        result["word_label"] = fields["word_to_practise"]
        result["sound_focus_label"] = fields["target_sound"]
        result["comment"] = result["practice_suggestion"]
    else:
        result["comment"] = ""
    return result


def derive_feedback_use_state(feedback_viewed, has_revision, improved, sustained=False):
    if sustained:
        return "F4"
    if feedback_viewed and has_revision and improved:
        return "F3"
    if feedback_viewed and has_revision:
        return "F2"
    if feedback_viewed:
        return "F1"
    return "F0"
