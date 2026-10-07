"""Source verification spike (ENGINEERING.md 8.3).

Observes each candidate source every evening: when a session's file first appears, whether
it is a real document, and how far back each archive reaches. Files are archived only to
private storage (a local directory or, from Phase 1, the private R2 bucket). Third-party
files are never written into the repository or into public CI artifacts, because doing so
would redistribute them (review RK-02, NSE Market Data Policies 4.5 and 20.2).
"""

from __future__ import annotations

import calendar as gregorian
import email.utils
import json
import statistics
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Iterator
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta

import httpx

from nsefc.calendar import TradingCalendar
from nsefc.config import PolitenessSettings, ProviderDefinition
from nsefc.domain import EAT
from nsefc.ingestion.archive import RawArtifact, archive
from nsefc.storage.objectstore import ObjectStore

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


# A WordPress upload folder (/uploads/2026/10/) names the month the file was uploaded, not the
# session it covers: a month-end wrap uploaded after midnight lands in the next month's folder.
LATE_UPLOAD_WINDOW_DAYS = 7


def render_url(template: str, day: date, *, upload: date | None = None) -> str:
    """Fill a URL template for a session date, without any locale dependence.

    Session tokens: {YYYY} {YY} {MM} {DD} {Mon} (Oct) {MON} (OCT). Upload-folder tokens:
    {UPLOAD_YYYY} {UPLOAD_MM}, which default to the session's month.
    """
    upload = upload or day
    month = MONTHS[day.month - 1]
    return (
        template.replace("{UPLOAD_YYYY}", f"{upload.year:04d}")
        .replace("{UPLOAD_MM}", f"{upload.month:02d}")
        .replace("{YYYY}", f"{day.year:04d}")
        .replace("{YY}", f"{day.year % 100:02d}")
        .replace("{MM}", f"{day.month:02d}")
        .replace("{DD}", f"{day.day:02d}")
        .replace("{MON}", month.upper())
        .replace("{Mon}", month)
    )


def candidate_urls(template: str, day: date) -> list[str]:
    """Where a session's file may be: its own month's upload folder, then, for sessions in the
    last week of a month, the next month's folder."""
    urls = [render_url(template, day)]
    days_in_month = gregorian.monthrange(day.year, day.month)[1]
    if "{UPLOAD_" in template and day.day > days_in_month - LATE_UPLOAD_WINDOW_DAYS:
        next_month = day.replace(day=1) + timedelta(days=days_in_month)
        urls.append(render_url(template, day, upload=next_month))
    return urls


@dataclass(frozen=True, slots=True)
class Observation:
    provider_id: str
    session_date: date
    url: str
    checked_at: datetime
    mode: str
    status_code: int | None
    available: bool
    size: int | None = None
    sha256: str | None = None
    content_type: str | None = None
    archived_key: str | None = None
    error: str | None = None
    tried: int = 1  # candidate URLs requested before this result

    @property
    def outcome(self) -> str:
        """available, not_found (404, 410 or a soft 404), blocked (401, 403, 429, 451) or error.

        Only not_found says anything about a source's archive; blocked and error mean the
        question was not answered (review: a firewall must not look like a shallow archive).
        """
        if self.available:
            return "available"
        if self.status_code in (404, 410) or (self.status_code == 200 and self.error):
            return "not_found"
        if self.status_code in (401, 403, 429, 451):
            return "blocked"
        return "error"

    @property
    def archive_failed(self) -> bool:
        return self.available and (self.error or "").startswith("archive failed")

    def to_json(self) -> str:
        data = asdict(self)
        data["session_date"] = self.session_date.isoformat()
        data["checked_at"] = self.checked_at.isoformat()
        return json.dumps(data, sort_keys=True)

    @classmethod
    def from_json(cls, line: str) -> Observation:
        data = json.loads(line)
        data["session_date"] = date.fromisoformat(data["session_date"])
        data["checked_at"] = datetime.fromisoformat(data["checked_at"])
        return cls(**data)


def _looks_like(content: bytes, expected_format: str) -> bool:
    """Reject soft 404s: a 200 response carrying an HTML error page instead of the file."""
    if expected_format == "pdf":
        return content.startswith(b"%PDF")
    if expected_format == "csv":
        return b"," in content[:2048] and not content.lstrip().startswith(b"<")
    return bool(content)


