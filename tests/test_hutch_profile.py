"""Invariant tests for the hutch provider plugin.

Run from a hermes-agent checkout (PYTHONPATH=<checkout>) so the real
``providers`` discovery path is exercised:

    PYTHONPATH=/path/to/hermes-agent python -m pytest tests/ -q -o 'addopts='

Each test runs discovery in a FRESH SUBPROCESS with a temp HERMES_HOME and
this plugin installed as a user model-provider plugin — proving the real
installation layout end to end (provider discovery is process-lazy and module
state cannot be reliably re-imported in-process).
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parent.parent


def _run_probe(code: str, *, extra_env: dict | None = None, drop_env: tuple = ()) -> dict:
    """Run ``code`` in a fresh interpreter with the plugin installed into a temp HERMES_HOME."""
    with tempfile.TemporaryDirectory() as home:
        target = Path(home) / "plugins" / "model-providers" / "hutch"
        target.parent.mkdir(parents=True)
        shutil.copytree(
            PLUGIN_ROOT, target,
            ignore=shutil.ignore_patterns("tests", ".git", "__pycache__", "*.pyc"),
        )
        env = dict(
            os.environ,
            HERMES_HOME=home,
            HUTCH_BASE_URL="https://relay.test.example/v1",
        )
        env.update(extra_env or {})
        for key in drop_env:
            env.pop(key, None)
        proc = subprocess.run(
            [sys.executable, "-c", textwrap.dedent(code)],
            capture_output=True, text=True, env=env, timeout=120,
        )
        assert proc.returncode == 0, f"probe failed:\n{proc.stderr}"
        return json.loads(proc.stdout.strip().splitlines()[-1])


def test_hutch_registers_with_relay_endpoint():
    out = _run_probe("""
        import json
        import providers
        p = providers.get_provider_profile("hutch")
        print(json.dumps({
            "found": p is not None,
            "name": p.name if p else None,
            "auth_type": p.auth_type if p else None,
            "base_url": p.base_url if p else None,
            "env0": p.env_vars[0] if p and p.env_vars else None,
        }))
    """)
    assert out["found"]
    assert out["name"] == "hutch"
    assert out["auth_type"] == "api_key"
    assert "openrouter.ai" not in out["base_url"]
    assert out["env0"] == "HUTCH_API_KEY"


def test_hutch_inherits_openrouter_wire_hooks():
    out = _run_probe("""
        import json
        import providers
        h = providers.get_provider_profile("hutch")
        o = providers.get_provider_profile("openrouter")
        extra_body, _top = h.build_api_kwargs_extras(
            reasoning_config={"effort": "high"}, supports_reasoning=True,
            model="deepseek/deepseek-v4-flash", session_id=None,
        )
        print(json.dumps({
            "openrouter_found": o is not None,
            "is_subclass": isinstance(h, type(o)) if o else False,
            "mro": [c.__name__ for c in type(h).__mro__],
            "reasoning_effort": (extra_body.get("reasoning") or {}).get("effort"),
        }))
    """)
    assert out["openrouter_found"], "bundled openrouter plugin missing from discovery"
    assert out["is_subclass"], f"expected OpenRouterProfile lineage, got {out['mro']}"
    assert out["reasoning_effort"] == "high"


def test_bare_openrouter_keeps_official_endpoint():
    out = _run_probe("""
        import json
        import providers
        o = providers.get_provider_profile("openrouter")
        print(json.dumps({
            "base_url": o.base_url if o else None,
            "env0": o.env_vars[0] if o and o.env_vars else None,
        }))
    """)
    assert "openrouter.ai" in out["base_url"]
    assert out["env0"] == "OPENROUTER_API_KEY"


def test_fetch_models_uses_bearer_auth_against_relay():
    out = _run_probe("""
        import json
        import providers
        from providers.base import ProviderProfile
        h = providers.get_provider_profile("hutch")
        calls = {}
        original = ProviderProfile.fetch_models
        def fake(self, *, api_key=None, base_url=None, timeout=8.0):
            calls["api_key"] = api_key
            calls["base_url"] = base_url
            return ["relay-model"]
        ProviderProfile.fetch_models = fake
        try:
            result = h.fetch_models(api_key="sk-test", base_url=h.base_url)
        finally:
            ProviderProfile.fetch_models = original
        print(json.dumps({"result": result, "calls": calls}))
    """)
    assert out["result"] == ["relay-model"]
    # Bearer auth reaches the base implementation (OpenRouter's public-catalog
    # override drops the key and would cache the public list process-wide).
    assert out["calls"]["api_key"] == "sk-test"
    assert "openrouter.ai" not in (out["calls"]["base_url"] or "")


def test_base_url_comes_from_env_only():
    """The endpoint is env-driven; the test env sets the placeholder relay."""
    out = _run_probe("""
        import json
        import providers
        p = providers.get_provider_profile("hutch")
        print(json.dumps({"base_url": p.base_url if p else None}))
    """)
    assert out["base_url"] == "https://relay.test.example/v1"


def test_base_url_survives_import_before_dotenv_load():
    """Regression: HUTCH_BASE_URL must be read at ACCESS time, not import time.

    Hermes imports provider plugins during discovery, which can run BEFORE
    ``~/.hermes/.env`` is loaded (hermes_cli/main.py loads dotenv after early
    config imports; the desktop tui_gateway backend does the same). An
    import-time ``os.environ`` read froze base_url='' permanently: the model
    catalog guard (``_profile_live_catalog`` requires a truthy
    ``profile.base_url``) then returned an empty picker even though chat
    worked (the runtime resolver reads the env var itself at call time).

    Simulated here exactly: discovery runs with NO env var, the var appears
    afterwards (as load_hermes_dotenv would do), and the profile must see it.
    """
    out = _run_probe(
        """
        import json, os
        import providers
        p = providers.get_provider_profile("hutch")  # discovery, no env var yet
        before = p.base_url
        os.environ["HUTCH_BASE_URL"] = "https://late.relay.example/v1"  # .env loads late
        after = p.base_url
        catalog_guard_passes = bool(p and p.auth_type == "api_key" and p.base_url)
        print(json.dumps({
            "before": before, "after": after,
            "catalog_guard_passes": catalog_guard_passes,
        }))
        """,
        drop_env=("HUTCH_BASE_URL",),
    )
    assert out["before"] == ""  # nothing frozen at import
    assert out["after"] == "https://late.relay.example/v1"
    assert out["catalog_guard_passes"]
