# -*- coding: utf-8 -*-
"""
arminer.data.news_scraper
=========================
Comprehensive Multi-Source News Scraper & Aggregator for Vietnamese Listed Companies.

Features:
- Company Website Directory (~1,430+ tickers) with Auto-Discovery heuristic
- Generic content extraction powered by `trafilatura` with BeautifulSoup fallback
- Multi-source aggregation (Official Company Website, CafeF, Tin Nhanh Chung Khoan, VnEconomy, Custom URLs)
- Dynamic quota backfill ("bù đắp nguồn"): if one source lacks articles or errors, others backfill
- Title-based deduplication
- Async streaming progress callbacks for realtime UI updates
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from difflib import SequenceMatcher
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Callable, Dict, Generator, List, Optional, Set, Tuple
import urllib.parse
from urllib.parse import urljoin, urlparse

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

from loguru import logger
import requests

try:
    import trafilatura
except ImportError:
    trafilatura = None

# Shared User-Agent and headers
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
WEBSITES_DB_PATH = FIXTURES_DIR / "company_websites.json"


class CompanyWebsiteResolver:
    """Manages ticker-to-website mappings with local caching and auto-discovery."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or WEBSITES_DB_PATH
        self._db: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self):
        if self.db_path.exists():
            try:
                with open(self.db_path, "r", encoding="utf-8") as f:
                    self._db = json.load(f)
                logger.info(f"Loaded {len(self._db)} company records from {self.db_path.name}")
            except Exception as e:
                logger.error(f"Failed to load company websites DB: {e}")
                self._db = {}
        else:
            self._db = {}

    def save(self):
        """Persist database changes back to disk."""
        try:
            with open(self.db_path, "w", encoding="utf-8") as f:
                json.dump(self._db, f, ensure_ascii=False, indent=2)
            logger.debug(f"Saved {len(self._db)} company records to {self.db_path.name}")
        except Exception as e:
            logger.error(f"Failed to save company websites DB: {e}")

    def get_company(self, ticker: str) -> Optional[Dict[str, Any]]:
        return self._db.get(ticker.upper().strip())

    def resolve_website(self, ticker: str, auto_discover: bool = True) -> Optional[str]:
        """
        Get company website URL.
        If not configured, runs auto-discovery heuristic, caches, and returns URL.
        """
        t = ticker.upper().strip()
        comp = self._db.get(t)
        if comp and comp.get("website"):
            return comp["website"]

        if not auto_discover:
            return None

        # Run Auto-Discovery
        discovered = self.discover_website(t)
        if discovered:
            if t not in self._db:
                self._db[t] = {
                    "ticker": t,
                    "name": f"Doanh nghiệp niêm yết {t}",
                    "exchange": "HOSE/HNX",
                    "website": discovered,
                    "ir_portal": None,
                    "news_paths": ["/tin-tuc", "/bai-viet", "/news", "/quan-he-co-dong"],
                }
            else:
                self._db[t]["website"] = discovered
            self.save()
            return discovered

        return None

    def discover_website(self, ticker: str) -> Optional[str]:
        """Auto-discover official company website via search engine query."""
        t = ticker.upper().strip()
        comp = self._db.get(t, {})
        name = comp.get("name", "")

        query = f"trang chu cong ty co phan {name or t} {t}"
        logger.info(f"Auto-discovering website for {t} with query: '{query}'")

        try:
            encoded = urllib.parse.quote(query)
            url = f"https://html.duckduckgo.com/html/?q={encoded}"
            resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=6)
            if resp.status_code == 200:
                # Extract DuckDuckGo results
                # Look for uddg redirect or direct hrefs
                raw_urls = re.findall(r'uddg=([^&"\']+)', resp.text)
                candidates = [urllib.parse.unquote(u) for u in raw_urls]

                # Filter out financial portals, social media, government portals
                excluded_domains = [
                    "duckduckgo", "google", "facebook", "youtube", "twitter",
                    "cafef.vn", "vietstock.vn", "vndirect.com.vn", "ssi.com.vn",
                    "fireant.vn", "24hmoney.vn", "tinnhanhchungkhoan.vn",
                    "vneconomy.vn", "baodautu.vn", "wikipedia.org", "hsx.vn", "hnx.vn",
                ]

                for candidate in candidates:
                    parsed = urlparse(candidate)
                    domain = parsed.netloc.lower()
                    if any(ex in domain for ex in excluded_domains):
                        continue
                    if domain:
                        clean_url = f"{parsed.scheme or 'https'}://{domain}"
                        logger.info(f"Auto-discovered official website for {t}: {clean_url}")
                        return clean_url
        except Exception as e:
            logger.warning(f"Auto-discovery failed for {t}: {e}")

        return None

    def update_company(self, ticker: str, website: Optional[str] = None, ir_portal: Optional[str] = None):
        t = ticker.upper().strip()
        if t not in self._db:
            self._db[t] = {
                "ticker": t,
                "name": f"Doanh nghiệp {t}",
                "exchange": "HOSE/HNX",
                "website": website,
                "ir_portal": ir_portal,
                "news_paths": ["/tin-tuc", "/bai-viet", "/news", "/quan-he-co-dong"],
            }
        else:
            if website is not None:
                self._db[t]["website"] = website
            if ir_portal is not None:
                self._db[t]["ir_portal"] = ir_portal
        self.save()

    def list_companies(
        self,
        query: Optional[str] = None,
        exchange: Optional[str] = None,
        has_website_only: bool = False,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        results = []
        q = (query or "").lower().strip()
        ex = (exchange or "").upper().strip()

        for t, d in self._db.items():
            if ex and ex not in d.get("exchange", ""):
                continue
            if has_website_only and not d.get("website"):
                continue
            if q:
                match = (
                    q in t.lower()
                    or q in d.get("name", "").lower()
                    or q in (d.get("website") or "").lower()
                )
                if not match:
                    continue

            results.append(d)
            if len(results) >= limit:
                break

        return results


class UniversalNewsExtractor:
    """Extracts article content, clean text, publication date, and title from any webpage."""

    @staticmethod
    def extract_from_html(html: str, url: str) -> Optional[Dict[str, Any]]:
        if not html or len(html.strip()) < 100:
            return None

        # 1. Try Trafilatura with metadata
        try:
            extracted_json = trafilatura.extract(
                html,
                url=url,
                output_format="json",
                with_metadata=True,
                include_comments=False,
                include_tables=True,
                favor_recall=True,
            )
            if extracted_json:
                data = json.loads(extracted_json)
                text = data.get("text") or ""
                title = data.get("title") or ""
                date = data.get("date") or ""
                author = data.get("author") or ""

                pub_year = UniversalNewsExtractor.parse_year(date, url, text)
                if text and len(text.strip()) > 80:
                    return {
                        "url": url,
                        "title": title.strip() or UniversalNewsExtractor._extract_title_soup(html),
                        "text": text.strip(),
                        "published_date": date,
                        "published_year": pub_year,
                        "author": author,
                        "word_count": len(text.split()),
                        "extractor": "trafilatura",
                    }
        except Exception as e:
            logger.debug(f"Trafilatura extraction warning for {url}: {e}")

        # 2. BeautifulSoup Fallback
        try:
            soup = BeautifulSoup(html, "html.parser")
            # Remove scripts, styles, navigations, footers
            for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
                tag.decompose()

            title = ""
            h1 = soup.find("h1")
            if h1 and h1.get_text(strip=True):
                title = h1.get_text(strip=True)
            elif soup.title and soup.title.get_text(strip=True):
                title = soup.title.get_text(strip=True)

            # Look for common article body containers
            candidates = soup.find_all(
                ["article", "div", "section"],
                class_=re.compile(r"content|article|detail|post-body|entry-content", re.IGNORECASE),
            )
            body_text = ""
            if candidates:
                # Pick the longest container
                longest = max(candidates, key=lambda c: len(c.get_text(strip=True)))
                body_text = longest.get_text(separator="\n", strip=True)
            else:
                # Fallback to all paragraphs
                paras = [p.get_text(strip=True) for p in soup.find_all("p") if len(p.get_text(strip=True)) > 20]
                body_text = "\n\n".join(paras)

            if len(body_text.strip()) > 80:
                # Look for meta date
                date = ""
                time_tag = soup.find("time")
                if time_tag:
                    date = time_tag.get("datetime") or time_tag.get_text(strip=True)
                if not date:
                    meta_date = soup.find("meta", property=re.compile(r"date|time", re.IGNORECASE))
                    if meta_date:
                        date = meta_date.get("content", "")

                pub_year = UniversalNewsExtractor.parse_year(str(date), url, body_text)
                return {
                    "url": url,
                    "title": title.strip(),
                    "text": body_text.strip(),
                    "published_date": str(date)[:10] if date else "",
                    "published_year": pub_year,
                    "author": "",
                    "word_count": len(body_text.split()),
                    "extractor": "beautifulsoup_fallback",
                }
        except Exception as e:
            logger.warning(f"Soup extraction failed for {url}: {e}")

        return None

    @staticmethod
    def parse_year(date_str: str = "", url: str = "", text: str = "") -> Optional[int]:
        """Extract publication year (e.g. 2024) from date string, URL, or lead text."""
        # 1. Date string (e.g. 2024-03-15 or 15/03/2024)
        if date_str:
            m = re.search(r"\b(20[0-2]\d)\b", str(date_str))
            if m:
                return int(m.group(1))
        # 2. URL path (e.g. /2024/05/ or -2023.html)
        if url:
            m = re.search(r"/(20[0-2]\d)[/-]", url)
            if m:
                return int(m.group(1))
            m2 = re.search(r"\b(20[0-2]\d)\b", url)
            if m2:
                return int(m2.group(1))
        # 3. Text opening (dateline e.g. "Hà Nội, 15/04/2024 -")
        if text:
            m = re.search(r"\b\d{1,2}[/-]\d{1,2}[/-](20[0-2]\d)\b", text[:500])
            if m:
                return int(m.group(1))
            m_year = re.search(r"\b(20[0-2]\d)\b", text[:200])
            if m_year:
                return int(m_year.group(1))
        return None

    @staticmethod
    def _extract_title_soup(html: str) -> str:
        try:
            soup = BeautifulSoup(html, "html.parser")
            if soup.title and soup.title.get_text(strip=True):
                return soup.title.get_text(strip=True)
            h1 = soup.find("h1")
            if h1:
                return h1.get_text(strip=True)
        except Exception:
            pass
        return "Không có tiêu đề"


class CafeFScraper:
    """Scrapes news articles related to a ticker from CafeF."""

    BASE_SEARCH_URL = "https://cafef.vn/tim-kiem.chn?keywords={ticker}&page={page}"

    @classmethod
    def get_article_links(cls, ticker: str, max_links: int = 30) -> List[str]:
        links: List[str] = []
        page = 1
        max_pages = max(1, (max_links + 19) // 20)

        while len(links) < max_links and page <= max_pages:
            url = cls.BASE_SEARCH_URL.format(ticker=urllib.parse.quote(ticker), page=page)
            try:
                resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=8)
                if resp.status_code != 200:
                    break

                soup = BeautifulSoup(resp.text, "html.parser")
                found_in_page = 0
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    # CafeF articles end with -[0-9]+.chn
                    if re.search(r"-\d+\.chn$", href):
                        full_url = href if href.startswith("http") else f"https://cafef.vn{href}"
                        if full_url not in links:
                            links.append(full_url)
                            found_in_page += 1
                            if len(links) >= max_links:
                                break

                if found_in_page == 0:
                    break
                page += 1
            except Exception as e:
                logger.warning(f"CafeF search failed for {ticker} page {page}: {e}")
                break

        return links


class CafeBizScraper:
    """Scrapes news articles related to a ticker from CafeBiz."""

    BASE_SEARCH_URL = "https://cafebiz.vn/search.chn?keywords={ticker}&page={page}"

    @classmethod
    def get_article_links(cls, ticker: str, max_links: int = 30) -> List[str]:
        links: List[str] = []
        page = 1
        max_pages = max(1, (max_links + 19) // 20)

        while len(links) < max_links and page <= max_pages:
            url = cls.BASE_SEARCH_URL.format(ticker=urllib.parse.quote(ticker), page=page)
            try:
                resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=8)
                if resp.status_code != 200:
                    break

                soup = BeautifulSoup(resp.text, "html.parser")
                found_in_page = 0
                for a in soup.find_all("a", href=True):
                    href = a["href"].strip()
                    if re.search(r"-\d+\.chn$", href):
                        full_url = href if href.startswith("http") else f"https://cafebiz.vn{href}"
                        if full_url not in links:
                            links.append(full_url)
                            found_in_page += 1
                            if len(links) >= max_links:
                                break

                if found_in_page == 0:
                    break
                page += 1
            except Exception as e:
                logger.warning(f"CafeBiz search failed for {ticker} page {page}: {e}")
                break

        return links


class VnExpressScraper:
    """Scrapes business news from VnExpress (Chuyên mục Kinh Doanh)."""

    BASE_SEARCH_URL = "https://timkiem.vnexpress.net/?q={ticker}&cate_code=kinh-doanh&page={page}"

    @classmethod
    def get_article_links(cls, ticker: str, max_links: int = 30) -> List[str]:
        links: List[str] = []
        page = 1
        max_pages = max(1, (max_links + 14) // 15)

        while len(links) < max_links and page <= max_pages:
            url = cls.BASE_SEARCH_URL.format(ticker=urllib.parse.quote(ticker), page=page)
            try:
                resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=8)
                if resp.status_code != 200:
                    break

                soup = BeautifulSoup(resp.text, "html.parser")
                found_in_page = 0
                for a in soup.find_all("a", href=True):
                    href = a["href"].strip()
                    if re.search(r"-\d+\.html$", href) and "vnexpress.net" in href:
                        if href not in links and not any(x in href for x in ["/video/", "/podcast/", "/anh/"]):
                            links.append(href)
                            found_in_page += 1
                            if len(links) >= max_links:
                                break

                if found_in_page == 0:
                    break
                page += 1
            except Exception as e:
                logger.warning(f"VnExpress search failed for {ticker} page {page}: {e}")
                break

        return links


class VietnamNetScraper:
    """Scrapes business news from VietnamNet."""

    BASE_SEARCH_URL = "https://vietnamnet.vn/tim-kiem?q={ticker}&c=kinh-doanh&page={page}"

    @classmethod
    def get_article_links(cls, ticker: str, max_links: int = 30) -> List[str]:
        links: List[str] = []
        page = 1
        max_pages = max(1, (max_links + 14) // 15)

        while len(links) < max_links and page <= max_pages:
            url = cls.BASE_SEARCH_URL.format(ticker=urllib.parse.quote(ticker), page=page)
            try:
                resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=8)
                if resp.status_code != 200:
                    break

                soup = BeautifulSoup(resp.text, "html.parser")
                found_in_page = 0
                for a in soup.find_all("a", href=True):
                    href = a["href"].strip()
                    if re.search(r"-\d+\.html$", href):
                        full_url = href if href.startswith("http") else urljoin("https://vietnamnet.vn", href)
                        if full_url not in links and not any(x in full_url for x in ["/video/", "/podcast/"]):
                            links.append(full_url)
                            found_in_page += 1
                            if len(links) >= max_links:
                                break

                if found_in_page == 0:
                    break
                page += 1
            except Exception as e:
                logger.warning(f"VietnamNet search failed for {ticker} page {page}: {e}")
                break

        return links


class TinNhanhCKScraper:
    """Scrapes news from Tin Nhanh Chung Khoan (Dau tu Chung khoan - vir.com.vn)."""

    BASE_SEARCH_URL = "https://tinnhanhchungkhoan.vn/tim-kiem/?q={ticker}&page={page}"

    @classmethod
    def get_article_links(cls, ticker: str, max_links: int = 30) -> List[str]:
        links: List[str] = []
        page = 1
        max_pages = max(1, (max_links + 19) // 20)

        while len(links) < max_links and page <= max_pages:
            url = cls.BASE_SEARCH_URL.format(ticker=urllib.parse.quote(ticker), page=page)
            try:
                resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=8)
                if resp.status_code != 200:
                    break

                soup = BeautifulSoup(resp.text, "html.parser")
                found_in_page = 0
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    # TinNhanhCK article links typically contain -post[0-9]+.html or /tin-tuc-
                    if re.search(r"-post\d+\.html$", href) or re.search(r"-\d+\.html$", href):
                        full_url = href if href.startswith("http") else urljoin("https://tinnhanhchungkhoan.vn", href)
                        if full_url not in links:
                            links.append(full_url)
                            found_in_page += 1
                            if len(links) >= max_links:
                                break

                if found_in_page == 0:
                    break
                page += 1
            except Exception as e:
                logger.warning(f"TinNhanhCK search failed for {ticker} page {page}: {e}")
                break

        return links


class VnEconomyScraper:
    """Scrapes news from VnEconomy."""

    BASE_SEARCH_URL = "https://vneconomy.vn/tim-kiem.htm?q={ticker}"

    @classmethod
    def get_article_links(cls, ticker: str, max_links: int = 30) -> List[str]:
        links: List[str] = []
        url = cls.BASE_SEARCH_URL.format(ticker=urllib.parse.quote(ticker))
        try:
            resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=8)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    # VnEconomy articles end with .htm and have slug
                    if href.endswith(".htm") and not any(x in href for x in ["tim-kiem", "tag", "chuyen-muc"]):
                        full_url = href if href.startswith("http") else urljoin("https://vneconomy.vn", href)
                        if full_url not in links and len(full_url.split("/")[-1]) > 10:
                            links.append(full_url)
                            if len(links) >= max_links:
                                break
        except Exception as e:
            logger.warning(f"VnEconomy search failed for {ticker}: {e}")

        return links


