# Crawl4AI v0.9.3: Security Release

*August 2026 - 4 min read*

---

I'm releasing Crawl4AI v0.9.3, a security release that closes five coordinated-disclosure advisories. No new features, no breaking changes.

Four of the five are in the PDF path, and they share one root cause. `PDFContentScrapingStrategy` can be selected from an untrusted Docker API request body, and it downloads with `requests` rather than through the browser. Every control the server applies on the Chromium side (destination pinning, resource caps) simply did not reach it. The fifth is a DOM-based XSS in the Playground UI that could hand an operator's API token to an attacker.

If you self-host the Docker server and accept crawl requests from clients you do not fully trust, upgrade. If you use the pip library and open PDFs from sources you do not control, upgrade.

## What's fixed at a glance

- **Arbitrary file write**: an untrusted request body could choose where extracted PDF images were written
- **SSRF**: the PDF download followed redirects into internal addresses
- **Denial of service**: remote PDFs were downloaded and parsed with no size or page cap
- **XSS**: PDF text was written into `cleaned_html` without escaping
- **DOM XSS**: the Playground result viewer re-parsed crawled content as live HTML

## Security fixes

### Arbitrary file write via PDF image-write fields

**GHSA-xpp7-j28w-2gvx, CWE-22, high.** Credit: Zhixi "Jace" Sun, independent security researcher.

`PDFContentScrapingStrategy` was in the untrusted-allowed type list but had no field allowlist of its own. A request body could therefore set `save_images_locally: true` and `image_save_dir` to any path, and the server would write extracted PDF images there.

Both fields are now filtered out of untrusted bodies at the trust boundary, and `extract_images` is forced off for them. Rasterizing every page of a caller-supplied PDF is the most expensive thing this strategy can do, and nothing about untrusted crawling needs it.

### SSRF via PDF download redirects

**GHSA-q5rj-45vw-vp2g, CWE-918, high.** Credit: Nguyen Tran Thanh Lam ([c240030](https://github.com/c240030)).

The PDF download let `requests` follow redirects on its own. A public, allowed URL that returned a 302 to `169.254.169.254` or any other internal address was fetched without the destination ever being checked.

Redirects are now resolved by hand, one hop at a time, with the destination policy consulted before each hop is fetched and a cap of five hops. The peer IP of the response whose body is actually read back is validated too, which closes DNS rebinding: passing the URL check only proves the *name* resolved somewhere allowed, and `requests` resolves it again when it dials.

The library ships with no egress policy of its own, because a plain library caller already chose the URL. The Docker server installs its existing `egress_broker` policy into the PDF path at boot, so that path now gets the same non-global-IP rule the browser path already had.

### Denial of service via unbounded PDF size and page count

**GHSA-v2rm-hvrj-2x9q, CWE-400, medium.** Credit: Nguyen Tran Thanh Lam ([c240030](https://github.com/c240030)).

A remote PDF was streamed to a temp file with no cap and then parsed with no page limit. One request pointing at a large or many-page PDF could exhaust disk, CPU, and bandwidth on a shared worker.

Downloads now stop at `max_pdf_bytes`, 100 MiB by default. The cap is enforced on the running byte total, not on the `content-length` header, because that header is attacker-controlled and may be absent or understated. Parsing stops at `max_pdf_pages`, 2000 by default, in both the single and batch paths. Untrusted request bodies have both caps clamped, so a client cannot raise its own limits back to unbounded.

The Docker config also ships a non-zero `limits.wall_clock_s` of 300 seconds. It was `0`, meaning no per-crawl deadline at all.

### XSS via unescaped PDF text in cleaned_html

**GHSA-7g3g-vhm6-79f3, CWE-79, medium.** Credit: Nguyen Tran Thanh Lam ([c240030](https://github.com/c240030)).

`clean_pdf_text_to_html()` escapes every sink it writes to except one: paragraph text. The `html.escape()` call on that path had been commented out. Markup embedded in a PDF therefore survived verbatim into `cleaned_html` and executed wherever the result was rendered.

The escape is restored.

### DOM-based XSS in the Playground leading to API token theft

**GHSA-m446-hp3q-qfxp, CWE-79, high.** Credit: [e1codes](https://github.com/e1codes).

The Playground result viewer reset syntax highlighting with:

```js
const text = element.textContent;
element.innerHTML = text;
```

That round trip re-parses the text as live HTML. The text is crawl output, so it is whatever the crawled page contained. Script in a crawled page could therefore run in the operator's Playground session and read the API token held there.

The round trip is removed. highlight.js renders from `textContent` and emits escaped markup on its own, so it was never needed.

## Tests

- `tests/unit/test_pdf_download_limits.py`, 22 tests: per-hop destination validation, DNS rebinding, redirect bounds, byte and page caps, untrusted-body clamping, and temp-file cleanup on abort.
- `tests/unit/test_pdf_html_escaping.py`, 7 tests: escaping of PDF paragraph text in `cleaned_html`.
- `deploy/docker/tests/test_security_pdf_image_write.py`, 6 tests: rejection of image-write fields from untrusted bodies.

## Breaking changes

None.

Two defaults changed, which is worth knowing if you process large PDFs in a self-hosted deployment:

- `PDFContentScrapingStrategy` now caps downloads at 100 MiB and parsing at 2000 pages. Raise them with `max_pdf_bytes` and `max_pdf_pages` when you call it from the SDK. Requests arriving over the Docker API cannot raise them past those caps.
- `limits.wall_clock_s` in `deploy/docker/config.yml` is now `300` instead of `0`. Set it back to `0` if you deliberately want no per-crawl deadline.

## Upgrade

```bash
pip install -U crawl4ai
crawl4ai-doctor  # verify installation
```

Docker users: pull the latest image once the Docker release workflow finishes.

```bash
docker pull unclecode/crawl4ai:0.9.3
```

## Acknowledgments

Thank you to Zhixi "Jace" Sun, Nguyen Tran Thanh Lam ([c240030](https://github.com/c240030)), and [e1codes](https://github.com/e1codes) for reporting these issues privately and giving us time to fix them before disclosure. All reporters are listed in [SECURITY-CREDITS.md](https://github.com/unclecode/crawl4ai/blob/main/SECURITY-CREDITS.md).

If you find a security issue in Crawl4AI, please report it privately. See [SECURITY.md](https://github.com/unclecode/crawl4ai/blob/main/SECURITY.md).

## Support & Resources

- [Documentation](https://docs.crawl4ai.com)
- [GitHub Issues](https://github.com/unclecode/crawl4ai/issues)
- [Discord Community](https://discord.gg/crawl4ai)
