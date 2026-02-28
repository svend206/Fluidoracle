"""
Vertical Loader — loads platform and vertical configurations from the filesystem.

This is the central configuration layer that makes the platform multi-vertical.
All other modules (consultation_engine, answer_engine, retrieval) receive their
vertical-specific configuration from here.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Repository root (parent of core/)
REPO_ROOT = Path(__file__).parent.parent


@dataclass
class VerticalConfig:
    """Complete configuration for a single vertical."""

    vertical_id: str
    platform_id: str
    display_name: str
    short_name: str
    description: str

    # Retrieval
    child_collection: str
    parent_collection: str
    bm25_index_path: str  # Absolute path to BM25 pickle

    # Prompts (loaded from .md files)
    gathering_prompt: str
    answering_prompt: str
    identity_prompt: str

    # Domain taxonomy
    application_domains: list = field(default_factory=list)

    # Reference data (full text for prompt injection)
    core_reference_data: str = ""

    # Tuning
    confidence_threshold_high: float = 0.75
    confidence_threshold_medium: float = 0.40
    retrieval_top_k: int = 10
    semantic_weight: float = 0.60

    # UI
    example_questions: list = field(default_factory=list)
    warmup_query: str = ""


@dataclass
class PlatformConfig:
    """Configuration for a platform (FPS or FDS)."""

    platform_id: str
    display_name: str
    description: str
    system_context: str  # Loaded from system_context.md
    verticals: dict[str, VerticalConfig] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Module-level cache
# ---------------------------------------------------------------------------
_platform_cache: dict[str, PlatformConfig] = {}
_vertical_cache: dict[str, VerticalConfig] = {}


def _read_file(path: Path) -> str:
    """Read a text file, returning empty string if it doesn't exist."""
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return ""


def _load_vertical(platform_id: str, vertical_id: str, vertical_dir: Path) -> VerticalConfig:
    """Load a single vertical's configuration from its directory."""
    # Import the vertical's config module
    config_module_path = f"platforms.{platform_id}.verticals.{vertical_id}.config"
    try:
        config_mod = importlib.import_module(config_module_path)
    except ModuleNotFoundError:
        raise ValueError(
            f"Vertical config module not found: {config_module_path}. "
            f"Expected at {vertical_dir / 'config.py'}"
        )

    # Load prompts from .md files
    gathering_prompt = _read_file(vertical_dir / "gathering_prompt.md")
    answering_prompt = _read_file(vertical_dir / "answering_prompt.md")
    identity_prompt = _read_file(vertical_dir / "identity.md")

    # Load domains if available
    application_domains = []
    try:
        domains_mod = importlib.import_module(
            f"platforms.{platform_id}.verticals.{vertical_id}.domains"
        )
        application_domains = getattr(domains_mod, "APPLICATION_DOMAINS", [])
    except ModuleNotFoundError:
        pass

    # Load reference data text (the full answering prompt already contains it,
    # but we also expose it separately for programmatic use)
    core_reference_data = ""
    try:
        ref_mod = importlib.import_module(
            f"platforms.{platform_id}.verticals.{vertical_id}.reference_data"
        )
        # The reference data is available as structured Python objects in ref_mod
        # For prompt injection, the answering_prompt.md already contains the full text
        core_reference_data = "(structured reference data available via reference_data module)"
    except ModuleNotFoundError:
        pass

    # Build BM25 index absolute path
    bm25_path = str(
        REPO_ROOT / "vector-store" / "bm25" / getattr(config_mod, "BM25_INDEX_FILENAME", f"{vertical_id}.pkl")
    )

    return VerticalConfig(
        vertical_id=vertical_id,
        platform_id=platform_id,
        display_name=getattr(config_mod, "DISPLAY_NAME", vertical_id),
        short_name=getattr(config_mod, "SHORT_NAME", vertical_id),
        description=getattr(config_mod, "DESCRIPTION", ""),
        child_collection=getattr(config_mod, "CHILD_COLLECTION", f"{vertical_id}-children"),
        parent_collection=getattr(config_mod, "PARENT_COLLECTION", f"{vertical_id}-parents"),
        bm25_index_path=bm25_path,
        gathering_prompt=gathering_prompt,
        answering_prompt=answering_prompt,
        identity_prompt=identity_prompt,
        application_domains=application_domains,
        core_reference_data=core_reference_data,
        confidence_threshold_high=getattr(config_mod, "CONFIDENCE_THRESHOLD_HIGH", 0.75),
        confidence_threshold_medium=getattr(config_mod, "CONFIDENCE_THRESHOLD_MEDIUM", 0.40),
        retrieval_top_k=getattr(config_mod, "RETRIEVAL_TOP_K", 10),
        semantic_weight=getattr(config_mod, "SEMANTIC_WEIGHT", 0.60),
        example_questions=getattr(config_mod, "EXAMPLE_QUESTIONS", []),
        warmup_query=getattr(config_mod, "WARMUP_QUERY", ""),
    )


