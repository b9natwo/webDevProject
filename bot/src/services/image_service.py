"""
bot/src/services/image_service.py
Fetches artist images from Last.fm.
Caches results in-memory for 1 hour to reduce outbound requests.
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Optional

from aiohttp import ClientSession
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

DEFAULT_THUMBNAIL = (
    "https://media.discordapp.net/attachments/1367275986466635858/"
    "1457623614726865031/prefixhub.png"
)
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}
_IMAGE_LIST_SELECTORS = [
    ("li", {"class": "image-list-item-wrapper"}),
    ("li", {"class": "image-list-item"}),
    ("div", {"class": "image-list-item-wrapper"}),
]
_GALLERY_IMG_SELECTORS = [
    ("img", {"class": "js-gallery-image"}),
    ("img", {"class": "gallery-image"}),
    ("meta", {"property": "og:image"}),
]
_CACHE_TTL = 3600  # 1 hour


class ImageService:
    """
    Provides artist thumbnail URLs sourced from Last.fm.
    Results are cached per-artist to avoid hammering Last.fm.
    """

    def __init__(self, session: ClientSession) -> None:
        self._session = session
        self._cache: dict[str, tuple[str, float]] = {}  # name -> (url, expires_at)

    async def get_artist_image(self, artist: str) -> str:
        """
        Return a thumbnail URL for the given artist.
        Falls back to DEFAULT_THUMBNAIL on any failure.
        """
        if not artist:
            return DEFAULT_THUMBNAIL

        key = artist.lower().strip()
        cached = self._cache.get(key)
        if cached and time.monotonic() < cached[1]:
            return cached[0]

        url = await self._fetch_lastfm_image(artist)
        self._cache[key] = (url, time.monotonic() + _CACHE_TTL)
        return url

    async def _fetch_lastfm_image(self, artist: str) -> str:
        slug = artist.title().replace(" ", "+")
        pages = [""] + [f"?page={i}" for i in range(2, 6)]
        list_url = f"https://www.last.fm/music/{slug}/+images{random.choice(pages)}"

        try:
            async with self._session.get(list_url, headers=_HEADERS, timeout=10) as resp:
                if resp.status != 200:
                    return DEFAULT_THUMBNAIL
                content = await resp.text()
        except Exception:
            return DEFAULT_THUMBNAIL

        soup = BeautifulSoup(content, "html.parser")
        list_items: list = []
        for tag, attrs in _IMAGE_LIST_SELECTORS:
            list_items = soup.find_all(tag, attrs)
            if list_items:
                break

        if not list_items:
            grid = soup.find("ul", class_="image-list") or soup.find("div", class_="image-list")
            if grid:
                list_items = grid.find_all("a", href=True)

        if not list_items:
            return DEFAULT_THUMBNAIL

        item = random.choice(list_items)
        anchor = item if item.name == "a" else item.find("a")
        if not anchor or not anchor.get("href"):
            return DEFAULT_THUMBNAIL

        href = anchor["href"]
        if not href.startswith("http"):
            href = "https://www.last.fm" + href

        try:
            async with self._session.get(href, headers=_HEADERS, timeout=10) as resp:
                if resp.status != 200:
                    return DEFAULT_THUMBNAIL
                image_content = await resp.text()
        except Exception:
            return DEFAULT_THUMBNAIL

        image_soup = BeautifulSoup(image_content, "html.parser")
        for tag, attrs in _GALLERY_IMG_SELECTORS:
            elem = image_soup.find(tag, attrs)
            if not elem:
                continue
            src = elem.get("content") or elem.get("src")
            if src:
                return str(src).split("#")[0].strip()

        return DEFAULT_THUMBNAIL

    def clear_cache(self) -> None:
        """Clear the in-memory image cache."""
        self._cache.clear()
