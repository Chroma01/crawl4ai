"""The body-visibility wait must not time out silently (issue #2144).

When the wait times out and `ignore_body_visibility` is True (the default), the
result is discarded and the crawl succeeds — just `body_visibility_timeout` ms
slower, with no signal at all. That silence is what made the delay in #2129
impossible to attribute without instrumenting the pipeline, and what makes
`body_visibility_timeout` undiscoverable. A warning names the option.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from crawl4ai.async_configs import CrawlerRunConfig
from crawl4ai.async_crawler_strategy import AsyncPlaywrightCrawlerStrategy


def _strategy(is_visible: bool):
    """A strategy whose body-visibility wait returns `is_visible`."""
    page = MagicMock()
    page.evaluate = AsyncMock()
    page.set_content = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.content = AsyncMock(return_value="<body>hi</body>")

    strategy = AsyncPlaywrightCrawlerStrategy.__new__(AsyncPlaywrightCrawlerStrategy)
    strategy.browser_config = SimpleNamespace(
        use_persistent_context=False, accept_downloads=False, text_mode=True, verbose=False
    )
    strategy.browser_manager = SimpleNamespace(
        get_page=AsyncMock(return_value=(page, MagicMock()))
    )
    strategy.execute_hook = AsyncMock()
    strategy.csp_compliant_wait = AsyncMock(return_value=is_visible)
    strategy.check_visibility = AsyncMock(return_value={})
    strategy.logger = MagicMock()
    return strategy


def _warnings(strategy):
    return [
        call.kwargs.get("message", "")
        for call in strategy.logger.warning.call_args_list
    ]


@pytest.mark.asyncio
async def test_warns_when_wait_times_out_and_result_is_discarded():
    strategy = _strategy(is_visible=False)
    config = CrawlerRunConfig(
        session_id="body-vis-warn", body_visibility_timeout=1234
    )

    await strategy._crawl_web("raw:<body>hi</body>", config)

    messages = _warnings(strategy)
    assert any("never became visible" in m for m in messages), messages
    assert any("body_visibility_timeout" in m for m in messages), messages
    # The timeout that actually applied is reported, not the hardcoded default.
    params = strategy.logger.warning.call_args.kwargs["params"]
    assert params["timeout"] == 1234


@pytest.mark.asyncio
async def test_no_warning_when_body_is_visible():
    strategy = _strategy(is_visible=True)
    config = CrawlerRunConfig(session_id="body-vis-quiet")

    await strategy._crawl_web("raw:<body>hi</body>", config)

    assert not any("never became visible" in m for m in _warnings(strategy))


@pytest.mark.asyncio
async def test_no_warning_when_hidden_body_is_treated_as_an_error():
    """With ignore_body_visibility=False the hidden body raises with details,
    so the warning would be redundant noise."""
    from playwright.async_api import Error

    strategy = _strategy(is_visible=False)
    config = CrawlerRunConfig(
        session_id="body-vis-strict", ignore_body_visibility=False
    )

    with pytest.raises(Error, match="Body element is hidden"):
        await strategy._crawl_web("raw:<body>hi</body>", config)

    assert not any("never became visible" in m for m in _warnings(strategy))
