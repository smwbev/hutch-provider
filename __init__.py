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

# The relay endpoint comes from the environment, exactly like the API key.
# ``HUTCH_BASE_URL`` doubles as Hermes' standard base-URL override slot (the
# final ``env_vars`` entry), so both the profile default and the runtime
# resolver read the same variable. Set it in ``~/.hermes/.env``:
#   HUTCH_BASE_URL=https://relay.example.com/v1
#   HUTCH_API_KEY=sk-...
HUTCH_BASE_URL = (os.environ.get("HUTCH_BASE_URL") or "").strip().rstrip("/")
if not HUTCH_BASE_URL:
    logger.warning(
        "hutch: HUTCH_BASE_URL is not set — the provider is registered but has "
        "no endpoint. Add HUTCH_BASE_URL (and HUTCH_API_KEY) to ~/.hermes/.env."
    )


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

    ``fetch_models`` is deliberately NOT inherited from OpenRouterProfile:
    that override serves the PUBLIC openrouter.ai catalog with no auth and
    caches it in a module-level global shared by every instance of the class.
    Inheriting it would (a) send an unauthenticated request to the relay and
    (b) cross-contaminate the hutch and openrouter model lists through the
    shared cache. The base implementation hits ``{base_url}/models`` with
    Bearer auth and no process-wide cache — exactly right for a private relay.
    """

    def fetch_models(self, *, api_key=None, base_url=None, timeout=8.0):
        return ProviderProfile.fetch_models(
            self, api_key=api_key, base_url=base_url, timeout=timeout
        )


hutch = HutchProfile(
    name="hutch",
    aliases=(),
    display_name="Hutch",
    description="Hutch — private multi-provider relay (OpenAI-compatible)",
    env_vars=("HUTCH_API_KEY", "HUTCH_BASE_URL"),
    base_url=HUTCH_BASE_URL,
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
