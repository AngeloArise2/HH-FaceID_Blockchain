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
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from contracts.discovery import DiscoveryMatch
from contracts.domain import AuthorizedImage, EvidenceBundle
from contracts.events import PipelineEvent
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

console = Console(theme=Theme({"error": "bold red", "ok": "bold green"}))

_STAGE_STYLES = {
    "validated": "cyan",
    "face_scanned": "blue",
    "post_found": "yellow",
    "anchored": "magenta",
    "verified": "ok",
    "failed": "error",
}

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
            console.print(f"Error: {message}{detail}", style="error")
            raise typer.Exit(code)
    console.print(f"Error: {exc}", style="error")
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


def _confidence_style(confidence: float | None) -> str:
    if confidence is None:
        return "dim"
    if confidence >= 0.7:
        return "ok"
    if confidence >= 0.5:
        return "yellow"
    return "error"


def _print_events(events: list[PipelineEvent]) -> None:
    """Print each pipeline event with its stage in a themed color."""
    for event in events:
        stage_style = _STAGE_STYLES.get(event.stage, "white")
        label = Text(f"[{event.stage}]", style=stage_style)
        detail = f" - {event.detail}" if event.detail else ""
        console.print(label, detail)


def _print_match_table(matches: list[DiscoveryMatch]) -> None:
    """Print a matchwise comparison table for every discovered match."""
    if not matches:
        console.print(Text("No matching public post was found.", style="error"))
        return
    table = Table(
        title=f"Matchwise comparison ({len(matches)} platform match(es))",
        box=box.ROUNDED,
        header_style="bold blue",
        title_style="bold blue",
    )
    table.add_column("#", justify="right", style="dim")
    table.add_column("Platform", no_wrap=True)
    table.add_column("Confidence", justify="right", no_wrap=True)
    table.add_column("Source", overflow="fold")
    for index, match in enumerate(matches, start=1):
        confidence = match.confidence
        if confidence is None:
            score = Text("no provider score", style="dim")
        else:
            score = Text(f"{confidence * 100:.0f}%", style=_confidence_style(confidence))
        table.add_row(
            str(index),
            match.post.platform,
            score,
            str(match.post.source_url),
        )
    console.print(table)


def _print_evidence(evidence: EvidenceBundle) -> None:
    """Print the full evidence bundle as readable JSON."""
    console.print(Panel(evidence.model_dump_json(indent=2), title="Evidence bundle"))
    console.print(
        Text(
            f"sha256: {hashlib.sha256(evidence.model_dump_json().encode()).hexdigest()}",
            style="dim",
        )
    )


@app.command()
def run(
    image: Annotated[Path, typer.Option("--image", help="Path to a consented face image")],
    runs_dir: Annotated[Path, typer.Option("--runs-dir", help="Directory for run outputs")] = Path("runs"),
    save: Annotated[bool, typer.Option("--save", help="Also write runs/<run-id>/evidence.json")] = False,
) -> None:
    """Run a face verification pipeline on a consented image.

    Validates the image, scans for a face, searches for a matching public post,
    anchors the evidence fingerprint on-chain, and re-verifies it.  Prints the
    full result to the terminal: every pipeline event plus a matchwise
    comparison table and the complete evidence bundle.  Nothing is written to
    disk unless --save is given.
    """
    try:
        sha256 = hashlib.sha256(image.read_bytes()).hexdigest()
    except (FileNotFoundError, PermissionError, OSError) as exc:
        console.print(f"Error: cannot read image: {exc}", style="error")
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

    console.print()
    console.print(
        Panel.fit(
            f"input sha256 {result.evidence.input_image_sha256 if result.evidence else sha256}\n"
            f"consent {consent_ref}",
            title=f"Run {result.run_id}",
            title_align="left",
            border_style="bright_blue",
        )
    )
    console.print()

    _print_events(result.events)
    console.print()
    _print_match_table(result.matches)
    console.print()

    if result.evidence is None:
        raise typer.Exit(6)

    _print_evidence(result.evidence)

    failed = any(event.stage == "failed" for event in result.events)
    if save:
        run_dir = runs_dir / result.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        evidence_path = run_dir / "evidence.json"
        evidence_path.write_text(result.evidence.model_dump_json(indent=2))
        console.print(f"Evidence saved to {evidence_path}" if not failed else "Evidence not anchored")
    else:
        console.print("Evidence not saved to disk (use --save to write runs/<run-id>/evidence.json).")

    if failed:
        console.print("Run failed; evidence was not anchored on-chain.", style="error")
        raise typer.Exit(9)


@app.command()
def verify(
    evidence_path: Annotated[Path, typer.Option("--evidence", help="Path to evidence.json from a prior run")],
) -> None:
    """Verify an existing evidence bundle against the on-chain ledger.

    Loads the evidence file produced by ``facechain run --save``, reconstructs
    the canonical fingerprint, and checks whether an identical fingerprint
    exists on-chain.
    """
    try:
        raw = evidence_path.read_text()
        evidence = EvidenceBundle.model_validate_json(raw)
    except (FileNotFoundError, PermissionError, OSError) as exc:
        console.print(f"Error: cannot read evidence file: {exc}", style="error")
        raise typer.Exit(1)
    except ValidationError as exc:
        console.print(f"Error: invalid evidence file: {exc}", style="error")
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
        console.print(
            Text(
                f"Verified: matched (sha256={result.evidence_sha256})",
                style="ok",
            )
        )
    else:
        console.print(
            Text(f"Not matched: sha256={result.evidence_sha256}", style="error")
        )
        raise typer.Exit(1)