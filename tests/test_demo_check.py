"""`./do demo-check`: the pre-demo timing check (scripts/demo_check.py), offline.

The shapes are the stalls measured on ecommerce.aito.ai on 2026-11-24: a 5 s DNS lookup on the
measuring machine, and a 2.4 s TCP connect after a fast lookup.
"""
import pytest

from scripts.demo_check import Call, parse_curl_timing, stage_durations, slow_stage, verdict


def line(dns=0.01, connect=0.03, tls=0.08, ttfb=0.20, total=0.25, status=200, size=116):
    return f"{dns} {connect} {tls} {ttfb} {total} {status} {size}"


def test_curl_timing_is_parsed_into_a_call():
    call = parse_curl_timing("/api/version", line(dns=0.15, total=0.9, size=435000))

    assert (call.path, call.status, call.size_bytes) == ("/api/version", 200, 435000)
    assert call.total == pytest.approx(0.9)


def test_each_stage_is_the_time_between_two_curl_marks():
    call = parse_curl_timing("/x", line(dns=0.1, connect=0.3, tls=0.7, ttfb=1.0, total=1.4))

    stages = stage_durations(call)

    assert stages == pytest.approx({"dns": 0.1, "connect": 0.2, "tls": 0.4, "server": 0.3, "transfer": 0.4})


def test_a_plain_http_call_has_no_tls_stage():
    call = parse_curl_timing("/x", line(dns=0.0, connect=0.01, tls=0.0, ttfb=0.05, total=0.06))

    assert stage_durations(call)["tls"] == 0.0
    assert stage_durations(call)["server"] == pytest.approx(0.04)


@pytest.mark.parametrize("timing, stage", [
    (dict(dns=5.05, connect=5.08, tls=5.15, ttfb=5.3, total=5.68), "dns"),
    (dict(dns=0.15, connect=2.51, tls=2.6, ttfb=2.7, total=2.8), "connect"),
    (dict(dns=0.02, connect=0.05, tls=1.5, ttfb=1.6, total=1.7), "tls"),
    (dict(dns=0.02, connect=0.05, tls=0.1, ttfb=2.2, total=2.3), "server"),
    (dict(dns=0.02, connect=0.05, tls=0.1, ttfb=0.32, total=2.51), "transfer"),
])
def test_the_slow_stage_is_named_when_one_stage_takes_over_a_second(timing, stage):
    assert slow_stage(parse_curl_timing("/x", line(**timing))) == stage


def test_a_call_with_no_stage_over_a_second_is_not_slow():
    assert slow_stage(parse_curl_timing("/x", line(dns=0.9, connect=1.0, tls=1.1, ttfb=1.6, total=2.5))) is None


def test_a_failed_status_is_reported_whatever_the_time():
    call = parse_curl_timing("/api/retention", line(status=503))

    assert call.status == 503
    assert "HTTP 503" in verdict([call])


def test_the_verdict_is_ready_when_every_call_is_fast_and_ok():
    calls = [parse_curl_timing(p, line(total=0.3)) for p in ("/api/version", "/shop/")]

    assert verdict(calls).startswith("READY")
    assert "0.3" in verdict(calls)


def test_a_dns_stall_is_blamed_on_the_resolver_not_on_the_demo():
    calls = [parse_curl_timing("/api/version", line()),
             parse_curl_timing("/api/version", line(dns=5.05, connect=5.08, tls=5.15, ttfb=5.3, total=5.68))]

    text = verdict(calls)

    assert text.startswith("SLOW")
    assert "1 of 2 calls" in text
    assert "dns" in text and "resolver" in text


def test_a_connect_stall_is_blamed_on_the_network_or_the_host_proxy():
    calls = [parse_curl_timing("/api/version", line(dns=0.15, connect=2.51, tls=2.6, ttfb=2.7, total=2.8))]

    assert "connect" in verdict(calls) and "proxy" in verdict(calls)


def test_a_line_that_is_not_seven_numbers_fails_loudly():
    with pytest.raises(ValueError, match="/api/version"):
        parse_curl_timing("/api/version", "0.1 0.2 curl: (28) timed out")
