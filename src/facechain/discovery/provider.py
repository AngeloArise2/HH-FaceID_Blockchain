"""Discovery provider protocol and implementations."""

import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlparse

import httpx
from pydantic import HttpUrl, ValidationError

from contracts.discovery import DiscoveryResult
from contracts.domain import AuthorizedImage, FaceScan, PublicPost
from facechain.discovery.exceptions import (
    DiscoveryConfigError,
    DiscoveryUnavailableError,
    NoMatchFoundError,
)


@runtime_checkable
class DiscoveryProvider(Protocol):
    """Protocol defining the visual search discovery provider interface."""

    def search(self, image: AuthorizedImage, scan: FaceScan) -> DiscoveryResult:
        """Search for a matching public post for the given authorized image.

        Args:
            image: Validated authorized image with consent.
            scan: Validated face scan metadata.

        Returns:
            DiscoveryResult containing the matched public post and provider info.

        Raises:
            NoMatchFoundError: When no matching public post is found.
            DiscoveryUnavailableError: When the provider service is unreachable or fails.
            DiscoveryConfigError: When the provider credentials or settings are invalid.
        """
        ...


class FakeDiscoveryProvider:
    """Deterministic fake provider for testing and offline runs."""

    def __init__(
        self,
        canned_result: DiscoveryResult | None = None,
        raise_error: Exception | None = None,
    ) -> None:
        self.canned_result = canned_result
        self.raise_error = raise_error
        self.recorded_calls: list[tuple[AuthorizedImage, FaceScan]] = []

    def search(self, image: AuthorizedImage, scan: FaceScan) -> DiscoveryResult:
        """Execute fake search returning canned response or raising specified error."""
        self.recorded_calls.append((image, scan))
        if self.raise_error is not None:
            raise self.raise_error
        if self.canned_result is not None:
            return self.canned_result
        raise NoMatchFoundError("No qualifying public match found by fake provider.")


