import pytest
from unittest.mock import patch, MagicMock


def test_build_prompt_includes_topic():
    from journal_generator import build_prompt
    profile = {"background": "DS expert", "explanation_styles": ["Show the math"], "detail_level": "deep"}
    sources = [{"name": "notes.txt", "type": "TXT", "content": "attention is all you need"}]
    prompt = build_prompt("Transformers", sources, profile)
    assert "Transformers" in prompt
    assert "attention is all you need" in prompt
    assert "DS expert" in prompt
    assert "deep" in prompt


def test_build_prompt_no_profile():
    from journal_generator import build_prompt
    sources = [{"name": "notes.txt", "type": "TXT", "content": "some content"}]
    prompt = build_prompt("Topic", sources, None)
    assert "Topic" in prompt
    assert "some content" in prompt


def test_parse_response_valid():
    from journal_generator import parse_response
    raw = '{"summary": "s", "journal": "j", "concepts": ["c1"], "resources": []}'
    result = parse_response(raw)
    assert result["summary"] == "s"
    assert result["concepts"] == ["c1"]


def test_parse_response_with_markdown_fence():
    from journal_generator import parse_response
    raw = '```json\n{"summary": "s", "journal": "j", "concepts": [], "resources": []}\n```'
    result = parse_response(raw)
    assert result["summary"] == "s"


def test_parse_response_invalid_returns_error():
    from journal_generator import parse_response
    result = parse_response("not json at all")
    assert "error" in result


def test_generate_journal_calls_claude():
    import journal_generator
    profile = {"background": "expert", "explanation_styles": [], "detail_level": "standard"}
    sources = [{"name": "f.txt", "type": "TXT", "content": "content"}]
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = '{"summary":"s","journal":"j","concepts":[],"resources":[]}'
    with patch("journal_generator.subprocess.run", return_value=mock_result) as mock_run:
        result = journal_generator.generate_journal("Topic", sources, profile)
    assert mock_run.called
    call_args = mock_run.call_args[0][0]
    assert "claude" in call_args
    assert "--print" in call_args
    assert result["summary"] == "s"


def test_generate_journal_cli_error():
    import journal_generator
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "CLI failed"
    sources = [{"name": "f.txt", "type": "TXT", "content": "content"}]
    with patch("journal_generator.subprocess.run", return_value=mock_result):
        result = journal_generator.generate_journal("Topic", sources, None)
    assert "error" in result
    assert "CLI failed" in result["error"]


def test_generate_journal_no_sources():
    import journal_generator
    result = journal_generator.generate_journal("Topic", [], None)
    assert "error" in result
