"""
Phase 1 — Standards and Regulatory Landscape
Collects all standards from ISO TC/SC catalogs and forum evidence.
LLM is used only for final synthesis.
"""

import yaml
import json
from pathlib import Path
from ..db import init_db, log_run_start, log_run_complete, get_or_create_standard, get_connection
from ..utils.logging import RunLogger
from ..collectors.brave_search import BraveSearchCollector
from ..collectors.base import BaseCollector


class Phase1Runner:
    def __init__(self, vertical: str, force: bool = False):
        self.vertical = vertical
        self.force = force
        self.config = self._load_config()
        self.logger = RunLogger(vertical, phase=1)
        self.errors = []
        self.sources_collected = 0

    def _load_config(self) -> dict:
        config_path = (
            Path(__file__).parent.parent.parent
            / "verticals" / self.vertical / "config.yaml"
        )
        with open(config_path) as f:
            return yaml.safe_load(f)

    def run(self) -> None:
        init_db()

        phase_config = self.config.get("phase1", {})
        run_id = log_run_start(self.vertical, 1, phase_config)

        self.logger.info("phase1_start", vertical=self.vertical)

        # Step 1: Forum evidence via Brave Search
        self._collect_forum_evidence(phase_config)

        # Step 2: Secondary standards bodies via Brave Search
        self._collect_secondary_bodies(phase_config)

        # Step 3: Vendor standard citations via Brave Search
        self._collect_vendor_citations(phase_config)

        # Step 4: ISO catalog (direct fetch — implemented in Sprint 2)
        self.logger.info("iso_catalog_skipped", note="Direct ISO catalog fetch — Sprint 2")

        # Step 5: Synthesis (LLM — Sprint 2)
        self.logger.info("synthesis_skipped", note="LLM synthesis — Sprint 2")

        log_run_complete(run_id, self.sources_collected, self.errors)
        self.logger.info("phase1_complete",
                         sources=self.sources_collected,
                         errors=len(self.errors))

    def _collect_forum_evidence(self, config: dict) -> None:
        brave = BraveSearchCollector(self.vertical, phase=1, logger=self.logger)
        forum_queries = config.get("forum_search_queries", {})

        all_queries = []
        for forum, queries in forum_queries.items():
            all_queries.extend(queries)

        self.logger.info("forum_search_start", query_count=len(all_queries))
        results = brave.collect(
            queries=all_queries,
            count_per_query=config.get("results_per_query", 10)
        )
        self.sources_collected += len(results)
        self.logger.info("forum_search_done", results=len(results))

    def _collect_secondary_bodies(self, config: dict) -> None:
        brave = BraveSearchCollector(self.vertical, phase=1, logger=self.logger)
        bodies = config.get("secondary_bodies", [])
        queries = [b["search_query"] for b in bodies if "search_query" in b]

        if not queries:
            return

        self.logger.info("secondary_bodies_start", query_count=len(queries))
        results = brave.collect(queries=queries, count_per_query=10)
        self.sources_collected += len(results)

    def _collect_vendor_citations(self, config: dict) -> None:
        brave = BraveSearchCollector(self.vertical, phase=1, logger=self.logger)
        queries = config.get("vendor_standard_queries", [])

        if not queries:
            return

        self.logger.info("vendor_citations_start", query_count=len(queries))
        results = brave.collect(queries=queries, count_per_query=10)
        self.sources_collected += len(results)