class CompanyWebsiteScraper:
    """Scrapes news articles from official company website and IR portal."""

    def __init__(self, resolver: CompanyWebsiteResolver):
        self.resolver = resolver

    def get_article_links(self, ticker: str, max_links: int = 30) -> List[str]:
        comp = self.resolver.get_company(ticker)
        website = self.resolver.resolve_website(ticker)
        if not website:
            logger.warning(f"No website available for {ticker}")
            return []

        article_links: Set[str] = set()
        news_paths = (comp.get("news_paths") if comp else None) or [
            "/tin-tuc", "/bai-viet", "/news", "/quan-he-co-dong",
            "/thong-bao", "/su-kien", "/press-release", "/quan-he-nha-dau-tu/tin-tuc"
        ]

        # Also check IR portal if available
        ir_portal = comp.get("ir_portal") if comp else None
        target_urls = [urljoin(website, p) for p in news_paths]
        if ir_portal:
            target_urls.insert(0, ir_portal)

        domain = urlparse(website).netloc.replace("www.", "").lower()

        domain_failed = False
        for target_url in target_urls:
            if domain_failed or len(article_links) >= max_links:
                break
            try:
                resp = requests.get(target_url, headers=DEFAULT_HEADERS, timeout=4)
                if resp.status_code != 200:
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    href = a["href"].strip()
                    if not href or href.startswith("#") or "javascript:" in href:
                        continue

                    full_url = urljoin(target_url, href)
                    full_domain = urlparse(full_url).netloc.replace("www.", "").lower()

                    # Keep only links within the same domain
                    if domain in full_domain or full_domain in domain:
                        # Match news/article keywords in path or slug
                        path_lower = urlparse(full_url).path.lower()
                        is_news = any(k in path_lower for k in [
                            "tin-tuc", "news", "bai-viet", "thong-bao", "su-kien",
                            "co-dong", "quan-he", "detail", "post", "article", "press"
                        ])
                        # Slug should be reasonably long
                        slug = path_lower.rstrip("/").split("/")[-1]
                        if is_news and len(slug) > 8 and full_url != target_url:
                            article_links.add(full_url)
                            if len(article_links) >= max_links:
                                break
            except (requests.exceptions.ConnectTimeout, requests.exceptions.ConnectionError) as e:
                logger.debug(f"Connection failed for {domain} ({e}), skipping remaining paths for this company.")
                domain_failed = True
                break
            except Exception as e:
                logger.debug(f"Failed crawling {target_url} for {ticker}: {e}")

        return list(article_links)


