import pytest

from aether_engine.inscriptions import render_inscription


@pytest.mark.parametrize(
    ("text", "latin", "egyptian", "babylonian", "meaning"),
    [
        ("truth", "veritas", "mꜣꜥt", "kīttum", "truth"),
        ("peace", "pax", "ḥtp", "šulmu", "peace"),
        ("life", "vita", "ꜥnḫ", "balāṭu", "life"),
        ("house", "domus", "pr", "bītum", "house"),
        ("sun", "sol", "rꜥ", "šamšu", "sun"),
        (
            "truth and peace",
            "veritas et pax",
            "mꜣꜥt ḥtp",
            "kīttum u šulmu",
            "truth and peace",
        ),
    ],
)
def test_reviewed_inscriptions_preserve_meaning(
    text, latin, egyptian, babylonian, meaning
):
    result = render_inscription(f"  {text.upper()}!  ")

    assert result["status"] == "REVIEWED_APPROXIMATION"
    assert result["modes"] == {
        "english": f"  {text.upper()}!  ",
        "latin": latin,
        "egyptian_transliteration": egyptian,
        "old_babylonian_transliteration": babylonian,
    }
    assert meaning in result["meaning"].lower()
    assert result["command_safe"] is False


def test_unknown_inscription_fails_closed_without_losing_original():
    original = '<script>alert("x")</script> deploy everything'

    result = render_inscription(original)

    assert result["status"] == "UNAVAILABLE_NOT_IN_REVIEWED_PHRASEBOOK"
    assert result["exact_original"] == original
    assert result["modes"]["english"] == original
    assert all(
        value is None
        for name, value in result["modes"].items()
        if name != "english"
    )
    assert "nothing was invented" in result["notice"]


def test_inscription_rejects_invalid_text():
    with pytest.raises(ValueError, match="Enter text"):
        render_inscription(" ")
    with pytest.raises(ValueError, match="240"):
        render_inscription("x" * 241)
    with pytest.raises(ValueError, match="must be a string"):
        render_inscription(3)