BACKOFF_SECONDS = (2.0, 8.0, 30.0)
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_RETRY_AFTER_SECONDS = 120.0  # a source asking for a longer pause is left alone this run


def retry_after_seconds(response: httpx.Response, now: datetime | None = None) -> float | None:
    """The Retry-After header as seconds (it may be a number or an HTTP date)."""
    value = response.headers.get("retry-after")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        when = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - (now or datetime.now(UTC))).total_seconds())


class PoliteClient:
    """One request per host per interval, identifying user agent, bounded retries (8.5, 9.5).

    Retries transport errors, 429 and 5xx with backoff, honouring Retry-After up to
    MAX_RETRY_AFTER_SECONDS; a longer requested pause returns the response unretried.
    """

    def __init__(
        self,
        politeness: PolitenessSettings,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.politeness = politeness
        self._sleep, self._clock = sleep, clock
        self._last: dict[str, float] = {}
        self._client = httpx.Client(
            headers={"User-Agent": politeness.user_agent},
            timeout=politeness.timeout_seconds,
            follow_redirects=True,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def _wait(self, host: str) -> None:
        last = self._last.get(host)
        if last is not None:
            gap = self.politeness.min_seconds_between_requests - (self._clock() - last)
            if gap > 0:
                self._sleep(gap)
        self._last[host] = self._clock()

    def get(self, url: str) -> httpx.Response:
        host = httpx.URL(url).host
        for attempt in range(self.politeness.retries + 1):
            delay = BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)]
            self._wait(host)
            try:
                response = self._client.get(url)
            except httpx.TransportError:
                if attempt == self.politeness.retries:
                    raise
            else:
                if response.status_code not in RETRY_STATUSES or attempt == self.politeness.retries:
                    return response
                requested = retry_after_seconds(response)
                if requested is not None:
                    if requested > MAX_RETRY_AFTER_SECONDS:
                        return response
                    delay = max(delay, requested)
            self._sleep(delay)
        raise AssertionError("unreachable")


