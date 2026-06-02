from pathlib import Path


def test_github_pages_is_not_forced_to_demo_mode():
    client_path = Path(__file__).resolve().parents[2] / "frontend" / "src" / "api" / "client.ts"
    text = client_path.read_text(encoding="utf-8")
    assert "hostname.endsWith(\"github.io\")" not in text
    assert "hostname.endsWith('github.io')" not in text
    assert "/health" in text
    assert "VITE_API_BASE is not configured" in text
