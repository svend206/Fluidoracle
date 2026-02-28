"""
Base collector — handles HTTP, retries, rate limiting, archiving, and provenance.
All specific collectors inherit from this.
"""

import time
import hashlib
import json
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from bs4 import BeautifulSoup

from ..db import get_connection, save_artifact
from ..utils.hashing import url_hash, source_id
from ..utils.logging import RunLogger
from ..utils.rate_limiter import web_limiter


DEFAULT_HEADERS = {
    "User-Agent": "OraclePipeline/0.1 (industrial knowledge research; contact via project account)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Domains we've already hit — track last request time per domain for polite crawling
_domain_last_hit: dict = {}
DOMAIN_MIN_INTERVAL = 5.0  # seconds between requests to same domain


def _domain_of(url: str) -> str:
    from urllib.parse import urlparse
    return urlparse(url).netloc


def _domain_wait(url: str) -> None:
    domain = _domain_of(url)
    last = _domain_last_hit.get(domain, 0)
    elapsed = time.monotonic() - last
    if elapsed < DOMAIN_MIN_INTERVAL:
        time.sleep(DOMAIN_MIN_INTERVAL - elapsed)
    _domain_last_hit[domain] = time.monotonic()


class BaseCollector(ABC):
    def __init__(self, vertical: str, phase: int, logger: RunLogger,
                 archive: bool = True):
        self.vertical = vertical
        self.phase = phase
        self.logger = logger
        self.archive = archive
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

        # Snapshot archive directory
        self.snapshot_dir = (
            Path(__file__).parent.parent.parent
            / "verticals" / vertical / "snapshots"
        )
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)

    def already_collected(self, url: str) -> bool:
        """Return True if this URL has already been collected."""
        with get_connection() as conn:
            row = conn.execute(
                "SELECT id FROM knowledge_artifacts WHERE source_url = ? AND collection_phase = ?",
                (url, self.phase)
            ).fetchone()
        return row is not None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
        reraise=True,
    )
    def _fetch_raw(self, url: str, timeout: int = 20) -> requests.Response:
        _domain_wait(url)
        start = time.monotonic()
        resp = self.session.get(url, timeout=timeout, allow_redirects=True)
        duration = int((time.monotonic() - start) * 1000)
        self.logger.fetch(url, "direct-fetch", resp.status_code, duration_ms=duration)
        resp.raise_for_status()
        return resp

    def fetch_html(self, url: str) -> Optional[BeautifulSoup]:
        """Fetch a URL and return a BeautifulSoup object. Returns None on failure."""
        try:
            resp = self._fetch_raw(url)
            content = resp.text
            if self.archive:
                self._archive(url, content, ".html")
            return BeautifulSoup(content, "lxml")
        except Exception as e:
            self.logger.error("fetch_failed", url=url, error=str(e))
            return None

    def _archive(self, url: str, content: str, ext: str = ".html") -> Path:
        filename = url_hash(url)[:16] + ext
        path = self.snapshot_dir / filename
        path.write_text(content, encoding="utf-8")
        return path

    def save_source(self, url: str, source_type: str, extracted_text: str = "",
                    metadata: Optional[dict] = None, confidence: float = 0.5,
                    title: str = "", http_status: Optional[int] = None,
                    snapshot_path: Optional[str] = None,
                    collection_method: str = "direct-fetch") -> str:
        """Save a collected artifact to knowledge_artifacts. Returns artifact ID."""
        from datetime import datetime, timezone
        aid = source_id(url, self.vertical, self.phase)
        access_date = datetime.now(timezone.utc).isoformat()

        # Authority score heuristic by source type
        authority_map = {
            "standards-catalog": 0.95,
            "vendor-catalog":    0.75,
            "forum-thread":      0.60,
            "search-result":     0.50,
            "academic-paper":    0.85,
            "course-syllabus":   0.70,
        }
        authority = authority_map.get(source_type, confidence)

        return save_artifact(
            artifact_id=aid,
            title=title or url,
            artifact_type=source_type,
            source_url=url,
            access_date=access_date,
            collection_phase=self.phase,
            collection_method=collection_method,
            authority_score=authority,
            raw_snapshot_path=snapshot_path,
        )

    @abstractmethod
    def collect(self, **kwargs) -> list[dict]:
        """Run this collector and return a list of result dicts."""
        ...
