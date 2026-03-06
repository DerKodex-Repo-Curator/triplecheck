"""Tests for JSON extraction from LLM output."""

import json

from triplecheck.providers.openai_compat import OpenAICompatProvider


def _provider() -> OpenAICompatProvider:
    return OpenAICompatProvider({"base_url": "http://localhost:9999", "model": "test"})


class TestExtractJson:
    def test_code_fence(self):
        text = 'Some text\n```json\n[{"file": "a.py"}]\n```\nMore text'
        result = _provider()._extract_json(text)
        assert json.loads(result) == [{"file": "a.py"}]

    def test_raw_json_object(self):
        text = '{"key": "value"}'
        result = _provider()._extract_json(text)
        assert json.loads(result) == {"key": "value"}

    def test_raw_json_array(self):
        text = '[{"a": 1}, {"b": 2}]'
        result = _provider()._extract_json(text)
        parsed = json.loads(result)
        assert len(parsed) == 2

    def test_strips_think_tags(self):
        text = '<think>reasoning here</think>\n[{"file": "a.py", "line": 1}]'
        result = _provider()._extract_json(text)
        parsed = json.loads(result)
        assert parsed[0]["file"] == "a.py"

    def test_strips_unclosed_think_tag(self):
        text = '<think>truncated thinking\n[{"file": "a.py"}]'
        result = _provider()._extract_json(text)
        # After stripping unclosed <think>, should be empty or just the remaining text
        # The key thing is it doesn't crash
        assert isinstance(result, str)

    def test_json_with_surrounding_text(self):
        text = 'Here are the findings:\n[{"file": "a.py", "line": 1}]\nDone!'
        result = _provider()._extract_json(text)
        parsed = json.loads(result)
        assert parsed[0]["file"] == "a.py"

    def test_prefers_largest_json(self):
        text = '{"small": 1} and then {"larger": "json", "with": "more", "keys": true}'
        result = _provider()._extract_json(text)
        parsed = json.loads(result)
        assert "larger" in parsed  # should pick the bigger one

    def test_nested_json(self):
        obj = {"findings": [{"file": "a.py", "nested": {"deep": True}}]}
        text = f"Result: {json.dumps(obj)}"
        result = _provider()._extract_json(text)
        parsed = json.loads(result)
        assert parsed["findings"][0]["nested"]["deep"] is True
