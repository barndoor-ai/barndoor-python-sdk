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
