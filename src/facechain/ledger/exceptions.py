"""Ledger module exceptions."""


class LedgerError(Exception):
    """Base exception for all ledger module errors."""


class LedgerUnavailableError(LedgerError):
    """Raised when the ledger provider is unreachable or an operation fails."""