def asr_supported_template(target_word, target_phoneme, speaking_target):
    if target_phoneme:
        return {
            "word_label": target_word,
            "sound_focus_label": "/%s/" % target_phoneme,
            "evidence_level_label": "ASR-supported cue",
            "diagnosis": "The focus word '%s' was not clearly recognized." % target_word,
            "criterion_link": "This task focuses on pronunciation clarity for the /%s/ sound in '%s'." % (target_phoneme, target_word),
            "explanation": "This is an ASR-supported cue, not an exact pronunciation diagnosis. It suggests that the word may need attention during practice.",
            "action_guidance": "Practise /%s/ in '%s', then read the phrase containing the word, and finally read the full sentence." % (target_phoneme, target_word),
            "revision_goal": "In your next attempt, try to make '%s' easier to recognize while keeping the sentence smooth." % target_word,
            "practice_path": "sound -> word -> phrase -> sentence",
            "speaking_target": speaking_target,
        }
    return generic_no_phoneme_template(target_word, speaking_target)


def model_supported_template(target_word, target_phoneme, score=None, confidence=None, speaking_target="pronunciation_clarity"):
    return {
        "word_label": target_word,
        "sound_focus_label": "/%s/" % target_phoneme if target_phoneme else "",
        "evidence_level_label": "model-supported diagnosis",
        "diagnosis": "The pronunciation model indicates that /%s/ in '%s' may need targeted practice." % (target_phoneme, target_word),
        "criterion_link": "This relates to pronunciation clarity and listener recognition of the focus word.",
        "explanation": "The model evidence suggests that this sound may be less clear than expected in this attempt.",
        "action_guidance": "Practise the target sound /%s/, then the word '%s', then the full sentence." % (target_phoneme, target_word),
        "revision_goal": "In your next attempt, try to improve the clarity of /%s/ in '%s'." % (target_phoneme, target_word),
        "practice_path": "sound -> word -> phrase -> sentence",
        "speaking_target": speaking_target,
        "model_score": score,
        "model_confidence": confidence,
    }


def human_validated_template(target_word, target_phoneme, observed_phoneme, speaking_target="pronunciation_clarity"):
    return {
        "word_label": target_word,
        "sound_focus_label": "/%s/" % target_phoneme if target_phoneme else "",
        "evidence_level_label": "human-validated diagnosis",
        "diagnosis": "In '%s', /%s/ appears to have been produced closer to /%s/." % (target_word, target_phoneme, observed_phoneme),
        "criterion_link": "This affects pronunciation clarity because the target sound helps listeners identify the intended word.",
        "explanation": "The target sound and the observed sound use different articulation patterns, so the word may be heard as a different word.",
        "action_guidance": "Practise the contrast /%s/ versus /%s/, then read '%s' slowly, then re-record the full sentence." % (target_phoneme, observed_phoneme, target_word),
        "revision_goal": "In your next attempt, try to keep /%s/ clear in '%s'." % (target_phoneme, target_word),
        "practice_path": "sound contrast -> word -> sentence",
        "speaking_target": speaking_target,
    }


def repeated_phoneme_template(target_word, target_phoneme, speaking_target="pronunciation_clarity"):
    return {
        "word_label": target_word,
        "sound_focus_label": "/%s/" % target_phoneme,
        "evidence_level_label": "ASR-supported cue",
        "diagnosis": "The /%s/ focus has appeared in several attempts." % target_phoneme,
        "criterion_link": "This suggests a persistent pronunciation focus in your current practice.",
        "explanation": "Repeated issues often improve through short targeted practice before full-sentence repetition.",
        "action_guidance": "Practise /%s/ alone, then '%s', then the phrase, then the full sentence." % (target_phoneme, target_word),
        "revision_goal": "Check whether the focus word becomes clearer after this step-by-step practice.",
        "metacognitive_prompt": "What did you change when you practised this sound?",
        "practice_path": "sound -> word -> phrase -> sentence",
        "speaking_target": speaking_target,
        "teacher_review_recommended": True,
    }


def generic_no_phoneme_template(target_word, speaking_target):
    return {
        "word_label": target_word,
        "sound_focus_label": "",
        "evidence_level_label": "ASR-supported cue",
        "diagnosis": "The focus word '%s' was not clearly recognized." % target_word if target_word else "A focus word was not clearly recognized.",
        "criterion_link": "Sound-specific feedback is unavailable for this task because no focus phoneme was defined.",
        "explanation": "Use this as a word-level clarity cue rather than a sound-level diagnosis.",
        "action_guidance": "Practise the focus word, then read the phrase and full sentence again.",
        "revision_goal": "Try to make the focus word easier to recognize in your next attempt.",
        "practice_path": "word -> phrase -> sentence",
        "speaking_target": speaking_target,
    }
