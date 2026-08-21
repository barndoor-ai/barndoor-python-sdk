# Security Policy

<img align="right" src=".github/rayna.png" width="100">

Thank you for helping keep Barndoor and its customers secure, one patch at a time!

## Reporting Security Issues

If you believe you have discovered a bug, defect, flaw or vulnerability in this project, please,

- If it is not sensitive in nature:
    - Open an issue/PR in the relevant repository

- If you believe it is sensitive in nature:
    - Submit your findings to our [Vulnerability Disclosure Program](https://docs.google.com/forms/d/e/1FAIpQLScKkUDCkghzOyg7cMBKcJYewTcOvJkY9G0KCaL5sREmEow8Vw/viewform?usp=header)

--,  with as much information as possible.

## Known Issues

### CVE-2026-69247 — cryptography Bleichenbacher oracle in PKCS#7 decryption (remediated)

- **Package:** `cryptography` (affected `>= 44.0.0, < 50.0.0`), see
  [NVD](https://nvd.nist.gov/vuln/detail/CVE-2026-69247). CVSS 4.0 **8.2**
  (HIGH). CWE-208 (Observable Timing Discrepancy).
- **Status:** Fixed in `cryptography >= 50.0.0`. This project now pins
  `cryptography>=50.0.0` via `[tool.uv] constraint-dependencies`.
- **Exposure in this SDK:** `cryptography` is a transitive dependency pulled in
  via `PyJWT[crypto]`, which is a direct runtime dependency of the published
  `barndoor` package. However, the vulnerable PKCS#7 decryption functions
  (`pkcs7_decrypt_der`, `pkcs7_decrypt_pem`, `pkcs7_decrypt_smime`) are never
  called by this SDK — the SDK uses `cryptography` only for JWT signature
  verification via PyJWT.
- **Remediation:** constraint `cryptography>=50.0.0` added to `pyproject.toml`;
  lock file updated. Tracked in BCP-3799.

### CVE-2026-69244 — aiohttp out-of-bounds heap read in C HTTP response parser (remediated)

- **Package:** `aiohttp` (affected `< 3.14.3`), see
  [NVD](https://nvd.nist.gov/vuln/detail/CVE-2026-69244). CVSS 4.0 **7.1**
  (HIGH). CWE-125 (Out-of-bounds Read).
- **Status:** Fixed in `aiohttp >= 3.14.3`. This project now pins
  `aiohttp>=3.14.3` via `[tool.uv] constraint-dependencies`.
- **Exposure in this SDK:** `aiohttp` is a transitive dependency pulled in via
  `crewai` and `langchain` dependencies, which appear only under the optional
  `examples` extra and the `dev` dependency group. It is not a runtime
  dependency of the published `barndoor` package.
- **Remediation:** constraint `aiohttp>=3.14.3` added to `pyproject.toml`;
  lock file updated. Tracked in BCP-3799.

### CVE-2026-54058 et al. — pillow memory-safety, decompression-bomb and DoS issues (remediated)

- **Package:** `pillow` (affected `< 12.3.0`). Covers CVE-2026-54058,
  CVE-2026-54059, CVE-2026-54060, CVE-2026-55379, CVE-2026-55380,
  CVE-2026-55798, CVE-2026-59197, CVE-2026-59198, CVE-2026-59199,
  CVE-2026-59200, CVE-2026-59203, CVE-2026-59204 and CVE-2026-59205 — a mix of
  heap out-of-bounds reads/writes (`Image.paste()`/`Image.crop()`,
  `ImageCmsTransform.apply()`, `ImageFilter.RankFilter`, McIdas AREA mmap
  path), missing `_decompression_bomb_check()` calls in the BDF/PCF/GD font and
  image loaders, OS command injection in `WindowsViewer.get_command()`, and
  several parser DoS paths.
- **Status:** All fixed in `pillow >= 12.3.0`. This project now pins
  `pillow>=12.3.0` via `[tool.uv] constraint-dependencies`; the lock resolves
  to `12.3.0`.
- **Exposure in this SDK:** `pillow` is a transitive dependency, reached via
  `llama-index-core` and via `pdfplumber` -> `crewai`, which appear only under
  the optional `examples` extra and the `dev` dependency group. It is not a
  runtime dependency of the published `barndoor` package.
- **Remediation:** constraint `pillow>=12.3.0` added to `pyproject.toml`; lock
  file updated `12.2.0` -> `12.3.0`. Tracked in BCP-3713.

### CVE-2026-12061 et al. — nltk path traversal, ReDoS and SSRF bypass (remediated)

- **Package:** `nltk` (affected `<= 3.9.4`). Covers CVE-2026-12061 (ReDoS in
  the `ReviewsCorpusReader` FEATURES regex), CVE-2026-12072 and CVE-2026-12074
  (path traversal in `NKJPCorpusReader` and `FramenetCorpusReader.frame()`
  allowing arbitrary local file read), CVE-2026-12075 (DNS-rebinding SSRF
  filter bypass in `nltk.pathsec.urlopen`), and CVE-2026-54293 /
  CVE-2026-12243 (URL-encoded path traversal in `nltk.data.load()`, the latter
  being an incomplete fix for the former).
- **Status:** All fixed in `nltk >= 3.10.0` — there is no fixed release on the
  `3.9.x` line. This project now pins `nltk>=3.10.0` via
  `[tool.uv] constraint-dependencies`; the lock resolves to `3.10.3`.
- **Exposure in this SDK:** `nltk` is a transitive dependency pulled in via
  `llama-index` and `llama-index-core` under the optional `examples` extra. It
  is not a runtime dependency of the published `barndoor` package.
- **Remediation:** constraint `nltk>=3.10.0` added to `pyproject.toml`; lock
  file updated `3.9.4` -> `3.10.3`. Tracked in BCP-3713.

### CVE-2026-59884 et al. — pyasn1 ASN.1 parsing vulnerabilities (remediated)

- **Package:** `pyasn1` (affected `< 0.6.4`). Covers CVE-2026-59884 (integer
  overflow in tag decoding), CVE-2026-59885 (unbounded memory allocation via
  crafted indefinite-length encodings), and CVE-2026-59886 (stack exhaustion
  through deeply nested constructed types).
- **Status:** All fixed in `pyasn1 >= 0.6.4`. This project pins `pyasn1>=0.6.4`
  via `[tool.uv] constraint-dependencies` as a defensive measure.
- **Exposure in this SDK:** `pyasn1` previously reached this project transitively
  via `cryptography` (pulled in by `PyJWT[crypto]`) but is **no longer in the
  resolved dependency tree** as of the current lock file. The constraint is
  retained so that if a future dependency change reintroduces `pyasn1`, it will
  resolve to a safe version.
- **Remediation:** constraint `pyasn1>=0.6.4` added to `pyproject.toml`. No lock
  file change required (package not in tree). Tracked in BCP-3713.

### GHSA-xf7x-x43h-rpqh — json-repair circular `$ref` unbounded CPU DoS (remediated)

- **Package:** `json-repair` (affected `< 0.60.1`), see
  [GHSA-xf7x-x43h-rpqh](https://github.com/advisories/GHSA-xf7x-x43h-rpqh).
- **Status:** Fixed in `json-repair >= 0.60.1`. This project now pins
  `json-repair>=0.60.1` via `[tool.uv] constraint-dependencies`; the lock
  resolves to `0.60.1`.
- **Exposure in this SDK:** `json-repair` is a transitive dependency pulled in
  via `crewai`, which appears only under the optional `examples` extra and the
  `dev` dependency group. It is not a runtime dependency of the published
  `barndoor` package.
- **Remediation:** constraint `json-repair>=0.60.1` added to `pyproject.toml`;
  lock file updated to `0.60.1`.

### CVE-2026-52870 — MCP experimental tasks feature lacks session ownership check (remediated)

- **Package:** `mcp` (affected `< 1.27.2`, CVSS 7.6), see
  [NVD](https://nvd.nist.gov/vuln/detail/CVE-2026-52870).
- **Status:** Fixed in `mcp >= 1.27.2`. This project now pins `mcp>=1.28.1` via
  `[tool.uv] constraint-dependencies` (covers this CVE and two others below);
  the lock resolves to `1.28.1`.
- **Exposure in this SDK:** `mcp` is a transitive dependency pulled in via
  `crewai`, `langchain-mcp-adapters`, and `llama-index-tools-mcp`, all under the
  optional `examples` extra and/or the `dev` dependency group. It is not a
  runtime dependency of the published `barndoor` package.
- **Remediation:** constraint `mcp>=1.28.1` added to `pyproject.toml`; lock file
  updated to `1.28.1`.

### CVE-2026-52869 — MCP SSE/Streamable HTTP session hijack via ID-only lookup (remediated)

- **Package:** `mcp` (affected `< 1.27.2`, CVSS 7.1), see
  [NVD](https://nvd.nist.gov/vuln/detail/CVE-2026-52869).
- **Status:** Fixed in `mcp >= 1.27.2`. Covered by the `mcp>=1.28.1` constraint
  above; the lock resolves to `1.28.1`.
- **Exposure in this SDK:** same as CVE-2026-52870 — transitive via examples/dev
  only.
- **Remediation:** see CVE-2026-52870 above.

### CVE-2026-59950 — MCP deprecated WebSocket transport lacks Host/Origin validation (remediated)

- **Package:** `mcp` (affected `< 1.28.1`), see
  [NVD](https://nvd.nist.gov/vuln/detail/CVE-2026-59950).
- **Status:** Fixed in `mcp >= 1.28.1`. Covered by the `mcp>=1.28.1` constraint
  above; the lock resolves to `1.28.1`.
- **Exposure in this SDK:** same as CVE-2026-52870 — transitive via examples/dev
  only.
- **Remediation:** see CVE-2026-52870 above.

### CVE-2026-28684 — python-dotenv environment variable injection (remediated)

- **Package:** `python-dotenv` (affected `< 1.2.2`), see [NVD](https://nvd.nist.gov/vuln/detail/CVE-2026-28684).
- **Status:** Fixed in `python-dotenv >= 1.2.2`. This project now requires
  `python-dotenv>=1.2.2` in `[project] dependencies`; the lock resolves to `1.2.2`.
- **Exposure in this SDK:** `python-dotenv` is a direct runtime dependency used
  to load environment variables (API keys, configuration) from `.env` files.
- **Remediation:** lower bound bumped from `>=1.0.0` to `>=1.2.2` in
  `pyproject.toml`; lock file updated to `1.2.2`.

### CVE-2026-22701 — filelock path traversal / symlink attack (remediated)

- **Package:** `filelock` (affected `< 3.20.3`), see [NVD](https://nvd.nist.gov/vuln/detail/CVE-2026-22701).
- **Status:** Fixed in `filelock >= 3.20.3`. This project now pins
  `filelock>=3.20.3` via `[tool.uv] constraint-dependencies`; the lock resolves
  to `3.29.4`.
- **Exposure in this SDK:** `filelock` is a transitive dependency pulled in via
  `huggingface-hub` and `virtualenv`, both of which appear only under the
  optional `examples` extra and the `dev` dependency group. It is not a runtime
  dependency of the published `barndoor` package.
- **Remediation:** constraint `filelock>=3.20.3` added to `pyproject.toml`;
  lock file updated to `3.29.4`.

### CVE-2026-25087 — pyarrow arbitrary code execution via IPC (remediated)

- **Package:** `pyarrow` (affected `>= 15.0.0, < 23.0.1`), see [NVD](https://nvd.nist.gov/vuln/detail/CVE-2026-25087).
- **Status:** Fixed in `pyarrow >= 23.0.1`. This project now pins
  `pyarrow>=23.0.1` via `[tool.uv] constraint-dependencies`; the lock resolves
  to `24.0.0`.
- **Exposure in this SDK:** `pyarrow` is a transitive dependency pulled in via
  `llama-index` under the optional `examples` extra. It is not a runtime
  dependency of the published `barndoor` package.
- **Remediation:** constraint `pyarrow>=23.0.1` added to `pyproject.toml`;
  lock file updated to `24.0.0`. Closes dependabot PR #92.

### CVE-2026-59890 — setuptools MANIFEST.in Unicode normalization bypass (remediated)

- **Package:** `setuptools` (affected `< 83.0.0`), see
  [NVD](https://nvd.nist.gov/vuln/detail/CVE-2026-59890),
  [GHSA-h35f-9h28-mq5c](https://github.com/advisories/GHSA-h35f-9h28-mq5c).
  Severity: MEDIUM.
- **Status:** Fixed in `setuptools >= 83.0.0`. This project now pins
  `setuptools>=83.0.0` via `[tool.uv] constraint-dependencies`.
- **Exposure in this SDK:** `setuptools` is a build-time dependency, referenced
  under `[tool.setuptools]` for package discovery configuration. The MANIFEST.in
  normalization bypass could cause excluded non-ASCII-named files to leak into
  source distributions. This SDK does not rely on MANIFEST.in exclusion of
  non-ASCII filenames, so the risk is low.
- **Remediation:** constraint `setuptools>=83.0.0` added to `pyproject.toml`;
  lock file updated `82.0.1` -> `83.0.0`. Tracked in BCP-3802.

### CVE-2026-71554 — h2 duplicate Host header smuggling (remediated)

- **Package:** `h2` (affected `<= 4.4.0`), see
  [NVD](https://nvd.nist.gov/vuln/detail/CVE-2026-71554). Severity: MODERATE.
- **Status:** Fixed in `h2 >= 4.4.1`. This project now pins `h2>=4.4.1` via
  `[tool.uv] constraint-dependencies`.
- **Exposure in this SDK:** `h2` is a transitive runtime dependency pulled in
  via `httpx[http2]`, which is a direct dependency of the published `barndoor`
  package. The vulnerability allows HTTP request smuggling via duplicate Host
  headers in HTTP/2 requests. While the SDK uses `httpx` for API communication,
  exploitation requires a malicious intermediary proxy.
- **Remediation:** constraint `h2>=4.4.1` added to `pyproject.toml`; lock file
  updated `4.3.0` -> `4.4.1`. Tracked in BCP-3802.

### CVE-2026-45829 — ChromaDB "ChromaToast" pre-auth RCE (transitive, not exploitable here)

- **Package:** `chromadb` (affected `>= 1.0.0, <= 1.5.9`), CVSS v4.0 10.0.
- **Status:** No fixed release exists upstream as of 2026-06-07 — the latest
  published version (`1.5.9`) is still vulnerable ([chroma-core/chroma#6717](https://github.com/chroma-core/chroma/issues/6717),
  [NVD](https://nvd.nist.gov/vuln/detail/CVE-2026-45829)).
- **Exposure in this SDK:** `chromadb` is **not** a runtime dependency of the
  `barndoor` package. It is pulled in transitively by `crewai`, which appears
  only under the optional `examples` extra and the `dev` dependency group.
- **Why it is not exploitable here:** the vulnerability is reachable only when
  running ChromaDB's Python FastAPI **server**
  (`chromadb.server.fastapi.FastAPI`). This project never starts that server;
  `crewai` uses `chromadb` purely as an embedded client. The published SDK
  ships no `chromadb` attack surface.
- **Remediation plan:** a forward-looking constraint is staged (commented out)
  in `pyproject.toml` under `[tool.uv] constraint-dependencies` and will be
  enabled as soon as a patched `chromadb` (`> 1.5.9`) is published.
