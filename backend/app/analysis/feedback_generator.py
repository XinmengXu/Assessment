def generate_feedback(group_id, score, target_text, transcript, alignment, features):
    if group_id == "control":
        return {
            "overall_score": score,
            "comment": "Your current clarity score is %s. Please practise again and try to read the sentence more clearly." % score,
        }

    issue_word = None
    if alignment["missing_words"]:
        issue_word = alignment["missing_words"][0]
        diagnosis = "The word '%s' may not have been clearly recognized." % issue_word
    elif alignment["substitutions"]:
        sub = alignment["substitutions"][0]
        issue_word = sub["expected"]
        diagnosis = "The word '%s' may have sounded like '%s'." % (sub["expected"], sub.get("heard") or "another word")
    elif features["speech_rate_wpm"] < 70:
        diagnosis = "The reading may be slow enough to reduce fluency."
    elif features["speech_rate_wpm"] > 180:
        diagnosis = "The reading may be fast enough to reduce intelligibility."
    elif features["long_pause_count"] > 0:
        diagnosis = "There may be one or more long pauses in the sentence."
    else:
        diagnosis = "Most target words were recognized clearly in this attempt."

    if issue_word:
        explanation = "This word carries sentence meaning. If it is unclear, a listener may misunderstand the message."
        action = "Practise '%s' three times, then say the full sentence again with steady rhythm." % issue_word
        revision = "After re-recording, compare whether '%s' is recognized more clearly." % issue_word
    elif "slow" in diagnosis:
        explanation = "Very slow reading can make the sentence sound less connected and harder to follow."
        action = "Practise the sentence in short chunks, then connect the chunks at a natural pace."
        revision = "Re-record and check whether the speech rate moves closer to a natural read-aloud pace."
    elif "fast" in diagnosis:
        explanation = "Very fast reading can blur final sounds and make key words harder to recognize."
        action = "Slow down slightly and keep final consonants clear."
        revision = "Re-record and compare the transcript and score."
    else:
        explanation = "Clear recognition suggests the main words were understandable in this attempt."
        action = "Repeat once more while keeping the same clarity and a smooth rhythm."
        revision = "Use the next attempt to check whether the clarity score remains stable or improves."

    return {
        "overall_score": score,
        "diagnosis": diagnosis,
        "explanation": explanation,
        "action_guidance": action,
        "revision_instruction": revision,
        "automatic_feedback_notice": "Automatically generated learning support, not a high-stakes assessment.",
    }
