"""
bot/src/services/scraper.py
All leaked.cx-specific HTTP interaction lives here.
Handles: session authentication, thread HTML parsing,
         download link extraction, and file-host filename resolution.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from aiohttp import ClientSession
from bs4 import BeautifulSoup

from shared.config import get_settings

log = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────
LEAKED_CX_BASE = "https://leaked.cx"
LOGIN_URL = f"{LEAKED_CX_BASE}/login/"
LOGIN_POST_URL = f"{LEAKED_CX_BASE}/login/login"
BOT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Tag labels that indicate content type (lower-cased for comparison)
CONTENT_TAGS: frozenset[str] = frozenset({
    "leak", "snippet", "early", "old leak", "demo", "stem",
    "instrumental", "session", "og file", "higher bitrate",
    "music video",
})

# Domains that are excluded from "download links" (navigation/reaction links)
EXCLUDED_LINK_DOMAINS: frozenset[str] = frozenset({
    "leaked.cx", "discord.gg", "discord.com",
})

# File-hosting domains where we can resolve a proper filename
FILENAME_RESOLVERS: dict[str, tuple[str, dict]] = {
    # domain: (tag, attrs)
    "krakenfiles.com": ("span", {"class": "coin-name"}),
    "imgur.gg": ("h2", {"class": "text-lg font-medium overflow-hidden text-ellipsis whitespace-nowrap"}),
    "pixeldrain.com": ("h1", {"class": "svelte-xeankq"}),
}


# ── Data structures ────────────────────────────────────────────────────────

@dataclass
class ParsedThread:
    """Structured representation of a scraped leaked.cx thread."""
    url: str
    title: str
    clean_title: str
    author: str
    author_avatar_url: str
    published_at: Optional[datetime]
    content_tags: list[str]          # e.g. ["[LEAK]", "[SNIPPET]"]
    artist_labels: list[str]         # artist names extracted from thread label spans
    download_links: list[str]        # raw download URLs
    download_filenames: list[str]    # resolved display names, parallel to download_links
    reaction_path: str               # path used to build Like/Dislike URLs
    raw_soup: BeautifulSoup = field(repr=False, default=None)  # type: ignore[assignment]


# ── Scraper class ──────────────────────────────────────────────────────────

class LeakedCxScraper:
    """
    Stateful scraper that maintains an authenticated aiohttp session
    against leaked.cx.

    The caller (FeedPollerService) should check `is_authenticated` before
    each polling cycle and call `authenticate()` if the session has expired.
    """

    def __init__(self, session: ClientSession) -> None:
        self._session = session
        self._authenticated = False
        self._settings = get_settings()

    # ── Authentication ─────────────────────────────────────────────────

    @property
    def is_authenticated(self) -> bool:
        return self._authenticated

    async def authenticate(self) -> bool:
        """
        Log into leaked.cx.
        Extracts the XenForo CSRF token from the login page first.
        Returns True on success.
        """
        try:
            async with self._session.get(
                LOGIN_URL,
                headers={"User-Agent": BOT_USER_AGENT},
                timeout=self._settings.http_request_timeout,
            ) as resp:
                if resp.status != 200:
                    log.warning("Login page returned HTTP %s", resp.status)
                    self._authenticated = False
                    return False
                html = await resp.text()

            token = self._extract_csrf(html)
            if not token:
                log.error("Could not extract CSRF token from login page")
                self._authenticated = False
                return False

            payload = {
                "login": self._settings.leaked_username,
                "password": self._settings.leaked_password.get_secret_value(),
                "remember": "on",
                "_xfRedirect": "",
                "_xfToken": token,
                "_xfResponseType": "json",
            }
            headers = {
                "Referer": LOGIN_URL,
                "Origin": LEAKED_CX_BASE,
                "User-Agent": BOT_USER_AGENT,
            }
            async with self._session.post(
                LOGIN_POST_URL,
                data=payload,
                headers=headers,
                timeout=self._settings.http_request_timeout,
            ) as lresp:
                success = lresp.status == 200
                self._authenticated = success
                if success:
                    log.info("Successfully authenticated with leaked.cx")
                else:
                    log.error("Authentication failed — HTTP %s", lresp.status)
                return success

        except Exception as exc:
            log.exception("Authentication error: %s", exc)
            self._authenticated = False
            return False

    @staticmethod
    def _extract_csrf(html: str) -> Optional[str]:
        soup = BeautifulSoup(html, "html.parser")
        inp = soup.find("input", {"name": "_xfToken"})
        return inp.get("value") if inp else None  # type: ignore[union-attr]

    # ── RSS fetch ──────────────────────────────────────────────────────

    async def fetch_rss_text(
        self,
        rss_url: str,
        etag: Optional[str] = None,
        last_modified: Optional[str] = None,
    ) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Fetch RSS XML with conditional-request support.
        Returns (xml_text, new_etag, new_last_modified).
        Returns (None, None, None) if the feed is unchanged (304) or on error.
        """
        headers: dict[str, str] = {"User-Agent": BOT_USER_AGENT}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified

        try:
            async with self._session.get(
                rss_url,
                headers=headers,
                timeout=self._settings.http_request_timeout,
            ) as resp:
                if resp.status == 304:
                    log.debug("Feed unchanged (304): %s", rss_url)
                    return None, None, None
                if resp.status == 403:
                    log.warning(
                        "RSS fetch returned 403 for %s — session likely expired, will re-authenticate next cycle",
                        rss_url,
                    )
                    self._authenticated = False  # Force re-auth on next poll
                    return None, None, None
                if resp.status != 200:
                    log.warning("RSS fetch returned HTTP %s for %s", resp.status, rss_url)
                    return None, None, None

                xml_text = await resp.text()
                new_etag = resp.headers.get("ETag")
                new_last_modified = resp.headers.get("Last-Modified")
                return xml_text, new_etag, new_last_modified

        except Exception as exc:
            log.warning("RSS fetch error for %s: %s", rss_url, exc)
            return None, None, None

    # ── Thread scraping ────────────────────────────────────────────────

    async def fetch_thread(self, url: str) -> Optional[BeautifulSoup]:
        """
        Fetch a thread page and return a parsed BeautifulSoup object.
        Returns None on any HTTP error.
        """
        try:
            async with self._session.get(
                url,
                headers={"User-Agent": BOT_USER_AGENT},
                timeout=self._settings.http_request_timeout,
            ) as resp:
                if resp.status == 404:
                    return None
                if resp.status != 200:
                    log.debug("Thread fetch returned HTTP %s for %s", resp.status, url)
                    return None
                html = await resp.text()
                return BeautifulSoup(html, "lxml")
        except Exception as exc:
            log.debug("Thread fetch error for %s: %s", url, exc)
            return None

    async def validate_thread_is_recent(self, url: str) -> bool:
        """
        Quick validation: fetch thread and check if it's within the recent window.
        Returns False immediately if thread is too old (optimization to avoid full parsing).
        """
        soup = await self.fetch_thread(url)
        if soup is None:
            return False

        published_at = self._extract_published_at(soup)
        if published_at is None:
            return False

        age_minutes = (datetime.now(timezone.utc) - published_at).total_seconds() / 60
        is_recent = age_minutes <= self._settings.feed_recent_window_minutes
        
        if not is_recent:
            if self._settings.debug_mode:
                return True  # DEBUG MODE: treat all threads as recent
            log.debug("Thread too old (%.1f min) — skipping: %s", age_minutes, url)
        
        return is_recent


    async def check_thread_exists(self, url: str) -> bool:
        """
        HEAD request to check whether a thread still exists.
        Returns False on 404 or any error.
        """
        try:
            async with self._session.head(
                url,
                headers={"User-Agent": BOT_USER_AGENT},
                timeout=self._settings.http_request_timeout,
                allow_redirects=True,
            ) as resp:
                return resp.status != 404
        except Exception:
            return True  # Assume alive on network error — avoid false deletions

    async def parse_thread(
        self, url: str, rss_title: str, rss_author: str
    ) -> Optional[ParsedThread]:
        """
        Full thread parse pipeline:
        1. Fetch the thread HTML
        2. Validate the publication timestamp is within the recent window
        3. Extract all structured data
        4. Resolve download link filenames (concurrent)

        Returns None if the thread is too old, returns 404, or has no parseable content.
        """
        soup = await self.fetch_thread(url)
        if soup is None:
            return None

        # ── Publication time validation ──────────────────────────────
        published_at = self._extract_published_at(soup)
        if published_at is None:
            log.debug("No publication timestamp found for %s — skipping", url)
            return None

        age_minutes = (datetime.now(timezone.utc) - published_at).total_seconds() / 60
        if age_minutes > self._settings.feed_recent_window_minutes:
            if self._settings.debug_mode:
                log.debug("DEBUG MODE: Thread is %.1f min old but processing anyway: %s", age_minutes, url)
            else:
                log.debug("Thread too old (%.1f min): %s", age_minutes, url)
                return None

        # ── Author avatar ────────────────────────────────────────────
        author_avatar = self._extract_avatar(soup)

        # ── Title tags & artist labels ───────────────────────────────
        content_tags, artist_labels, clean_title = self._extract_title_metadata(soup, rss_title)

        # ── Download links ───────────────────────────────────────────
        download_links = self._extract_download_links(soup)

        # ── Resolve filenames concurrently ───────────────────────────
        filenames = await asyncio.gather(
            *[self._resolve_filename(link) for link in download_links],
            return_exceptions=True,
        )
        resolved: list[str] = []
        for link, name in zip(download_links, filenames):
            if isinstance(name, Exception) or not name:
                resolved.append(re.sub(r"^https?://", "", link))
            else:
                resolved.append(str(name))

        # ── Reaction path ────────────────────────────────────────────
        reaction_path = self._extract_reaction_path(soup)

        return ParsedThread(
            url=url,
            title=rss_title,
            clean_title=clean_title,
            author=rss_author,
            author_avatar_url=author_avatar,
            published_at=published_at,
            content_tags=content_tags,
            artist_labels=artist_labels,
            download_links=download_links,
            download_filenames=resolved,
            reaction_path=reaction_path,
            raw_soup=soup,
        )

    # ── Private parsing helpers ────────────────────────────────────────

    @staticmethod
    def _extract_published_at(soup: BeautifulSoup) -> Optional[datetime]:
        """Extract the XenForo thread creation timestamp."""
        time_elem = soup.find("time", class_="u-dt")
        if not time_elem:
            return None
        dt_str = time_elem.get("datetime")
        if not dt_str:
            return None
        try:
            return datetime.fromisoformat(str(dt_str).replace("Z", "+00:00"))
        except ValueError:
            return None

    @staticmethod
    def _extract_avatar(soup: BeautifulSoup) -> str:
        """Extract the thread author's avatar URL."""
        default = "https://media.discordapp.net/attachments/1367275986466635858/1457623614726865031/prefixhub.png"
        wrap = soup.find("a", class_="avatar avatar--l")
        if not wrap:
            return default
        img = wrap.find("img")
        if not img or not img.get("src"):
            return default
        src = img["src"]
        if not str(src).startswith("https://"):
            src = LEAKED_CX_BASE + src
        return str(src)

    @staticmethod
    def _extract_title_metadata(
        soup: BeautifulSoup, rss_title: str
    ) -> tuple[list[str], list[str], str]:
        """
        Parse the thread title element for:
          - content_tags: e.g. ["[LEAK]", "[SNIPPET]"]
          - artist_labels: non-content label spans (i.e. artist names)
          - clean_title: title with bracket-tags stripped
        """
        content_tags: list[str] = []
        artist_labels: list[str] = []

        title_elem = soup.find("h1", class_="p-title-value")
        if title_elem:
            for span in title_elem.find_all("span", class_="label"):
                text = span.get_text(strip=True)
                if text.lower() in CONTENT_TAGS:
                    content_tags.append(f"[{text.upper()}]")
                elif text.strip():
                    artist_labels.append(text.strip())

        # Strip [TAG] patterns from RSS title to get the clean title
        clean_title = re.sub(r"\[.*?\]", "", rss_title).strip()

        return content_tags, artist_labels, clean_title

    @staticmethod
    def _extract_download_links(soup: BeautifulSoup) -> list[str]:
        """
        Extract external (non leaked.cx) download links from the post body.
        Filters out Discord invite links from the download list —
        those are handled separately in embed building.
        """
        content_div = soup.find("div", class_="bbWrapper")
        if not content_div:
            return []

        links: list[str] = []
        for a in content_div.find_all("a", href=True):
            href = str(a["href"])
            # Skip internal leaked.cx links
            if any(domain in href for domain in EXCLUDED_LINK_DOMAINS):
                continue
            if href.startswith("http") and href not in links:
                links.append(href)

        return links

    @staticmethod
    def _extract_reaction_path(soup: BeautifulSoup) -> str:
        """Extract the base path for Like/Dislike reaction URLs."""
        reaction_elem = soup.find("a", class_="reaction")
        if not reaction_elem or not reaction_elem.get("href"):
            return ""
        href = str(reaction_elem["href"])
        return href.replace("/react?reaction_id=1", "")

    async def _resolve_filename(self, url: str) -> Optional[str]:
        """
        Attempt to resolve a human-readable filename from a file-hosting URL.
        Returns None if the domain isn't supported or the request fails.
        """
        for domain, (tag, attrs) in FILENAME_RESOLVERS.items():
            if domain in url:
                try:
                    async with self._session.get(
                        url,
                        headers={"User-Agent": BOT_USER_AGENT},
                        timeout=5,
                    ) as resp:
                        if resp.status != 200:
                            return None
                        html = await resp.text()
                    elem = BeautifulSoup(html, "html.parser").find(tag, attrs)
                    return elem.get_text(strip=True) if elem else None
                except Exception:
                    return None
        return None
