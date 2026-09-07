"""CLI entry point; implemented during integration."""

from __future__ import annotations

import sys
from pathlib import Path

# The shared ``contracts/`` package lives at the repository root and is not part
# of the installed wheel, so the console script must resolve it from the source
# checkout before importing the contract models below.
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import hashlib
from typing import Annotated

import typer
from pydantic import ValidationError

from contracts.domain import AuthorizedImage, EvidenceBundle
from facechain.config import Settings, SettingsValidationError
from facechain.discovery import (
    DiscoveryConfigError,
    DiscoveryService,
    DiscoveryUnavailableError,
    NoMatchFoundError,
    SerpAPILensProvider,
)
from facechain.identity import (
    IdentityService,
    InputValidationError,
    InsightFaceFaceScanner,
    MultipleFacesDetectedError,
    NoFaceDetectedError,
    RecognitionUnavailableError,
)
from facechain.ledger import (
    AnvilWeb3Adapter,
    EvidenceLedger,
    LedgerUnavailableError,
    Web3LedgerProvider,
)
from facechain.pipeline import FaceVerificationPipeline

app = typer.Typer(no_args_is_help=True)

_ERROR_MAP: dict[type[BaseException], tuple[str, int]] = {
    InputValidationError: ("image validation failed", 2),
    NoFaceDetectedError: ("no face detected in the image", 3),
    MultipleFacesDetectedError: ("multiple faces detected; exactly one required", 4),
    RecognitionUnavailableError: ("face recognition unavailable", 5),
    NoMatchFoundError: ("no public match found", 6),
    DiscoveryUnavailableError: ("discovery provider unavailable", 7),
    DiscoveryConfigError: ("discovery provider misconfigured", 8),
    LedgerUnavailableError: ("ledger provider unavailable", 9),
    SettingsValidationError: ("configuration error", 10),
}


def _handle_error(exc: BaseException) -> None:
    """Print a concise one-line error and exit with a non-zero code."""
    for exc_type, (message, code) in _ERROR_MAP.items():
        if isinstance(exc, exc_type):
            detail = f": {exc}" if str(exc) else ""
            typer.echo(f"Error: {message}{detail}", err=True)
            raise typer.Exit(code)
    typer.echo(f"Error: {exc}", err=True)
    raise typer.Exit(1)


def _build_pipeline() -> FaceVerificationPipeline:
    """Build the verification pipeline with real providers from Settings."""
    settings = Settings()
    settings.validate()

    identity = IdentityService(InsightFaceFaceScanner())
    discovery = DiscoveryService(SerpAPILensProvider(api_key=settings.serpapi_key))
    adapter = AnvilWeb3Adapter(
        rpc_url=settings.anvil_rpc_url,
        private_key=settings.anvil_private_key,
        chain_id=settings.chain_id,
    )
    provider = Web3LedgerProvider(settings=settings, adapter=adapter)
    ledger = EvidenceLedger(provider=provider)

    return FaceVerificationPipeline(
        identity=identity,
        discovery=discovery,
        ledger=ledger,
    )


@app.command()
def run(
    image: Annotated[Path, typer.Option("--image", help="Path to a consented face image")],
    runs_dir: Annotated[Path, typer.Option("--runs-dir", help="Directory for run outputs")] = Path("runs"),
    no_save: Annotated[bool, typer.Option("--no-save", help="Print evidence to the terminal without writing evidence.json")] = False,
) -> None:
    """Run a face verification pipeline on a consented image.

    Validates the image, scans for a face, searches for a matching public post,
    anchors the evidence fingerprint on-chain, and re-verifies it.  Prints the
    evidence bundle and every detected platform match to the terminal; writes
    runs/<run-id>/evidence.json unless --no-save is given.
    """
    try:
        sha256 = hashlib.sha256(image.read_bytes()).hexdigest()
    except (FileNotFoundError, PermissionError, OSError) as exc:
        typer.echo(f"Error: cannot read image: {exc}", err=True)
        raise typer.Exit(1)

    consent_ref = f"cli-run-{sha256[:16]}"

    try:
        pipeline = _build_pipeline()
        authorized = AuthorizedImage(
            image_path=str(image.resolve()),
            sha256=sha256,
            consent_reference=consent_ref,
        )
        result = pipeline.run(authorized)
    except (
        InputValidationError,
        NoFaceDetectedError,
        MultipleFacesDetectedError,
        RecognitionUnavailableError,
        NoMatchFoundError,
        DiscoveryUnavailableError,
        DiscoveryConfigError,
        LedgerUnavailableError,
        SettingsValidationError,
        OSError,
    ) as exc:
        _handle_error(exc)

    for event in result.events:
        detail = f" - {event.detail}" if event.detail else ""
        typer.echo(f"[{event.stage}]{detail}")

    if result.matches:
        typer.echo(
            f"\n{len(result.matches)} platform match(es) found; checking each:"
        )
        for index, match in enumerate(result.matches, start=1):
            confidence = match.confidence
            score = f"{confidence * 100:.0f}%" if confidence is not None else "no provider score"
            typer.echo(
                f"  [{index}/{len(result.matches)}] "
                f"platform={match.post.platform} confidence={score} "
                f"source={match.post.source_url}"
            )
        typer.echo("")

    if result.evidence is None:
        raise typer.Exit(6)

    printout = result.evidence.model_dump_json(indent=2)
    if no_save:
        typer.echo("Evidence (not saved):")
        typer.echo(printout)
        if any(event.stage == "failed" for event in result.events):
            typer.echo("Error: run failed; no evidence was anchored on-chain", err=True)
            raise typer.Exit(9)
        return

    run_dir = runs_dir / result.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = run_dir / "evidence.json"
    evidence_path.write_text(printout)
    typer.echo("Evidence bundle:")
    typer.echo(printout)
    typer.echo(f"Evidence saved to {evidence_path}")

    if any(event.stage == "failed" for event in result.events):
        typer.echo("Error: run failed; evidence was written but not anchored", err=True)
        raise typer.Exit(9)


@app.command()
def verify(
    evidence_path: Annotated[Path, typer.Option("--evidence", help="Path to evidence.json from a prior run")],
) -> None:
    """Verify an existing evidence bundle against the on-chain ledger.

    Loads the evidence file produced by ``facechain run``, reconstructs the
    canonical fingerprint, and checks whether an identical fingerprint exists
    on-chain.
    """
    try:
        raw = evidence_path.read_text()
        evidence = EvidenceBundle.model_validate_json(raw)
    except (FileNotFoundError, PermissionError, OSError) as exc:
        typer.echo(f"Error: cannot read evidence file: {exc}", err=True)
        raise typer.Exit(1)
    except ValidationError as exc:
        typer.echo(f"Error: invalid evidence file: {exc}", err=True)
        raise typer.Exit(1)

    try:
        pipeline = _build_pipeline()
        result = pipeline.verify_bundle(evidence)
    except (
        LedgerUnavailableError,
        SettingsValidationError,
        FileNotFoundError,
        OSError,
    ) as exc:
        _handle_error(exc)

    if result.matched:
        typer.echo(f"Verified: matched (sha256={result.evidence_sha256})")
    else:
        typer.echo(f"Not matched: sha256={result.evidence_sha256}")
        raise typer.Exit(1)