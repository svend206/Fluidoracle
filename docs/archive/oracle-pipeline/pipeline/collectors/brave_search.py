"""
Brave Search API collector. Used across all phases to find relevant pages.
"""

import os
import requests
from typing import Optional
from .base import BaseCollector
from ..utils.rate_limiter import brave_limiter
from ..utils.logging import RunLogger


BRAVE_API_URL = "https://api.search.brave.com/res/v1/web/search"


class BraveSearchCollector(BaseCollector):
    def __init__(self, vertical: str, phase: int, logger: RunLogger):
        super().__init__(vertical, phase, logger, archive=False)
        self.api_key = os.environ.get("BRAVE_API_KEY", "")
        if not self.api_key:
            raise ValueError("BRAVE_API_KEY not set in environment")

    def search(self, query: str, count: int = 10,
               freshness: Optional[str] = None) -> list[dict]:
        """
        Run a Brave search and return a list of result dicts.
        Each dict: {title, url, description, age}
        Rate-limited to 20 calls/min.
        """
        brave_limiter.wait()

        params = {
            "q": query,
            "count": min(count, 20),
            "search_lang": "en",
            "country": "US",
        }
        if freshness:
            params["freshness"] = freshness

        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self.api_key,
        }

        try:
            resp = requests.get(BRAVE_API_URL, params=params, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            results = []
            for item in data.get("web", {}).get("results", []):
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "description": item.get("description", ""),
                    "age": item.get("age", ""),
                })

            self.logger.info("brave_search", query=query, results=len(results))
            return results

        except Exception as e:
            self.logger.error("brave_search_failed", query=query, error=str(e))
            return []

    def collect(self, queries: list[str], count_per_query: int = 10) -> list[dict]:
        """Run multiple queries and deduplicate results by URL."""
        seen_urls = set()
        all_results = []

        for query in queries:
            results = self.search(query, count=count_per_query)
            for r in results:
                if r["url"] not in seen_urls:
                    seen_urls.add(r["url"])
                    all_results.append(r)

                    # Save each result as a source stub
                    self.save_source(
                        url=r["url"],
                        source_type="search-result",
                        extracted_text=r["description"],
                        metadata={"title": r["title"], "query": query, "age": r["age"]},
                        collection_method="brave-search",
                    )

        return all_results
