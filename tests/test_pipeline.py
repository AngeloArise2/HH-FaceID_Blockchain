import pytest
from pydantic import ValidationError

from facechain.config import Settings, SettingsValidationError


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "anvil_rpc_url": "http://127.0.0.1:8545",
        "anvil_private_key": "0x" + "1" * 64,
        "chain_id": 31337,
        "discovery_mode": "fake",
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)  # type: ignore[arg-type]


def test_settings_defaults_to_fake_discovery_and_anvil_chain() -> None:
    settings = _settings()
    assert settings.discovery_mode == "fake"
    assert settings.chain_id == 31337
    assert settings.anvil_rpc_url == "http://127.0.0.1:8545"


def test_settings_validate_passes_for_fake_discovery() -> None:
    _settings().validate()


def test_settings_validate_passes_for_real_discovery_with_key() -> None:
    _settings(discovery_mode="real", serpapi_key="secret").validate()


def test_settings_validate_requires_serpapi_key_in_real_mode() -> None:
    with pytest.raises(SettingsValidationError, match="SERPAPI_KEY"):
        _settings(discovery_mode="real").validate()


def test_settings_validate_requires_anvil_private_key() -> None:
    with pytest.raises(SettingsValidationError, match="ANVIL_PRIVATE_KEY"):
        _settings(anvil_private_key="").validate()


def test_settings_validate_requires_anvil_rpc_url() -> None:
    with pytest.raises(SettingsValidationError, match="ANVIL_RPC_URL"):
        _settings(anvil_rpc_url="").validate()


def test_settings_loads_serpapi_key_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SERPAPI_KEY", "env-key")
    settings = _settings(discovery_mode="real")
    assert settings.serpapi_key == "env-key"


def test_settings_rejects_unknown_discovery_mode() -> None:
    with pytest.raises(ValidationError):
        _settings(discovery_mode="live")