class SerpAPILensProvider:
    """Real discovery adapter using SerpAPI Google Lens visual search."""

    DEFAULT_BASE_URL = "https://serpapi.com"
    DEFAULT_TIMEOUT = 15.0
    DEFAULT_MAX_RETRIES = 3

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_backoff: float = 0.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.getenv("SERPAPI_KEY", "")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max(1, max_retries)
        self.retry_backoff = retry_backoff
        self._client = http_client

    def _get_client(self) -> httpx.Client:
        if self._client is not None:
            return self._client
        return httpx.Client(timeout=self.timeout)

    def _request_with_retry(
        self,
        client: httpx.Client,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = client.request(method, url, **kwargs)
                if resp.status_code in (401, 403):
                    raise DiscoveryConfigError(
                        f"SerpAPI authentication failed ({resp.status_code}): {resp.text}"
                    )
                if resp.status_code >= 500:
                    if attempt < self.max_retries:
                        if self.retry_backoff > 0:
                            time.sleep(self.retry_backoff * attempt)
                        continue
                    resp.raise_for_status()
                resp.raise_for_status()
                return resp
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    if self.retry_backoff > 0:
                        time.sleep(self.retry_backoff * attempt)
                    continue
                raise DiscoveryUnavailableError(
                    f"SerpAPI connection failed after {self.max_retries} attempts: {exc}"
                ) from exc
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in (401, 403):
                    raise DiscoveryConfigError(
                        f"SerpAPI authentication failed ({exc.response.status_code}): {exc}"
                    ) from exc
                raise DiscoveryUnavailableError(
                    f"SerpAPI error ({exc.response.status_code}): {exc}"
                ) from exc
        raise DiscoveryUnavailableError(f"SerpAPI request failed: {last_exc}")

    def _upload_local_image(self, client: httpx.Client, file_path: str) -> str:
        path = Path(file_path)
        if not path.exists():
            raise DiscoveryUnavailableError(f"Image file not found: {file_path}")
        try:
            image_bytes = path.read_bytes()
        except OSError as exc:
            raise DiscoveryUnavailableError(f"Failed to read image file {file_path}: {exc}") from exc

        upload_url = f"{self.base_url}/image"
        files = {"image": (path.name, image_bytes, "image/jpeg")}
        data = {"api_key": self.api_key}

        resp = self._request_with_retry(client, "POST", upload_url, files=files, data=data)
        try:
            payload = resp.json()
        except (ValueError, TypeError) as exc:
            raise DiscoveryUnavailableError(f"Invalid JSON response from SerpAPI upload: {exc}") from exc

        image_id = payload.get("image_id")
        if not image_id or not isinstance(image_id, str):
            raise DiscoveryUnavailableError("No image_id returned from SerpAPI image upload.")
        return str(image_id)

    def search(self, image: AuthorizedImage, scan: FaceScan) -> DiscoveryResult:
        """Search for qualifying public post using SerpAPI Google Lens."""
        if not self.api_key:
            raise DiscoveryConfigError("SERPAPI_KEY is required but not configured.")

        client = self._get_client()
        params: dict[str, Any] = {
            "engine": "google_lens",
            "api_key": self.api_key,
        }

        if image.image_path.startswith(("http://", "https://")):
            params["url"] = image.image_path
        else:
            image_id = self._upload_local_image(client, image.image_path)
            params["image_id"] = image_id

        search_url = f"{self.base_url}/search.json"
        resp = self._request_with_retry(client, "GET", search_url, params=params)

        try:
            data = resp.json()
        except (ValueError, TypeError) as exc:
            raise DiscoveryUnavailableError(f"Failed to decode SerpAPI JSON response: {exc}") from exc

        if "error" in data:
            err_msg = str(data["error"])
            if "Invalid API key" in err_msg or "api_key" in err_msg.lower():
                raise DiscoveryConfigError(f"SerpAPI authentication failed: {err_msg}")
            raise DiscoveryUnavailableError(f"SerpAPI returned error: {err_msg}")

        matches = data.get("visual_matches") or data.get("exact_matches") or []
        if not isinstance(matches, list) or not matches:
            raise NoMatchFoundError("No qualifying public match found by visual search.")

        qualifying_match: dict[str, Any] | None = None
        for candidate in matches:
            if not isinstance(candidate, dict):
                continue
            link = candidate.get("link")
            if link and isinstance(link, str) and link.startswith(("http://", "https://")):
                qualifying_match = candidate
                break

        if qualifying_match is None:
            raise NoMatchFoundError("No visual match with a valid public source URL was found.")

        source_url = HttpUrl(qualifying_match["link"])
        platform = qualifying_match.get("source")
        if not platform or not isinstance(platform, str):
            netloc = urlparse(qualifying_match["link"]).netloc
            platform = netloc or "Web"

        title = qualifying_match.get("title")
        if title and not isinstance(title, str):
            title = str(title)

        text_excerpt = qualifying_match.get("snippet") or qualifying_match.get("text")
        if text_excerpt and isinstance(text_excerpt, str):
            if len(text_excerpt) > 500:
                text_excerpt = text_excerpt[:497] + "..."
        else:
            text_excerpt = None

        image_url = None
        raw_image_url = qualifying_match.get("thumbnail") or qualifying_match.get("original")
        if raw_image_url and isinstance(raw_image_url, str) and raw_image_url.startswith(("http://", "https://")):
            try:
                image_url = HttpUrl(raw_image_url)
            except (ValueError, TypeError, ValidationError):
                image_url = None

        matched_post = PublicPost(
            source_url=source_url,
            platform=platform,
            title=title,
            text_excerpt=text_excerpt,
            image_url=image_url,
            retrieved_at=datetime.now(UTC),
        )

        return DiscoveryResult(
            provider="serpapi_google_lens",
            matched_post=matched_post,
            confidence=None,
        )
