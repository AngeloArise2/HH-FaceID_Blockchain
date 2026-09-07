"""Central settings boundary; minimal ANVIL settings needed by the ledger module."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and ``.env``.

    Only the entries required by the ledger provider are declared here. The full
    surface (``SERPAPI_KEY``, ``DISCOVERY_MODE``, ``validate()``) is implemented
    by the integration owner. Settings values are never logged.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anvil_rpc_url: str = "http://127.0.0.1:8545"
    anvil_private_key: str = ""
    chain_id: int = 31337