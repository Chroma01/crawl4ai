import inspect
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api import _raise_for_crawl_failure, handle_llm_qa, handle_markdown_request


def test_crawl_failure_is_reported_as_bad_gateway():
    result = SimpleNamespace(success=False, error_message="Blocked by anti-bot protection: challenge")

    with pytest.raises(HTTPException) as raised:
        _raise_for_crawl_failure(result)

    assert raised.value.status_code == 502
    assert raised.value.detail == result.error_message


@pytest.mark.parametrize("handler", [handle_llm_qa, handle_markdown_request])
def test_single_url_handlers_use_crawl_failure_mapping(handler):
    source = inspect.getsource(handler)
    assert "_raise_for_crawl_failure(result)" in source
    assert handler is not handle_llm_qa or "except HTTPException:" in source
