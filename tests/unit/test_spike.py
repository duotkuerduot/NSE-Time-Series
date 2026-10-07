from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest

from nsefc.calendar import TradingCalendar
from nsefc.config import PolitenessSettings, ProviderDefinition
from nsefc.domain import PriceBasis
from nsefc.ingestion.spike import (
    Observation,
    PoliteClient,
    backcheck,
    candidate_urls,
    latest_probe_session,
    load_observations,
    observe,
    render_url,
    retry_after_seconds,
    save_observations,
    summarise,
)
from nsefc.storage.objectstore import LocalObjectStore

PDF = {"content-type": "application/pdf"}

KINGDOM = ProviderDefinition(
    provider_id="kingdom",
    name="Kingdom",
    role="validator_candidate",
    price_basis=PriceBasis.VWAP,
    format="pdf",
    url_template="https://kingdomsecurities.co.ke/wp-content/uploads/{UPLOAD_YYYY}/{UPLOAD_MM}/Daily-Market-Wrap-{DD}-{Mon}-{YYYY}.pdf",
)
NSE = ProviderDefinition(
    provider_id="nse_pricelist",
    name="NSE",
    role="primary_candidate",
    price_basis=PriceBasis.VWAP,
    format="pdf",
    url_template="https://www.nse.co.ke/dataservices/wp-content/uploads/{DD}-{MON}-{YY}.pdf",
)


def test_render_url_matches_observed_patterns() -> None:
    day = date(2026, 10, 7)
    assert render_url(KINGDOM.url_template or "", day).endswith(
        "/2026/10/Daily-Market-Wrap-07-Oct-2026.pdf"
    )
    assert render_url(NSE.url_template or "", date(2026, 10, 6)).endswith("/06-OCT-26.pdf")


def client_for(handler, sleeps: list[float] | None = None) -> PoliteClient:  # type: ignore[no-untyped-def]
    recorded = sleeps if sleeps is not None else []
    return PoliteClient(
        PolitenessSettings(retries=1),
        transport=httpx.MockTransport(handler),
        sleep=recorded.append,
        clock=lambda: 0.0,
    )


def test_observe_archives_real_documents(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["user-agent"].startswith("nsefc/")
        return httpx.Response(
            200, content=b"%PDF-1.7 wrap", headers={"content-type": "application/pdf"}
        )

    store = LocalObjectStore(tmp_path)
    obs = observe(
        client_for(handler),
        KINGDOM,
        date(2026, 10, 7),
        mode="probe",
        store=store,
        now=lambda: datetime(2026, 10, 7, 17, 8, tzinfo=UTC),
    )
    assert obs.available and obs.archived_key and store.exists(obs.archived_key)


def test_soft_404_is_not_available(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=b"<html>Page not found</html>", headers={"content-type": "text/html"}
        )

    obs = observe(
        client_for(handler),
        KINGDOM,
        date(2026, 10, 7),
        mode="probe",
        store=LocalObjectStore(tmp_path),
    )
    assert not obs.available and obs.archived_key is None and "soft 404" in (obs.error or "")


def test_retries_server_errors_with_backoff() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(503) if len(calls) == 1 else httpx.Response(404)

    sleeps: list[float] = []
    obs = observe(client_for(handler, sleeps), KINGDOM, date(2026, 10, 7), mode="probe", store=None)
    assert len(calls) == 2 and obs.status_code == 404 and not obs.available
    assert 2.0 in sleeps  # first backoff step


def test_politeness_spaces_requests_per_host() -> None:
    sleeps: list[float] = []
    ticks = iter([0.0, 0.2, 0.2])
    client = PoliteClient(
        PolitenessSettings(min_seconds_between_requests=1.0),
        transport=httpx.MockTransport(lambda r: httpx.Response(404)),
        sleep=sleeps.append,
        clock=lambda: next(ticks),
    )
    client.get("https://a.test/1")
    client.get("https://a.test/2")
    assert sleeps and sleeps[0] == pytest.approx(0.8)


def test_backcheck_walks_sessions(calendar: TradingCalendar) -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(200, content=b"%PDF-1.7", headers={"content-type": "application/pdf"})

    found = list(
        backcheck(
            client_for(handler),
            calendar,
            KINGDOM,
            date(2026, 10, 16),
            date(2026, 10, 21),
            store=None,
        )
    )
    assert [o.session_date for o in found] == [
        date(2026, 10, 16),
        date(2026, 10, 19),
        date(2026, 10, 21),
    ]
    assert all(o.mode == "backcheck" for o in found)


def test_observations_round_trip_and_summary(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path)
    day = date(2026, 10, 7)
    rows = [
        Observation(
            "kingdom", day, "u", datetime(2026, 10, 7, 14, 30, tzinfo=UTC), "probe", 404, False
        ),
        Observation(
            "kingdom", day, "u", datetime(2026, 10, 7, 15, 30, tzinfo=UTC), "probe", 200, True
        ),
        Observation(
            "kingdom", day, "u", datetime(2026, 10, 7, 16, 30, tzinfo=UTC), "probe", 200, True
        ),
    ]
    assert save_observations(store, rows) == 3
    save_observations(store, rows)  # idempotent: same observation, same key
    assert load_observations(store) == rows
    (summary,) = summarise(load_observations(store))
    assert summary["median_first_seen_eat"] == "18:30"
    assert summary["sessions_available"] == 1


def test_latest_probe_session(calendar: TradingCalendar) -> None:
    before_close = datetime(2026, 10, 7, 9, 0, tzinfo=UTC)  # 12:00 EAT
    after_close = datetime(2026, 10, 7, 14, 0, tzinfo=UTC)  # 17:00 EAT
    holiday_evening = datetime(2026, 10, 20, 15, 0, tzinfo=UTC)
    assert latest_probe_session(calendar, before_close) == date(2026, 10, 6)
    assert latest_probe_session(calendar, after_close) == date(2026, 10, 7)
    assert latest_probe_session(calendar, holiday_evening) == date(2026, 10, 19)


def test_month_end_sessions_also_try_the_next_upload_folder() -> None:
    template = KINGDOM.url_template or ""
    assert [u.split("uploads/")[1] for u in candidate_urls(template, date(2026, 10, 30))] == [
        "2026/10/Daily-Market-Wrap-30-Oct-2026.pdf",
        "2026/11/Daily-Market-Wrap-30-Oct-2026.pdf",
    ]
    assert candidate_urls(template, date(2025, 12, 31))[1].endswith(
        "/2026/01/Daily-Market-Wrap-31-Dec-2025.pdf"
    )
    assert len(candidate_urls(template, date(2026, 10, 7))) == 1
    assert len(candidate_urls(NSE.url_template or "", date(2026, 10, 30))) == 1


def test_observe_finds_a_file_in_the_next_month_folder() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "/2026/11/" in request.url.path:
            return httpx.Response(200, content=b"%PDF-1.7", headers=PDF)
        return httpx.Response(404)

    obs = observe(client_for(handler), KINGDOM, date(2026, 10, 30), mode="probe", store=None)
    assert obs.available and "/2026/11/" in obs.url and obs.tried == 2


def test_not_found_everywhere_reports_the_first_url() -> None:
    obs = observe(
        client_for(lambda r: httpx.Response(404)),
        KINGDOM,
        date(2026, 10, 30),
        mode="backcheck",
        store=None,
    )
    assert obs.outcome == "not_found" and "/2026/10/" in obs.url and obs.tried == 2


@pytest.mark.parametrize("status", [401, 403, 451])
def test_a_block_is_not_a_missing_file(status: int) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(status)

    obs = observe(client_for(handler), KINGDOM, date(2026, 10, 30), mode="probe", store=None)
    assert obs.outcome == "blocked" and not obs.available
    assert len(calls) == 1  # a block does not move on to the next candidate URL


def test_rate_limit_waits_for_retry_after() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"retry-after": "5"})
        return httpx.Response(200, content=b"%PDF-1.7", headers=PDF)

    sleeps: list[float] = []
    obs = observe(client_for(handler, sleeps), KINGDOM, date(2026, 10, 7), mode="probe", store=None)
    assert obs.available and len(calls) == 2
    assert 5.0 in sleeps


