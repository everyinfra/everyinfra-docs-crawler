# Validation and evidence boundaries

This page separates implementation, local evidence, and claims that have not yet been verified. Commands use only synthetic loopback fixtures unless an operator deliberately supplies an authorized URL.

## Current local evidence

Local evidence was collected on Python 3.12.11 and macOS arm64 with Scrapy 2.18.0. The initial public CI run also completed on Python 3.12 for Ubuntu and macOS:

- 25 unit and subprocess integration tests passed in one run. They cover exact-origin admission, URL and budget validation, robots behavior, redirects, error classification, output non-overwrite, CSV formula safety, response-size enforcement, and rejection of undecoded content encodings.
- 22 resource scenarios passed in two batches. They cover supported compression paths and 4 MiB limit failures, malformed and unsupported encodings, 10,000 discovered links with a 25-candidate cap, a 40,000-node synthetic DOM, 300 sequential pages, and 1,000 paced sequential pages.
- The 1,000-page fixture made 1,001 HTTP requests in 51.966 seconds. The crawler child used 4.175 CPU seconds and reached 75.5 MiB peak RSS. Across both batches the highest observed child RSS was 79.016 MiB.
- Two final hash-constrained wheel builds were byte-identical: SHA-256 `8e024e3f15149ab2d282efcc312957efb410aae01595eb6fbd6de48d058d0b14`. All nine members, RECORD hashes, four source files, MIT license bytes, `License-Expression`, and `License-File` metadata passed the project verifier.
- The final licensed wheel was reinstalled into an isolated environment and imported from `site-packages` under Python isolated mode. Its version, MIT expression, license-file field, and Scrapy-dependent crawler import passed. The same source bytes passed the 25-test public-tree run.
- Runtime and build dependency inventories, CycloneDX 1.6 component lists, package license files, and an OSV query snapshot were generated. The query was refreshed after licensing for 41 exact package versions; all responses returned without pagination, and one Scrapy advisory remains visible and is not suppressed.

These observations are evidence for the named samples, not performance benchmarks, a service-level objective, proof of memory-leak absence, or a production security certification.

## Reproduce the core checks

```bash
uv sync --locked --python 3.12
uv run --locked python -m unittest discover -s tests -v
uv run --locked python scripts/demo.py --output outputs/local-demo
uv run --locked python scripts/resource_probe.py --output outputs/resource-probe
uv pip check
```

Every output directory must be new. Resource probes enforce test-process guards, but the production CLI does not inherit those process limits.

## Not yet verified

- Windows installation and behavior
- Long-running or concurrent production workloads
- DNS rebinding defense or complete SSRF isolation
- JavaScript-rendered pages, authenticated content, PDFs, and media
- General compatibility across external documentation platforms
- Search indexing, ranking, AI mention, citation, traffic, or conversion outcomes
- A package-registry upload or deployment; GitHub Release state is verified separately

This repository uses the reviewed 25-file allowlist-only source boundary. The copied publication candidate passed the same 25-test suite before the initial push. [GitHub Actions run 33939102052](https://github.com/everyinfra/everyinfra-docs-crawler/actions/runs/33939102052) then passed on Ubuntu and macOS; Ubuntu completed the bounded resource fixtures as well. The workflow pins third-party actions to exact Node 24 commits and pins uv 0.11.29. Windows, longer-duration production behavior, and the other limits above remain unverified.

See [SECURITY.md](SECURITY.md) for deployment and reporting boundaries and [THIRD_PARTY.md](THIRD_PARTY.md) for dependency ownership and licensing limits.
