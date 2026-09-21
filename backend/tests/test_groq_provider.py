"""GroqProvider unit tests. A stub replaces the Groq SDK client, so no network."""
from types import SimpleNamespace

from src.llm.groq import GroqProvider


def stub_client(deltas, captured):
    """Mimics groq.Groq just enough: records the kwargs, replays scripted deltas."""

    def create(**kwargs):
        captured.update(kwargs)
        return iter(
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=d))])
            for d in deltas
        )

    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def make(deltas, captured=None):
    if captured is None:
        captured = {}
    return GroqProvider(model="m", client=stub_client(deltas, captured))


def test_empty_deltas_are_dropped():
    # Groq emits empty deltas at stream edges; forwarding them would render
    # as stray blank frames on the client.
    tokens = list(make(["", "Hi", "", "!"]).stream([{"role": "user", "content": "x"}]))

    assert tokens == ["Hi", "!"]


def test_system_prompt_becomes_the_first_message():
    captured = {}

    list(make(["ok"], captured).stream([{"role": "user", "content": "x"}], "Be brief."))

    assert captured["messages"][0] == {"role": "system", "content": "Be brief."}
    assert captured["messages"][1] == {"role": "user", "content": "x"}


def test_no_system_prompt_means_no_system_message():
    captured = {}

    list(make(["ok"], captured).stream([{"role": "user", "content": "x"}]))

    assert captured["messages"] == [{"role": "user", "content": "x"}]


def test_streams_with_the_configured_model():
    captured = {}

    list(make(["ok"], captured).stream([{"role": "user", "content": "x"}]))

    assert captured["model"] == "m"
    assert captured["stream"] is True