def test_long_retry_after_is_respected_by_stopping() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(429, headers={"retry-after": "3600"})

    obs = observe(client_for(handler), KINGDOM, date(2026, 10, 7), mode="probe", store=None)
    assert obs.outcome == "blocked" and obs.status_code == 429 and len(calls) == 1


def test_retry_after_accepts_http_dates() -> None:
    response = httpx.Response(503, headers={"retry-after": "Wed, 07 Oct 2026 17:00:30 GMT"})
    now = datetime(2026, 10, 7, 17, 0, 0, tzinfo=UTC)
    assert retry_after_seconds(response, now) == pytest.approx(30.0)
    assert retry_after_seconds(httpx.Response(503, headers={"retry-after": "soon"})) is None
    assert retry_after_seconds(httpx.Response(503)) is None


def test_transport_errors_are_errors_not_missing_files() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    obs = observe(client_for(handler), KINGDOM, date(2026, 10, 7), mode="probe", store=None)
    assert (
        obs.outcome == "error" and obs.status_code is None and "ConnectError" in (obs.error or "")
    )


class BrokenStore(LocalObjectStore):
    def put_if_absent(self, key: str, data: bytes) -> bool:
        raise OSError("bucket unavailable")


def test_archive_failure_keeps_the_observation(tmp_path: Path) -> None:
    obs = observe(
        client_for(lambda r: httpx.Response(200, content=b"%PDF-1.7", headers=PDF)),
        KINGDOM,
        date(2026, 10, 7),
        mode="probe",
        store=BrokenStore(tmp_path),
    )
    assert obs.available and obs.archive_failed and obs.archived_key is None
    assert (obs.error or "").startswith("archive failed: OSError")


def test_summary_separates_outcomes() -> None:
    day = date(2026, 10, 7)
    at = datetime(2026, 10, 7, 15, 0, tzinfo=UTC)
    rows = [
        Observation("nse_pricelist", day, "u", at, "backcheck", 404, False),
        Observation("nse_pricelist", day, "u", at, "backcheck", 403, False),
        Observation("nse_pricelist", day, "u", at, "backcheck", None, False, error="timeout"),
        Observation("nse_pricelist", day, "u", at, "backcheck", 200, True),
    ]
    (summary,) = summarise(rows)
    assert summary["observations"] == {"available": 1, "blocked": 1, "error": 1, "not_found": 1}


def test_observations_without_tried_still_load() -> None:
    line = (
        '{"archived_key": null, "checked_at": "2026-10-07T15:00:00+00:00", "content_type": null,'
        ' "error": null, "mode": "probe", "provider_id": "kingdom", "session_date": "2026-10-07",'
        ' "sha256": null, "size": null, "status_code": 404, "url": "u", "available": false}'
    )
    assert Observation.from_json(line).tried == 1
