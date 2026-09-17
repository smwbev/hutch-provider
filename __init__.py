"""Hutch provider profile — a private OpenAI-compatible relay behind the OpenRouter wire policy.

Registers a first-class ``hutch`` provider whose requests go to the Hutch
gateway instead of openrouter.ai. Inherits the bundled OpenRouter profile
class at runtime (provider preferences, reasoning passthrough, speed-tier
pins, sticky routing) so upstream improvements arrive for free, while the
distinct name sidesteps the custom:<name> / built-in collision class entirely
(hermes-agent#109015).

Install (either works):
  $HERMES_HOME/plugins/model-providers/hutch/   <- drop this directory
  hermes plugins install smwbev/hutch-provider  <- or via the plugin manager
"""

import logging
import os

from providers import register_provider
from providers.base import ProviderProfile

logger = logging.getLogger(__name__)

# The relay endpoint comes from the environment, exactly like the API key
# (the URL is private, so no static default ships in this public repo).
# ``HUTCH_BASE_URL`` is read at ACCESS time via the ``base_url`` property
# below — never at import time: provider discovery can import this module
# before Hermes loads ``~/.hermes/.env`` (hermes_cli/main.py loads dotenv
# after early config imports, and config's provider discovery imports user
# plugins), so an import-time ``os.environ`` read would permanently freeze
# an empty endpoint into the profile and blank the model catalog
# (hermes_cli/models.py::_profile_live_catalog requires a truthy
# ``profile.base_url``). Set it in ``~/.hermes/.env``:
#   HUTCH_BASE_URL=https://relay.example.com/v1
#   HUTCH_API_KEY=sk-...


def _env_base_url() -> str:
    return (os.environ.get("HUTCH_BASE_URL") or "").strip().rstrip("/")


def _openrouter_profile_class() -> type:
    """The bundled OpenRouterProfile class, resolved from the live registry.

    Bundled plugins live under a dashed path (``plugins/model-providers/``) and
    are not importable by dotted name; discovery imports bundled plugins BEFORE
    user plugins, so by the time this module loads the ``openrouter`` profile
    instance is registered and its class carries every OpenRouter hook
    (build_extra_body, build_api_kwargs_extras, endpoint pins). The public
    ``get_provider_profile`` lookup is reentrancy-safe here: ``_discovered``
    is set at the top of ``_discover_providers``, so a recursive call from an
    importing plugin does a plain registry read. Fall back to the plain
    ProviderProfile if the bundled plugin ever goes away — the provider still
    works, just without the aggregator niceties (and says so loudly).
    """
    try:
        from providers import get_provider_profile
        profile = get_provider_profile("openrouter")
        if profile is not None:
            return type(profile)
    except Exception as exc:  # pragma: no cover - defensive: registry shape changed
        logger.debug("hutch: could not resolve bundled OpenRouterProfile (%s)", exc)
    logger.warning(
        "hutch: bundled openrouter profile not registered yet — falling back to "
        "plain ProviderProfile (sticky routing / reasoning passthrough disabled). "
        "This happens when the plugin is imported before provider discovery "
        "(e.g. as a pip entry point); install it as a directory plugin instead."
    )
    return ProviderProfile


_Base = _openrouter_profile_class()


class HutchProfile(_Base):
    """OpenRouter wire behavior pointed at the Hutch relay.

    Do NOT re-decorate this class with ``@dataclass``: ``base_url`` is a
    property, and re-decoration would capture the property object as the
    field default and silently break the generated ``__init__``.

    ``base_url`` is a PROPERTY resolved from ``HUTCH_BASE_URL`` at access
    time. Provider discovery imports this module before ``~/.hermes/.env``
    is loaded (main.py loads dotenv after early config imports, and the
    desktop backend's tui_gateway does the same), so a value captured at
    import time would freeze empty and blank the model catalog —
    ``_profile_live_catalog`` requires a truthy ``profile.base_url``. The
    runtime credential resolver reads the same env var through
    ``base_url_env_var``, so both paths agree by construction.

    ``fetch_models`` is deliberately NOT inherited from OpenRouterProfile:
    that override serves the PUBLIC openrouter.ai catalog with no auth and
    caches it in a module-level global shared by every instance of the class.
    Inheriting it would (a) send an unauthenticated request to the relay and
    (b) cross-contaminate the hutch and openrouter model lists through the
    shared cache. The base implementation hits ``{base_url}/models`` with
    Bearer auth and no process-wide cache — exactly right for a private relay.
    """

    @property
    def base_url(self) -> str:  # type: ignore[override]
        return _env_base_url() or self._configured_base_url

    @base_url.setter
    def base_url(self, value) -> None:
        # The dataclass __init__ assigns ``self.base_url = base_url`` — route
        # the constructor value into a backing slot; env wins when set.
        self._configured_base_url = (value or "").strip().rstrip("/")

    def fetch_models(self, *, api_key=None, base_url=None, timeout=8.0):
        if not (base_url or self.base_url):
            logger.warning(
                "hutch: HUTCH_BASE_URL is not set — add it (and HUTCH_API_KEY) "
                "to ~/.hermes/.env; the model catalog is empty without it."
            )
        return ProviderProfile.fetch_models(
            self, api_key=api_key, base_url=base_url, timeout=timeout
        )


hutch = HutchProfile(
    name="hutch",
    aliases=(),
    display_name="Hutch",
    description="Hutch — private multi-provider relay (OpenAI-compatible)",
    env_vars=("HUTCH_API_KEY", "HUTCH_BASE_URL"),
    base_url="",  # resolved live from HUTCH_BASE_URL by the property above
    auth_type="api_key",
    api_mode="chat_completions",
    default_aux_model="openai/gpt-5.6-terra",
    fallback_models=(
        "anthropic/claude-fable-5",
        "anthropic/claude-opus-5",
        "openai/gpt-5.6-sol",
        "openai/gpt-5.6-terra",
        "x-ai/grok-4.6",
        "deepseek/deepseek-v4-flash",
    ),
)

register_provider(hutch)
