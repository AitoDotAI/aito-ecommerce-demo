"""A period with nothing ticked is counted once: the count reads every customer's lines and is slow on the deployed host."""
import src.customer_profile_routes as routes


def test_the_same_period_is_counted_once(monkeypatch):
    calls = []
    monkeypatch.setattr(routes, "preference_changes", lambda *args: calls.append("preferences") or [])
    monkeypatch.setattr(routes, "segment_changes", lambda *args: calls.append("segments") or [])
    monkeypatch.setattr(routes, "facts", lambda: {"customers": {}})
    monkeypatch.setattr(routes, "rows", lambda: {"customers": {}, "products": {}})
    monkeypatch.setattr(routes, "_selection", lambda conditions: {"options": {}})
    routes._everyone_mix.cache_clear()

    first = routes._everyone_mix(("2026-02", "2026-03"), "2026-02", "2026-03")
    second = routes._everyone_mix(("2026-02", "2026-03"), "2026-02", "2026-03")
    other = routes._everyone_mix(("2026-03", "2026-04"), "2026-03", "2026-04")

    assert first is second and other is not first
    assert calls == ["preferences", "segments", "preferences", "segments"]
