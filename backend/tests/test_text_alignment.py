from app.analysis.text_alignment import align_text, normalize_words


def test_normalize_words_removes_case_and_punctuation():
    assert normalize_words("The thin path!") == ["the", "thin", "path"]


def test_align_text_finds_missing_and_substitution():
    result = align_text("The thin path is clear", "the tin path clear")
    assert result["word_match_score"] < 100
    assert "is" in result["missing_words"]
    assert any(item["expected"] == "thin" for item in result["substitutions"])
