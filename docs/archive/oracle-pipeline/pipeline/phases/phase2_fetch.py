"""
Phase 2 — Full Content Fetch
Fetches the actual page content for all URLs collected in Phase 1.
Uses trafilatura for clean text extraction. Zero LLM tokens.

Saves content to:
  verticals/{vertical}/raw-fetch/{artifact_id}.md

Updates knowledge_artifacts.raw_snapshot_path on success.
Logs failures without halting — paywalled/binary URLs are expected.
"""

import time
import requests
import trafilatura
from pathlib import Path
from typing import Optional
from ..db import init_db, get_connection
from ..utils.logging import RunLogger


FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

MAX_CONTENT_CHARS = 40_000   # ~10K tokens — enough for a full article
REQUEST_TIMEOUT   = 20       # seconds
DELAY_BETWEEN     = 1.5      # seconds between requests — be polite


class Phase2Runner:
    def __init__(self, vertical: str, force: bool = False):
        self.vertical = vertical
        self.force    = force
        self.logger   = RunLogger(vertical, phase=2)

        # Output directory: verticals/{vertical}/raw-fetch/
        self.out_dir = (
            Path(__file__).parent.parent.parent
            / "verticals" / vertical / "raw-fetch"
        )
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def run(self) -> dict:
        init_db()
        conn = get_connection()

        # Load unfetched artifacts (or all if force=True)
        query = """
            SELECT id, source_url, collection_method
            FROM knowledge_artifacts
            WHERE raw_snapshot_path IS NULL
        """ if not self.force else """
            SELECT id, source_url, collection_method
            FROM knowledge_artifacts
        """
        artifacts = conn.execute(query).fetchall()

        self.logger.info("phase2_start", total=len(artifacts), vertical=self.vertical)

        fetched, skipped, failed = 0, 0, []

        for i, art in enumerate(artifacts):
            artifact_id = art["id"]
            url         = art["source_url"]

            # Skip obvious non-HTML content we can't extract
            if self._should_skip(url):
                self.logger.info("phase2_skip", url=url[:80], reason="binary/paywall")
                skipped += 1
                continue

            self.logger.info(
                "phase2_fetch",
                n=f"{i+1}/{len(artifacts)}",
                url=url[:80]
            )

            content = self._fetch(url)

            if content:
                out_path = self.out_dir / f"{artifact_id}.md"
                out_path.write_text(
                    f"# Fetched Content\nSource: {url}\n\n{content}",
                    encoding="utf-8"
                )
                # Update DB
                conn.execute(
                    "UPDATE knowledge_artifacts SET raw_snapshot_path = ? WHERE id = ?",
                    (str(out_path), artifact_id)
                )
                conn.commit()
                fetched += 1
                self.logger.info("phase2_saved", artifact_id=artifact_id, chars=len(content))
            else:
                failed.append(url)
                self.logger.info("phase2_failed", url=url[:80])

            time.sleep(DELAY_BETWEEN)

        summary = {
            "fetched": fetched,
            "skipped": skipped,
            "failed":  len(failed),
            "failed_urls": failed,
        }
        self.logger.info("phase2_complete", **{k: v for k, v in summary.items() if k != "failed_urls"})
        return summary

    def _should_skip(self, url: str) -> bool:
        """Skip URLs that won't yield extractable text."""
        skip_patterns = [
            # Obvious paywalled/login-required sources
            "sae.org/standards", "ansi.org", "saemobilus.sae.org",
            # SAE profile pages
            "profiles.sae.org",
            # NFPA standards store
            "nfpa.org/codes-and-standards",
            # Webstore preview pages (partial only)
            "webstore.ansi.org",
        ]
        url_lower = url.lower()
        return any(p in url_lower for p in skip_patterns)

    def _fetch(self, url: str) -> Optional[str]:
        """
        Fetch URL and extract clean text using trafilatura.
        Returns None on failure.
        """
        try:
            resp = requests.get(
                url,
                headers=FETCH_HEADERS,
                timeout=REQUEST_TIMEOUT,
                allow_redirects=True
            )

            if resp.status_code != 200:
                self.logger.info("phase2_http_error", url=url[:80], status=resp.status_code)
                return None

            content_type = resp.headers.get("Content-Type", "")

            # Handle PDFs — trafilatura can handle some but many are binary images
            if "pdf" in content_type or url.lower().endswith(".pdf"):
                return self._extract_pdf(resp.content, url)

            # HTML extraction via trafilatura
            text = trafilatura.extract(
                resp.text,
                include_tables=True,
                include_links=False,
                no_fallback=False,
                favor_precision=False,
            )

            if not text or len(text.strip()) < 200:
                return None

            return text[:MAX_CONTENT_CHARS]

        except Exception as e:
            self.logger.info("phase2_exception", url=url[:80], error=str(e)[:100])
            return None

    def _extract_pdf(self, content: bytes, url: str) -> Optional[str]:
        """
        Attempt text extraction from PDF bytes using pdfplumber.
        Falls back gracefully for image-scanned PDFs.
        """
        try:
            import pdfplumber
            import io
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                pages_text = []
                for page in pdf.pages[:20]:  # cap at 20 pages
                    text = page.extract_text()
                    if text:
                        pages_text.append(text.strip())
                combined = "\n\n".join(pages_text)
                if len(combined.strip()) > 200:
                    self.logger.info("phase2_pdf_extracted", url=url[:80], chars=len(combined))
                    return combined[:MAX_CONTENT_CHARS]
        except Exception as e:
            pass

        self.logger.info("phase2_pdf_unextractable", url=url[:80])
        return None