def load_platform(platform_id: str) -> PlatformConfig:
    """Load a platform and all its registered verticals.

    Results are cached after first load.
    """
    if platform_id in _platform_cache:
        return _platform_cache[platform_id]

    platform_dir = REPO_ROOT / "platforms" / platform_id
    if not platform_dir.exists():
        raise ValueError(f"Platform directory not found: {platform_dir}")

    # Import platform config module
    platform_config_path = f"platforms.{platform_id}.platform_config"
    try:
        platform_mod = importlib.import_module(platform_config_path)
    except ModuleNotFoundError:
        raise ValueError(f"Platform config module not found: {platform_config_path}")

    # Load system context
    system_context = _read_file(platform_dir / "system_context.md")

    # Load registered verticals
    verticals_registry = getattr(platform_mod, "VERTICALS", {})
    verticals: dict[str, VerticalConfig] = {}

    for vertical_id in verticals_registry:
        vertical_dir = platform_dir / "verticals" / vertical_id
        if not vertical_dir.exists():
            raise ValueError(
                f"Vertical directory not found: {vertical_dir} "
                f"(registered in {platform_id}/platform_config.py)"
            )
        vc = _load_vertical(platform_id, vertical_id, vertical_dir)
        verticals[vertical_id] = vc
        # Also cache individually
        _vertical_cache[f"{platform_id}:{vertical_id}"] = vc

    platform = PlatformConfig(
        platform_id=platform_id,
        display_name=getattr(platform_mod, "DISPLAY_NAME", platform_id),
        description=getattr(platform_mod, "DESCRIPTION", ""),
        system_context=system_context,
        verticals=verticals,
    )

    _platform_cache[platform_id] = platform
    return platform


def get_vertical_config(platform_id: str, vertical_id: str) -> VerticalConfig:
    """Get a specific vertical's configuration.

    Loads the full platform if not already cached.
    """
    cache_key = f"{platform_id}:{vertical_id}"
    if cache_key in _vertical_cache:
        return _vertical_cache[cache_key]

    platform = load_platform(platform_id)
    if vertical_id not in platform.verticals:
        available = list(platform.verticals.keys())
        raise ValueError(
            f"Vertical '{vertical_id}' not registered in platform '{platform_id}'. "
            f"Available: {available}"
        )
    return platform.verticals[vertical_id]


def list_platforms() -> list[str]:
    """List available platform IDs by scanning the platforms/ directory."""
    platforms_dir = REPO_ROOT / "platforms"
    return [
        d.name
        for d in platforms_dir.iterdir()
        if d.is_dir() and (d / "platform_config.py").exists()
    ]


def list_verticals(platform_id: str) -> list[str]:
    """List available vertical IDs for a platform."""
    platform = load_platform(platform_id)
    return list(platform.verticals.keys())


def clear_cache() -> None:
    """Clear all cached configs. Useful for testing or hot-reload."""
    _platform_cache.clear()
    _vertical_cache.clear()
