"""Hutch image generation backend — the relay's image models via the OpenRouter-compatible surface.

Reuses the bundled ``OpenRouterCompatImageProvider`` class (chat-completions
image output + the dedicated ``/images/*`` API) with ``runtime_name="hutch"``,
so credentials and endpoint resolve through the ``hutch`` model-provider
plugin (install it first — see the repository README). The catalog is
discovered live from the relay, so new image models appear without a plugin
update.
"""

import logging

logger = logging.getLogger(__name__)


def _openrouter_compat_class():
    """The bundled OpenRouterCompatImageProvider class, via its loaded module.

    The bundled image_gen/openrouter plugin is imported by the PluginManager
    under the ``hermes_plugins`` namespace before user plugins load (bundled
    backends are ``load_now``; user plugins come later in discovery order).
    """
    import sys
    for name, module in list(sys.modules.items()):
        if "image_gen" in name and hasattr(module, "OpenRouterCompatImageProvider"):
            return module.OpenRouterCompatImageProvider
    return None


def register(ctx) -> None:
    """Register the hutch image backend, reusing the bundled compat provider."""
    compat_cls = _openrouter_compat_class()
    if compat_cls is None:
        logger.warning(
            "hutch image_gen: bundled openrouter image plugin not loaded — "
            "cannot reuse OpenRouterCompatImageProvider; hutch image backend disabled."
        )
        return
    ctx.register_image_gen_provider(compat_cls(
        provider_name="hutch",
        display_name="Hutch",
        runtime_name="hutch",
        config_key="hutch",
        model_env_var="HUTCH_IMAGE_MODEL",
        supports_image_api=True,
        setup_schema={
            "name": "Hutch (image)",
            "badge": "relay",
            "tag": "gpt-image-2/2.5, Grok Imagine, Muse Image via the Hutch relay; uses HUTCH_API_KEY",
            "env_vars": [{
                "key": "HUTCH_API_KEY", "prompt": "Hutch relay API key", "url": "",
            }],
        },
    ))
