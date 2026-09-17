"""Hutch video generation backend — the relay's video models via the OpenRouter-compatible API.

Subclasses the bundled OpenRouter video provider (async job submit + poll on
``/videos/*``, live catalog with per-model limits) and swaps only the
credentials: ``HUTCH_API_KEY`` / ``HUTCH_BASE_URL``. New relay video models
(grok-imagine-video*, …) appear in the picker without a plugin update.
"""

import logging
import os

logger = logging.getLogger(__name__)


def _openrouter_video_class():
    """The bundled OpenRouterVideoGenProvider class, via its loaded module."""
    import sys
    for name, module in list(sys.modules.items()):
        if "video_gen" in name and hasattr(module, "OpenRouterVideoGenProvider"):
            return module.OpenRouterVideoGenProvider
    return None


def register(ctx) -> None:
    """Register the hutch video backend, reusing the bundled OpenRouter provider."""
    base_cls = _openrouter_video_class()
    if base_cls is None:
        logger.warning(
            "hutch video_gen: bundled openrouter video plugin not loaded — "
            "hutch video backend disabled."
        )
        return

    class HutchVideoGenProvider(base_cls):
        """OpenRouter video wire behavior pointed at the Hutch relay."""

        name = "hutch"
        display_name = "Hutch"

        def _api_key(self) -> str:
            return os.environ.get("HUTCH_API_KEY", "").strip()

        def _base_url(self) -> str:
            return os.environ.get("HUTCH_BASE_URL", "").strip().rstrip("/")

        def is_available(self) -> bool:
            return bool(self._api_key() and self._base_url())

        def _catalog(self):
            """Live video catalog synthesized from the relay's ``/models`` list.

            Overridden entirely: the inherited implementation targets
            OpenRouter's ``/videos/models`` (which CLIProxyAPI does not serve —
            a GET there is captured by the ``/videos/:request_id`` polling
            route and 400s) and falls back to a snapshot of OPENROUTER's video
            models when unreachable — meaningless slugs for the relay. The
            relay's single source of truth is ``/models`` (Bearer auth);
            entries are filtered to video-named slugs with permissive defaults
            — the relay validates the actual generation request. Same TTL
            cache slot as the parent.
            """
            import time
            import requests
            if self._catalog_cache and time.monotonic() - self._catalog_cache[1] < 600:
                return self._catalog_cache[0]
            entries = []
            try:
                response = requests.get(
                    f"{self._base_url()}/models",
                    headers={"Authorization": f"Bearer {self._api_key()}"}, timeout=15)
                response.raise_for_status()
                entries = [
                    {"id": str(row.get("id")), "name": str(row.get("id"))}
                    for row in (response.json().get("data") or [])
                    if "video" in str(row.get("id", "")).lower()
                ]
            except Exception as exc:
                logger.debug("hutch video: /models catalog fetch failed: %s", exc)
                return []
            if entries:
                self._catalog_cache = (entries, time.monotonic())
            return entries

    ctx.register_video_gen_provider(HutchVideoGenProvider())
