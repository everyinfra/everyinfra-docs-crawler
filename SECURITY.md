# Security policy

## Supported scope

This project is a local, single-operator prototype for bounded collection from documentation websites the operator is authorized to access. The current tested environment is Python 3.12 on macOS. No released version or production support window exists yet.

Do not expose the CLI as an unrestricted URL-fetching or multi-tenant network service. Exact-origin admission, literal private-IP rejection, request budgets, response-size limits, and robots checks reduce accidental scope expansion; they do not provide DNS rebinding protection, complete SSRF isolation, operating-system sandboxing, or unlimited resource safety.

## Report a vulnerability

Report security issues privately to `sales@everyinfra.com`. Include the affected source version, reproduction steps using a synthetic or otherwise authorized target, observed impact, and any suggested mitigation. Do not include third-party credentials, personal data, destructive payloads, or data obtained without authorization.

Please do not open a public issue for an unpatched vulnerability. There is no bounty or response-time commitment unless separately agreed in writing.

## Safe testing

- Use loopback fixtures or systems you own or are explicitly authorized to test.
- Do not test login bypasses, paywalls, CAPTCHA solving, credential reuse, destructive requests, denial of service, or access-control evasion through this project.
- Keep dependency advisories visible until their version range and reachability have been reviewed; do not suppress a finding merely to make a scan green.
- Treat collected text and source URLs as potentially sensitive and minimize retention and access.
