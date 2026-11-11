from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path


class _EmbedAudit(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.script_count = 0
        self.external_resources: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script":
            self.script_count += 1
        for name, value in attrs:
            if name in {"href", "src"} and value is not None:
                if value.startswith(("http://", "https://", "//")):
                    self.external_resources.append(value)


def test_wix_api_website_is_static_and_keeps_api_private() -> None:
    embed_path = Path(__file__).resolve().parents[1] / "website" / "wix-embed.html"
    content = embed_path.read_text(encoding="utf-8")
    audit = _EmbedAudit()
    audit.feed(content)

    assert audit.script_count == 0
    assert audit.external_resources == []
    assert "AETHER_API_TOKEN" in content
    assert "does not proxy requests" in content
    assert "API access is not hosted here" in content
