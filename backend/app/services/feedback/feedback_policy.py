CONDITION_PRESETS = {
    "assessment_only": {
        "show_transcript": False,
        "show_score": False,
        "show_diagnosis": False,
        "show_explanation": False,
        "show_action_guidance": False,
        "revision_allowed": False,
        "feedback_type": "assessment_only",
    },
    "transcript_only": {
        "show_transcript": True,
        "show_score": False,
        "show_diagnosis": False,
        "show_explanation": False,
        "show_action_guidance": False,
        "revision_allowed": True,
        "feedback_type": "transcript_only",
    },
    "score_only": {
        "show_transcript": True,
        "show_score": True,
        "show_diagnosis": False,
        "show_explanation": False,
        "show_action_guidance": False,
        "revision_allowed": True,
        "feedback_type": "score_only",
    },
    "explainable_word_sound_feedback": {
        "show_transcript": True,
        "show_score": True,
        "show_diagnosis": True,
        "show_explanation": True,
        "show_action_guidance": True,
        "revision_allowed": True,
        "feedback_type": "explainable",
    },
    "adaptive_word_sound_feedback": {
        "show_transcript": True,
        "show_score": True,
        "show_diagnosis": True,
        "show_explanation": True,
        "show_action_guidance": True,
        "revision_allowed": True,
        "feedback_type": "adaptive",
    },
    "human_validated_phoneme_feedback": {
        "show_transcript": True,
        "show_score": True,
        "show_diagnosis": False,
        "show_explanation": False,
        "show_action_guidance": False,
        "revision_allowed": True,
        "feedback_type": "human_validated_pending",
    },
    "teacher_orchestrated_feedback": {
        "show_transcript": True,
        "show_score": True,
        "show_diagnosis": True,
        "show_explanation": True,
        "show_action_guidance": True,
        "revision_allowed": True,
        "feedback_type": "teacher_orchestrated",
    },
}


def normalize_condition(value):
    key = (value or "explainable").strip().lower()
    aliases = {
        "control": "score_only",
        "condition_a": "assessment_only",
        "condition_b": "transcript_only",
        "condition_c": "score_only",
        "condition_d": "explainable_word_sound_feedback",
        "condition_e": "adaptive_word_sound_feedback",
        "condition_f": "human_validated_phoneme_feedback",
        "condition_g": "teacher_orchestrated_feedback",
        "explainable": "explainable_word_sound_feedback",
        "adaptive": "adaptive_word_sound_feedback",
        "human_validated": "human_validated_phoneme_feedback",
        "explainable_diagnostic_feedback": "explainable_word_sound_feedback",
        "adaptive_diagnostic_feedback": "adaptive_word_sound_feedback",
        "human_validated_feedback": "human_validated_phoneme_feedback",
    }
    return aliases.get(key, key if key in CONDITION_PRESETS else "explainable_word_sound_feedback")


def condition_policy(condition):
    return CONDITION_PRESETS[normalize_condition(condition)].copy()


def filter_feedback_for_condition(condition, transcript, score, structured_feedback):
    policy = condition_policy(condition)
    result = {
        "feedback_type": policy["feedback_type"],
        "show_transcript": policy["show_transcript"],
        "show_score": policy["show_score"],
        "show_diagnosis": policy["show_diagnosis"],
        "show_explanation": policy["show_explanation"],
        "show_action_guidance": policy["show_action_guidance"],
        "revision_allowed": policy["revision_allowed"],
        "asr_transcript": transcript if policy["show_transcript"] else "",
        "overall_score": score if policy["show_score"] else None,
        "practice_score": score if policy["show_score"] else None,
        "score_breakdown": structured_feedback.get("score_breakdown", {}) if policy["show_score"] else {},
        "score_note": structured_feedback.get("score_note", "This is a practice indicator, not a validated proficiency score."),
    }
    if policy["feedback_type"] == "assessment_only":
        result["comment"] = "This is an assessment-only task. Feedback is hidden for research design reasons."
        return result
    if policy["feedback_type"] == "transcript_only":
        result["comment"] = "Review the transcript and decide whether the sentence was recognized as intended."
        return result
    if policy["feedback_type"] == "score_only":
        result["comment"] = structured_feedback.get("comment") or "Your current clarity score is %s. Please practise again." % score
        return result
    if policy["feedback_type"] == "human_validated_pending":
        result["comment"] = "Draft feedback has been generated and is waiting for human validation."
        return result
    for key in [
        "word_label",
        "sound_focus_label",
        "evidence_level_label",
        "diagnosis",
        "criterion_link",
        "explanation",
        "action_guidance",
        "revision_instruction",
        "revision_goal",
        "metacognitive_prompt",
        "practice_path",
        "speaking_target",
        "teacher_review_recommended",
    ]:
        if key in structured_feedback:
            result[key] = structured_feedback[key]
    if policy["feedback_type"] == "adaptive":
        result["metacognitive_prompt"] = result.get("metacognitive_prompt") or "Check whether this issue has appeared in your previous attempts, then set one revision goal."
    if policy["feedback_type"] == "teacher_orchestrated":
        result["teacher_review_recommended"] = True
        result["metacognitive_prompt"] = result.get("metacognitive_prompt") or "Your teacher may use this attempt to plan follow-up practice."
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
