# Dependency licence report

Project licence: **MIT** (see `LICENSE`).

This report covers direct dependencies declared in `pyproject.toml` and notable transitive packages observed in the development environment on 2026-10-23. Licence metadata was read from installed package metadata. It is not legal advice.

Reachy does not vendor these packages in its source tree. A normal `pip install` resolves and installs them separately. If you redistribute a wheel, container image, or bundled environment, you are redistributing third-party code and must include the applicable licence texts and notices.

## Direct runtime dependencies

| Package | Declared range | Installed | Licence | Notes |
| :--- | :--- | :--- | :--- | :--- |
| beautifulsoup4 | >=4.12.0 | 4.14.3 | MIT | HTML parsing. |
| certifi | >=2024.0.0 | 2025.8.3 | MPL-2.0 | CA bundle. Unmodified package; source availability obligation applies to MPL files if redistributed. |
| mcp | >=1.0.0 | 2.2.0 | MIT | MCP server. |
| dnspython | >=2.6.0 | 2.8.0 | ISC | MX/A verification. |
| cryptography | >=42.0.0 | 46.0.5 | Apache-2.0 OR BSD-3-Clause | Fernet secret storage. Choose either licence when redistributing. |
| rich | >=13.7.0 | 15.0.0 | MIT | Terminal output. |

## Optional dependencies

| Package | Extra | Installed | Licence | Notes |
| :--- | :--- | :--- | :--- | :--- |
| playwright | browser | 1.60.0 | Apache-2.0 | Browser automation. Playwright downloads Chromium under its own licences; review the browser distribution terms. |
| google-auth | gmail | 2.49.1 | Apache-2.0 | Google authentication. |
| google-auth-oauthlib | gmail | 1.3.0 | Apache-2.0 | Installed-app OAuth flow. |
| google-api-python-client | gmail | 2.198.0 | Apache-2.0 | Gmail API client. |

## Development dependencies

| Package | Installed | Licence |
| :--- | :--- | :--- |
| pytest | 9.1.1 | MIT |
| pytest-cov | 7.1.0 | MIT |
| setuptools | 83.0.0 | MIT |

## Notable transitive packages

| Package | Installed | Licence |
| :--- | :--- | :--- |
| soupsieve | 2.8.3 | MIT |
| cffi | 2.0.0 | MIT |
| pycparser | 3.0 | BSD-3-Clause |
| httplib2 | 0.31.2 | MIT |
| uritemplate | 4.2.0 | BSD-3-Clause OR Apache-2.0 |
| google-auth-httplib2 | 0.4.0 | Apache-2.0 |
| googleapis-common-protos | 1.75.0 | Apache-2.0 |
| protobuf | 6.33.6 | BSD-3-Clause |
| requests | 2.34.2 | Apache-2.0 |
| requests-oauthlib | 2.0.0 | ISC |
| oauthlib | 3.3.1 | BSD-3-Clause |
| urllib3 | 2.5.0 | MIT |
| idna | 3.20 | BSD-3-Clause |
| pydantic | 2.13.4 | MIT |
| starlette | 1.3.1 | BSD-3-Clause |
| anyio | 4.13.0 | MIT |
| httpx | 0.28.1 | BSD-3-Clause |

The full transitive set can change with resolver results. Generate an inventory for the exact artifact you ship:

```bash
python -m pip install -e ".[browser,gmail,dev]"
python -m pip freeze > requirements-lock.txt
python -m pip install pip-licenses
pip-licenses --format=markdown --with-urls
```

Review the generated list before distribution, especially if you bundle dependencies into a container or executable.

## Obligation summary

- **MIT / ISC / BSD:** retain copyright and permission notices; do not use contributor names to endorse your product.
- **Apache-2.0:** retain the licence, include any `NOTICE` file supplied by the package, and state significant modifications. `cryptography` is dual-licensed; either branch is acceptable.
- **MPL-2.0 (certifi):** if you distribute MPL-covered files, make the source available and disclose modifications. Reachy does not modify certifi. MPL is file-level copyleft, not copyleft over Reachy's code.
- **Chromium / Playwright browsers:** Playwright's package licence does not replace the browser binary's own notices. Review the Chromium distribution and any bundled components before redistributing a browser binary.
- **Google APIs / Gmail:** use is governed by Google's API terms and user-data policy in addition to the client library licences.

## Compliance actions for distributors

1. Include `LICENSE` (Reachy MIT) with the distribution.
2. Include the licence texts and notices of all bundled third-party packages.
3. Preserve `NOTICE` files for Apache-2.0 packages where supplied.
4. Do not strip licence headers from vendored code.
5. Publish the exact dependency set used for the artifact.
6. Re-run the inventory when dependencies change.
7. If you modify an MPL-2.0 file, publish the modified source for that file.

Maintainers should update this report when adding or removing a direct dependency or changing an extra.
