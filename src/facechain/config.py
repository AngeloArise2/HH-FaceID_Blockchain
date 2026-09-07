"""Central settings boundary; single source of truth for environment configuration.

Only the integration pipeline and CLI import :class:`Settings`. Provider modules never
read settings directly; values are injected through their public constructors.
Settings values are never logged.
"""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class SettingsValidationError(ValueError):
    """Raised when settings required for the selected mode are missing."""


class Settings(BaseSettings):
    """Application settings loaded from environment variables and ``.env``."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    serpapi_key: str = ""
    anvil_rpc_url: str = "http://127.0.0.1:8545"
    anvil_private_key: str = ""
    chain_id: int = 31337
    discovery_mode: Literal["fake", "real"] = "fake"

    def validate(self) -> None:  # type: ignore[override]  # legacy pydantic classmethod shadows
        """Raise a typed error when settings required for the selected mode are missing.

        The real ledger always requires an RPC URL and a funded private key. Real
        visual search additionally requires the SerpAPI key.
        """
        missing: list[str] = []
        if not self.anvil_rpc_url:
            missing.append("ANVIL_RPC_URL")
        if not self.anvil_private_key:
            missing.append("ANVIL_PRIVATE_KEY")
        if self.discovery_mode == "real" and not self.serpapi_key:
            missing.append("SERPAPI_KEY")
        if missing:
            raise SettingsValidationError(
                "Missing required settings for mode "
                f"DISCOVERY_MODE={self.discovery_mode}: {', '.join(sorted(missing))}"
            )