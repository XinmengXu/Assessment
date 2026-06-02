from app.analysis.text_alignment import align_text, normalize_words


def test_normalize_words_removes_case_and_punctuation():
    assert normalize_words("The thin path!") == ["the", "thin", "path"]


def test_align_text_finds_missing_and_substitution():
    result = align_text("The thin path is clear", "the tin path clear")
    assert result["word_match_score"] < 100
    assert "is" in result["missing_words"]
    assert any(item["expected"] == "thin" for item in result["substitutions"])


def test_align_text_reports_insertions_and_operations():
    result = align_text("The thin path is clear.", "the very thin path is clear now")
    assert result["inserted_words"] == ["very", "now"]
    assert result["alignment_operations"]
    assert result["word_match_score"] == 100


def test_align_text_handles_empty_transcript():
    result = align_text("The thin path", "")
    assert result["word_match_score"] == 0
    assert result["missing_words"] == ["the", "thin", "path"]
