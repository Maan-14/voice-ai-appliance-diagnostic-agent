"""Unit tests for sentence chunking used by streaming TTS."""
from __future__ import annotations

# Mirrors web/static/js/voice.js pullSentenceChunks for regression safety.


def pull_sentence_chunks(buffer: str, min_chunk: int = 18) -> tuple[list[str], str]:
    import re

    sentences: list[str] = []
    re_end = re.compile(r"[.!?;]+(?=\s|$)")
    hits = [m.end() for m in re_end.finditer(buffer)]
    last_cut = 0
    for end in hits:
        chunk = buffer[last_cut:end].strip()
        if len(chunk) >= min_chunk or chunk.endswith((".", "!", "?")):
            sentences.append(chunk)
            last_cut = end
    rest = buffer[last_cut:]
    return sentences, rest


def test_pull_two_sentences():
    buf = "Your dryer is not producing enough heat. There are a few things we can check."
    sents, rest = pull_sentence_chunks(buf)
    assert len(sents) == 2
    assert "heat" in sents[0]
    assert "check" in sents[1]
    assert rest.strip() == ""


def test_incomplete_held_back():
    buf = "Based on what you've described, your dryer is"
    sents, rest = pull_sentence_chunks(buf)
    assert sents == []
    assert "dryer is" in rest


def test_incremental():
    buf = ""
    parts = [
        "Your dryer is not producing enough heat. ",
        "There are a few things we can check.",
    ]
    out = []
    for p in parts:
        buf += p
        sents, buf = pull_sentence_chunks(buf)
        out.extend(sents)
    if buf.strip():
        out.append(buf.strip())
    assert len(out) >= 2
