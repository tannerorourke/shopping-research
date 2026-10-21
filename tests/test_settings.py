"""Settings resolution: env over file over default, with an empty env value treated as unset."""
import settings as settings_mod


def test_env_overrides_file_and_empty_env_is_unset(toml_settings, monkeypatch):
    toml_settings('[serpapi]\napi_key = "file-key"\nmonthly_budget = 100\n[target]\nenabled = true\n')
    monkeypatch.setenv("SERPAPI_KEY", "")
    monkeypatch.setenv("SERPAPI_MONTHLY_BUDGET", "42")
    monkeypatch.setenv("TARGET_ENABLED", "false")
    s = settings_mod.reload()
    assert s.serpapi.api_key == "file-key"
    assert s.serpapi.monthly_budget == 42
    assert s.target.enabled is False


def test_defaults_without_file_or_env(toml_settings):
    s = toml_settings("")
    assert s.serpapi.monthly_budget == 250 and s.target.enabled is True and s.c1.enabled is False