def observe(
    client: PoliteClient,
    provider: ProviderDefinition,
    session_date: date,
    *,
    mode: str,
    store: ObjectStore | None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> Observation:
    """Request each candidate URL in turn until one serves the document.

    A 404 moves on to the next candidate; any other failure stops, because asking again
    elsewhere would not answer a block or an outage. Archive failures are recorded on the
    observation rather than raised, so the observation itself is never lost.
    """
    if not provider.url_template:
        raise ValueError(f"{provider.provider_id} has no URL template to probe")
    candidates = candidate_urls(provider.url_template, session_date)
    first: Observation | None = None
    for tried, url in enumerate(candidates, start=1):
        result = _request(client, provider, session_date, url, mode, store, now(), tried)
        if result.available or result.outcome != "not_found":
            return result
        first = first or result
    assert first is not None  # candidate_urls always returns at least one URL
    return Observation(**{**asdict(first), "tried": len(candidates)})


def _request(
    client: PoliteClient,
    provider: ProviderDefinition,
    session_date: date,
    url: str,
    mode: str,
    store: ObjectStore | None,
    checked_at: datetime,
    tried: int,
) -> Observation:
    try:
        response = client.get(url)
    except httpx.HTTPError as exc:
        return Observation(
            provider.provider_id,
            session_date,
            url,
            checked_at,
            mode,
            None,
            False,
            error=f"{type(exc).__name__}: {exc}",
            tried=tried,
        )
    content = response.content
    ok = response.status_code == 200 and _looks_like(content, provider.format)
    archived_key = None
    error = None if ok else ("soft 404: not a document" if response.status_code == 200 else None)
    artifact = RawArtifact(
        provider_id=provider.provider_id,
        session_date=session_date,
        url=str(response.url),
        fetched_at=checked_at,
        content=content,
        content_type=response.headers.get("content-type", ""),
        status_code=response.status_code,
        etag=response.headers.get("etag"),
        last_modified=response.headers.get("last-modified"),
    )
    if ok and store is not None:
        try:
            archived_key, _ = archive(store, artifact)
        except Exception as exc:  # the observation must survive a storage failure
            error = f"archive failed: {type(exc).__name__}: {exc}"
    return Observation(
        provider.provider_id,
        session_date,
        url,
        checked_at,
        mode,
        response.status_code,
        ok,
        size=len(content),
        sha256=artifact.sha256 if ok else None,
        content_type=artifact.content_type or None,
        archived_key=archived_key,
        error=error,
        tried=tried,
    )


OBSERVATIONS_PREFIX = "spike/observations/"


def observation_key(observation: Observation) -> str:
    stamp = observation.checked_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return (
        f"{OBSERVATIONS_PREFIX}{observation.provider_id}/{observation.session_date.isoformat()}/"
        f"{stamp}-{observation.mode}.json"
    )


def save_observations(store: ObjectStore, observations: Iterable[Observation]) -> int:
    """One immutable object per observation: concurrent runs never contend for a file."""
    count = 0
    for observation in observations:
        store.put_if_absent(observation_key(observation), observation.to_json().encode("utf-8"))
        count += 1
    return count


def load_observations(store: ObjectStore, prefix: str = OBSERVATIONS_PREFIX) -> list[Observation]:
    return [
        Observation.from_json(store.get(key).decode("utf-8"))
        for key in store.list(prefix)
        if key.endswith(".json")
    ]


def probe_session(
    client: PoliteClient,
    providers: Iterable[ProviderDefinition],
    session_date: date,
    store: ObjectStore | None,
) -> Iterator[Observation]:
    """One observation per provider, yielded as made so the caller can save each at once."""
    for provider in providers:
        yield observe(client, provider, session_date, mode="probe", store=store)


def backcheck(
    client: PoliteClient,
    calendar: TradingCalendar,
    provider: ProviderDefinition,
    start: date,
    end: date,
    store: ObjectStore | None,
) -> Iterator[Observation]:
    """Probe every scheduled session in [start, end]: how deep does the archive go?"""
    for day in calendar.sessions_in(start, end):
        yield observe(client, provider, day, mode="backcheck", store=store)


def _eat_minutes(moment: datetime) -> int:
    local = moment.astimezone(EAT)
    return local.hour * 60 + local.minute


def summarise(observations: list[Observation]) -> list[dict[str, object]]:
    """Per provider: sessions seen, availability, first-seen times in EAT, archive reach."""
    by_provider: dict[str, list[Observation]] = defaultdict(list)
    for observation in observations:
        by_provider[observation.provider_id].append(observation)
    rows: list[dict[str, object]] = []
    for provider_id, items in sorted(by_provider.items()):
        sessions = sorted({o.session_date for o in items})
        available = sorted({o.session_date for o in items if o.available})
        first_seen: list[int] = []
        for day in available:
            probes = [o for o in items if o.session_date == day and o.mode == "probe"]
            hits = [o.checked_at for o in probes if o.available]
            # Only same-day sightings say anything about publication time.
            same_day = [t for t in hits if t.astimezone(EAT).date() == day]
            if same_day:
                first_seen.append(_eat_minutes(min(same_day)))
        median = statistics.median(first_seen) if first_seen else None
        rows.append(
            {
                "provider_id": provider_id,
                "sessions_checked": len(sessions),
                "sessions_available": len(available),
                "earliest_available": available[0].isoformat() if available else None,
                "latest_available": available[-1].isoformat() if available else None,
                "median_first_seen_eat": (
                    f"{int(median) // 60:02d}:{int(median) % 60:02d}"
                    if median is not None
                    else None
                ),
                "same_day_sightings": len(first_seen),
                "observations": dict(sorted(Counter(o.outcome for o in items).items())),
                "archive_failures": sum(o.archive_failed for o in items),
            }
        )
    return rows


def latest_probe_session(calendar: TradingCalendar, now: datetime) -> date:
    """The latest scheduled session whose close (15:00 EAT) has passed."""
    local = now.astimezone(EAT)
    day = local.date()
    if local.hour < 15:
        day -= timedelta(days=1)
    return calendar.latest_session_on_or_before(day)