class MultiSourceNewsAggregator:
    """
    Coordinates crawling across all sources with dynamic quota backfill
    ("thiếu nguồn này thì nguồn khác đắp vào") and deduplication.
    """

    def __init__(self, resolver: Optional[CompanyWebsiteResolver] = None):
        self.resolver = resolver or CompanyWebsiteResolver()
        self.extractor = UniversalNewsExtractor()
        self.company_scraper = CompanyWebsiteScraper(self.resolver)

    def fetch_article(self, url: str, source_name: str, ticker: str) -> Optional[Dict[str, Any]]:
        """Download and extract clean content from article URL."""
        try:
            resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=10)
            if resp.status_code != 200:
                return None

            extracted = self.extractor.extract_from_html(resp.text, url)
            if extracted and extracted.get("text"):
                extracted["news_source"] = source_name
                extracted["ticker"] = ticker
                return extracted
        except Exception as e:
            logger.debug(f"Fetch article failed for {url}: {e}")
        return None

    def crawl_ticker(
        self,
        ticker: str,
        sources: List[str],
        target_articles: int = 25,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        custom_urls: Optional[List[str]] = None,
        progress_cb: Optional[Callable[[str, int, int], None]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Gathers articles for a ticker across requested sources.
        Implements dynamic backfill: if source X returns fewer than target,
        other sources are queried for additional articles to reach target_articles.
        Optionally filters by publication year range [year_from, year_to].
        """
        t = ticker.upper().strip()
        collected_articles: List[Dict[str, Any]] = []
        seen_titles: List[str] = []

        def is_duplicate(title: str) -> bool:
            t_clean = re.sub(r"[^\w\s]", "", title.lower()).strip()
            for prev in seen_titles:
                ratio = SequenceMatcher(None, t_clean, prev).ratio()
                if ratio > 0.75:
                    return True
            seen_titles.append(t_clean)
            return False

        # Phase 1: Collect article links per source
        links_by_source: Dict[str, List[str]] = {}
        # Fetch slightly higher buffer if year filtering is active to account for filtered years
        multiplier = 2 if (year_from or year_to) else 1
        target_per_source = max(5, ((target_articles * multiplier) // max(1, len(sources))) + 4)

        if progress_cb:
            progress_cb(f"Đang tìm kiếm link bài viết cho {t}...", 0, target_articles)

        # 1. Custom URLs
        if "custom" in sources and custom_urls:
            links_by_source["custom"] = custom_urls[:target_articles * multiplier]

        # 2. Company Website
        if "company_website" in sources:
            if progress_cb:
                progress_cb(f"Đang quét trang tin tức trên website {t}...", len(collected_articles), target_articles)
            comp_links = self.company_scraper.get_article_links(t, max_links=target_per_source)
            links_by_source["company_website"] = comp_links

        # 3. CafeF
        if "cafef" in sources:
            if progress_cb:
                progress_cb(f"Đang tìm tin tức {t} trên CafeF...", len(collected_articles), target_articles)
            cafef_links = CafeFScraper.get_article_links(t, max_links=target_per_source)
            links_by_source["cafef"] = cafef_links

        # 4. Tin Nhanh Chung Khoan
        if "tinnhanhchungkhoan" in sources:
            if progress_cb:
                progress_cb(f"Đang tìm tin {t} trên Tin Nhanh Chứng Khoán...", len(collected_articles), target_articles)
            tn_links = TinNhanhCKScraper.get_article_links(t, max_links=target_per_source)
            links_by_source["tinnhanhchungkhoan"] = tn_links

        # 5. VnEconomy
        if "vneconomy" in sources:
            if progress_cb:
                progress_cb(f"Đang tìm tin {t} trên VnEconomy...", len(collected_articles), target_articles)
            vne_links = VnEconomyScraper.get_article_links(t, max_links=target_per_source)
            links_by_source["vneconomy"] = vne_links

        # 6. VnExpress Kinh Doanh
        if "vnexpress" in sources:
            if progress_cb:
                progress_cb(f"Đang tìm tin {t} trên VnExpress Kinh Doanh...", len(collected_articles), target_articles)
            vnex_links = VnExpressScraper.get_article_links(t, max_links=target_per_source)
            links_by_source["vnexpress"] = vnex_links

        # 7. CafeBiz
        if "cafebiz" in sources:
            if progress_cb:
                progress_cb(f"Đang tìm tin {t} trên CafeBiz...", len(collected_articles), target_articles)
            biz_links = CafeBizScraper.get_article_links(t, max_links=target_per_source)
            links_by_source["cafebiz"] = biz_links

        # 8. VietnamNet Kinh Doanh
        if "vietnamnet" in sources:
            if progress_cb:
                progress_cb(f"Đang tìm tin {t} trên VietnamNet...", len(collected_articles), target_articles)
            vnn_links = VietnamNetScraper.get_article_links(t, max_links=target_per_source)
            links_by_source["vietnamnet"] = vnn_links

        # Interleave links from sources to achieve a balanced and diverse aggregation
        all_candidate_links: List[Tuple[str, str]] = []  # (url, source_name)
        source_keys = list(links_by_source.keys())
        max_len = max([len(v) for v in links_by_source.values()]) if links_by_source else 0

        for idx in range(max_len):
            for s_key in source_keys:
                s_links = links_by_source[s_key]
                if idx < len(s_links):
                    all_candidate_links.append((s_links[idx], s_key))

        # Backfill expansion: if total links < target_articles and portals can provide more
        existing_urls = {u for u, _ in all_candidate_links}
        if len(all_candidate_links) < (target_articles * multiplier):
            needed = (target_articles * multiplier) - len(all_candidate_links)
            for backfill_src, scraper_fn in [
                ("cafef", lambda: CafeFScraper.get_article_links(t, max_links=target_per_source + needed + 10)),
                ("cafebiz", lambda: CafeBizScraper.get_article_links(t, max_links=target_per_source + needed + 10)),
                ("vnexpress", lambda: VnExpressScraper.get_article_links(t, max_links=target_per_source + needed + 10)),
            ]:
                if backfill_src in sources:
                    extra_links = scraper_fn()
                    for u in extra_links:
                        if u not in existing_urls:
                            all_candidate_links.append((u, f"{backfill_src} (bù đắp)"))
                            existing_urls.add(u)
                            if len(all_candidate_links) >= (target_articles * multiplier):
                                break
                if len(all_candidate_links) >= (target_articles * multiplier):
                    break

        # Phase 2: Fetch articles content concurrently
        total_links = len(all_candidate_links)
        logger.info(f"Starting content extraction for {t}: {total_links} links queued")

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_meta = {
                executor.submit(self.fetch_article, url, src, t): (url, src)
                for url, src in all_candidate_links
            }

            for future in concurrent.futures.as_completed(future_to_meta):
                url, src = future_to_meta[future]
                try:
                    art = future.result()
                    if art and art.get("title") and not is_duplicate(art["title"]):
                        # Year range filter check
                        art_year = art.get("published_year")
                        if not art_year:
                            art_year = UniversalNewsExtractor.parse_year(
                                art.get("published_date", ""),
                                art.get("url", ""),
                                art.get("text", ""),
                            )
                            if art_year:
                                art["published_year"] = art_year

                        if art_year:
                            if year_from is not None and art_year < year_from:
                                continue
                            if year_to is not None and art_year > year_to:
                                continue

                        collected_articles.append(art)
                        if progress_cb:
                            progress_cb(
                                f"Đã thu thập: {art['title'][:40]}... ({src})",
                                len(collected_articles),
                                target_articles,
                            )
                        if len(collected_articles) >= target_articles:
                            break
                except Exception as e:
                    logger.debug(f"Error processing article {url}: {e}")

        logger.info(f"Finished crawling for {t}: collected {len(collected_articles)} articles")
        return collected_articles
