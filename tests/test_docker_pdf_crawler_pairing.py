"""Tests for the Docker API's PDF crawler pairing.

When a client requests PDFContentScrapingStrategy, the crawl handlers must
pair it with PDFCrawlerStrategy (which downloads the PDF itself) instead of a
pooled Playwright crawler — headless Chromium cannot render PDFs inline, so
browser navigation fails with "Page.goto: Download is starting" before the
scraping strategy ever runs.
"""

import importlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from crawl4ai.processors.pdf import PDFCrawlerStrategy

ROOT = Path(__file__).resolve().parent.parent

CONFIG = {
    "crawler": {
        "memory_threshold_percent": 90,
        "rate_limiter": {"enabled": False, "base_delay": [0.1, 0.3]},
        "base_config": {},
    }
}


def _crawler_config_payload(with_pdf_strategy):
    params = {"cache_mode": "bypass"}
    if with_pdf_strategy:
        params["scraping_strategy"] = {
            "type": "PDFContentScrapingStrategy",
            "params": {},
        }
    return {"type": "CrawlerRunConfig", "params": params}


@pytest.fixture
def api(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "deploy" / "docker"))
    return importlib.import_module("api")


@pytest.fixture
def pool_mock(api, monkeypatch):
    crawler_pool = importlib.import_module("crawler_pool")
    egress_broker = importlib.import_module("egress_broker")
    governor = importlib.import_module("governor")

    pooled = MagicMock()
    pooled.arun = AsyncMock(return_value=[])
    pooled.active_requests = 1  # release_crawler decrements this int
    mock = AsyncMock(return_value=pooled)
    monkeypatch.setattr(crawler_pool, "get_crawler", mock)
    monkeypatch.setattr(api, "_normalize_and_validate_seeds", lambda urls: urls)
    monkeypatch.setattr(egress_broker, "enforce_egress", lambda _: None)
    monkeypatch.setattr(governor, "clamp_deep_crawl", lambda _: None)
    return mock


@pytest.mark.asyncio
async def test_pdf_scraping_strategy_gets_pdf_crawler(api, pool_mock, monkeypatch):
    used = {}
    real_crawler_cls = api.AsyncWebCrawler

    def spy_crawler(*args, **kwargs):
        crawler = real_crawler_cls(*args, **kwargs)
        used["crawler"] = crawler
        used["crawler_strategy"] = crawler.crawler_strategy
        crawler.arun = AsyncMock(return_value=[])
        crawler.close = AsyncMock(wraps=crawler.close)
        return crawler

    monkeypatch.setattr(api, "AsyncWebCrawler", spy_crawler)

    response = await api.handle_crawl_request(
        urls=["https://example.com/document.pdf"],
        browser_config={"type": "BrowserConfig", "params": {}},
        crawler_config=_crawler_config_payload(with_pdf_strategy=True),
        config=CONFIG,
    )

    assert response["success"] is True
    assert isinstance(used["crawler_strategy"], PDFCrawlerStrategy)
    pool_mock.assert_not_awaited()
    # The dedicated PDF crawler is not pooled, so the handler must close it.
    used["crawler"].close.assert_awaited_once()


@pytest.mark.asyncio
async def test_pdf_strategy_with_hooks_rejected(api, pool_mock):
    from fastapi import HTTPException

    # A VALID hook action: without the guard this reaches set_hook and blows up
    # with AttributeError (PDFCrawlerStrategy has no set_hook) -> 500. An invalid
    # action would 400 via HookValidationError even without the guard, proving nothing.
    hooks = {"hooks": [{"action": "block_resources", "params": {"resource_types": ["image"]}}]}
    with pytest.raises(HTTPException) as exc_info:
        await api.handle_crawl_request(
            urls=["https://example.com/document.pdf"],
            browser_config={"type": "BrowserConfig", "params": {}},
            crawler_config=_crawler_config_payload(with_pdf_strategy=True),
            config=CONFIG,
            hooks_config=hooks,
        )

    assert exc_info.value.status_code == 400
    assert "PDFContentScrapingStrategy" in exc_info.value.detail
    pool_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_default_strategy_still_uses_pool(api, pool_mock):
    response = await api.handle_crawl_request(
        urls=["https://example.com/"],
        browser_config={"type": "BrowserConfig", "params": {}},
        crawler_config=_crawler_config_payload(with_pdf_strategy=False),
        config=CONFIG,
    )

    assert response["success"] is True
    pool_mock.assert_awaited_once()
