# Public release manifest

This file defines the source-repository boundary. It does not claim that a release tag, package upload, deployment, search ranking, or AI citation exists.

## Repository identity

- Repository: `everyinfra/everyinfra-docs-crawler`
- Suggested description: `Bounded, source-linked documentation crawler for authorized websites. Robots-first Scrapy workflow with JSON and CSV evidence.`
- Suggested topics: `web-crawler`, `documentation`, `scrapy`, `python`, `web-scraping`, `robots-txt`, `source-provenance`, `data-export`, `reproducible-builds`, `security-boundaries`
- Website: `https://everyinfra.com`
- Package import: `everyinfra_docs`
- CLI: `everyinfra-docs`
- Original-code license: MIT

The repository name, description, topics, website, package identity, and opening definition use the same factual vocabulary. This supports discovery and entity consistency; it does not guarantee indexing, ranking, traffic, or AI citations.

## Published source boundary

```text
.github/workflows/ci.yml
.gitignore
LICENSE
PUBLIC_RELEASE.md
README.md
SECURITY.md
THIRD_PARTY.md
VALIDATION.md
build-constraints.txt
build-requirements.in
pyproject.toml
uv.lock
examples/fixture_site.py
scripts/demo.py
scripts/dependency_inventory.py
scripts/resource_probe.py
scripts/verify_wheel.py
src/everyinfra_docs/__init__.py
src/everyinfra_docs/cli.py
src/everyinfra_docs/crawler.py
src/everyinfra_docs/policy.py
tests/test_crawler.py
tests/test_dependency_inventory.py
third_party/pydispatcher-LICENSE.txt
third_party/scrapy-LICENSE.txt
```

The list contains source, reproducible dependency constraints, synthetic fixtures, tests, safety documentation, attribution, and license evidence. It excludes private evidence locations and host-specific instructions.

## Files excluded from publication

- `.venv/`, `__pycache__/`, `*.pyc`, `outputs/`, `dist/`, `.DS_Store`
- `CLAUDE.md` and its `AGENTS.md` symlink: local execution instructions, not product documentation
- `docs/验收记录.md` and dated internal reports: contain local evidence paths and operational history
- Downloads evidence, local install environments, generated crawl results, credentials, cookies, customer data, and account state

Exclusion does not authorize deletion. These files remain local evidence or reproducible build output.

## Publication gates

- [x] Original-code license selected and declared using SPDX `MIT`.
- [x] Upstream framework and dependency ownership stated without self-development claims.
- [x] Runtime and isolated-build dependency locks exist; installed environment passed dependency consistency checks.
- [x] Local behavior, bounded-resource samples, duplicate wheel build, RECORD, and isolated installation checks have evidence.
- [x] Rebuilt twice after the final source change: byte-identical wheel, exact source payload, `License-Expression: MIT`, `License-File: LICENSE`, and matching license bytes.
- [x] Prepared an allowlist-only public-tree copy; membership, regular-file type, local Markdown links, absolute local paths and private-key blocks passed targeted checks. `gitleaks` is not installed, so this is not a universal secret scan.
- [x] Ran the 25-test suite from the copied public tree with imports proven to resolve from that copy; all passed.
- [ ] Obtain Linux CI evidence; a commit-SHA-pinned Ubuntu/macOS workflow is prepared but has not run. The local Docker CLI could not reach its daemon, so no container result is claimed.
- [x] Refreshed 41 exact PyPI name/version queries on 2026-09-05; all responses returned without pagination and `PYSEC-2017-83` remains visible for Scrapy 2.18.0.
- [x] Review the exact repository identity and 25-file source boundary before the initial public push.

The initial source publication does not create a GitHub Release, upload a package, deploy a service, change another account, or send email.
