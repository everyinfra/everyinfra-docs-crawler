# EveryInfra Docs Crawler: bounded, source-linked documentation crawling

基于 Scrapy 的有界文档采集原型：从一个明确授权的站点读取 HTML，输出带来源链接的 JSON 记录和 CSV 文档数据。

EveryInfra Docs Crawler is a robots-first, budget-aware web crawler for documentation websites you are authorized to access. It exports source-linked JSON and CSV evidence while enforcing an exact origin, page and request budgets, candidate limits, response-size limits, and fail-closed robots checks.

**当前是本地工程原型，不是已上架的 EveryInfra 服务、官方 Skill 或公开发行包。** 下载、HTML 解析等框架能力来自 [Scrapy](https://scrapy.org/)；EveryInfra 新增的是范围与预算控制、robots 前置检查、字段归一、错误记录、导出和本机行为测试。第三方归属见 [THIRD_PARTY.md](THIRD_PARTY.md)，原创代码采用 [MIT License](LICENSE)。

## What it does

- Collects HTML documents from one exact authorized origin using read-only GET requests.
- Checks `robots.txt` before crawling and stops when the rules cannot be safely established.
- Emits source URL, discovery URL, timestamp, status, depth, extracted text, truncation state, and a content SHA-256.
- Separates successful documents from redirects, HTTP errors, blocked paths, unsupported content, and download failures.
- Runs without browser cookies, authentication headers, JavaScript execution, automatic retries, redirects, proxies, or HTTP cache.

It is not a login scraper, anti-bot bypass, general SSRF sandbox, media downloader, or production multi-tenant crawling service.

## 在本机运行演示

需要 Python 3.12 和 uv。在本项目目录执行：

```bash
uv sync --locked --python 3.12
uv run --locked python scripts/demo.py --output outputs/local-demo
```

演示只创建一个动态端口的 `127.0.0.1` HTTP 样本站，结束后关闭。样本全部合成，包含分页、重复链接、缺标题、robots 禁止、503 和非 HTML 响应；不是客户数据，也不代表任何真实平台接口可用。

输出目录必须是新路径。重复演示请换一个目录名，不覆盖旧证据：

- `crawl/report.json`：全部成功、跳转、拒绝和失败记录，以及预算、来源、停止原因。
- `crawl/documents.csv`：仅成功解析的 HTML 文档；对可能被表格软件解释为公式的字符串添加文本前缀，JSON 保留原始值。
- `demo-evidence.json`：CLI 退出码和样本站真实收到的请求。演示故意包含错误，所以 CLI 返回 `partial` / 2；演示脚本验到预期 partial 后自身返回 0。

## 采集你有权访问的站点

以下为命令模板。将 `docs.example.com` 换成你实际拥有授权的站点，并在本项目目录运行；已执行的本机样本见[验证摘要](VALIDATION.md)，不代表其他站点兼容性：

```bash
uv run --locked everyinfra-docs https://docs.example.com/ \
  --allow-origin https://docs.example.com \
  --acknowledge-authorized \
  --max-pages 20 --max-requests 25 --output outputs/authorized-run
```

授权声明参数只是操作者确认，不会赋予站点访问权。工具不登录、不读浏览器 Cookie、不发送认证凭据，不自动处理验证码，不绕过付费或私有内容控制。请勿输入带秘密值的 URL；已拦截 URL 用户名/密码和部分常见敏感查询键，不能把这一检查当成通用脱敏器。

精确 origin 包含协议、主机和端口。不自动允许子域或 HTTP/HTTPS 切换。页面跳转逐个重新核范围；允许范围内的跳转会消耗请求预算。它不是 SSRF/DNS 安全沙箱：没有 DNS 重绑定防护，不能直接部署为接受陌生用户 URL 的在线服务。私网 IP 字面量拒绝；loopback 仅可用显式 `--allow-loopback` 开启本机测试。

## 预算、robots 与停止条件

| 参数 | 默认 | 含义 |
| --- | --- | --- |
| `--max-pages` | 20 | 文档 HTTP 尝试上限，包含重定向与失败，不含 robots 请求 |
| `--max-requests` | 25 | 总 HTTP 尝试上限，包含 robots；不是成功响应计数 |
| `--max-candidates` | 500 | 去重后纳入队列的 URL 上限；超限会标记 partial |
| `--max-body-bytes` | 2000000 | 单响应体大小限制；不保留原始 HTML/媒体文件 |
| `--max-text-chars` | 5000 | 单文档输出文本长度；截断有独立标记，摘要哈希依据截断前提取文本 |
| `--delay` | 0.5 | 请求间隔秒数；若支持的 robots Crawl-delay 更大则采用更大值 |
| `--timeout` | 10 | 单请求超时秒数 |

先请求同 origin 的 `/robots.txt`，再开始文档采集。200 类非 HTML 文本响应使用 Python 标准库 `RobotFileParser` 解析；404 记为规则缺失；HTML 登录页、其他 HTTP 状态、跳转、网络或大小错误均停止，不静默放行。支持解析器识别的 Crawl-delay；若大于60秒则停止。不是 robots 全语法或所有站点策略的兼容承诺。

单并发，关闭自动重试、自动跳转、Cookie、环境代理、HTTP缓存和 Telnet 调试端口。HTML 会正常作为响应读取，但仅导出提取文本与元数据；遇到非 HTML 类型会分类，识别前仍可能读取到受大小限制的响应体，不宣称零媒体网络流量。

解压后仍有非空 `Content-Encoding` 的响应按 `download_error` 拒绝，包括 robots；不将未知编码的字节当成已验证正文或规则。当前环境已实测 gzip/x-gzip、deflate（含 raw）、Brotli、Zstandard 及一组叠加编码的正常和超限样本，不承诺所有编码排列或损坏数据兼容性。

## 数据与退出码

成功文档包含 `url`、`discovered_from`、`fetched_at`（UTC）、`http_status`、`depth`、`title`、`title_missing`、`text`、`text_truncated` 和 `content_sha256`。没有标题就保留空值，不生成猜测标题。通过 URL 去重并移除 fragment；不按正文哈希合并不同来源，也不擅自重排查询参数。

报告中的 `kind` 区分 `document`、`redirect`、`http_error`、`unsupported_content`、`blocked_robots`、`robots_error`、`download_error`。失败记录不混入 CSV 成功行。

- **0 / `complete_within_scope`**：已穷尽纳入范围的队列且没有上述失败；不代表完整网站、隐藏页面或渲染后内容已覆盖。文本截断仍需查看行级标记。
- **2 / `partial`**：已有文档，但存在预算截停、拒绝、非 HTML 或失败等不完整情况。
- **1 / `failed`**：未获得文档或爬虫内部出错。
- 参数错误也返回非零（argparse 为2），此时不会创建采集报告；脚本应结合报告是否存在及 `status` 判断。

不执行页面 JavaScript；不支持自动登录、PDF解析、图片/视频导出、跨站递归、增量持久化任务或生产调度。来源页文本可能包含个人信息，使用者仍需按授权范围最小化收集和保管输出。

## 验证与开发

```bash
uv run --locked python -m unittest discover -s tests -v
uv run --locked python scripts/dependency_inventory.py --output outputs/dependency-inventory.json
```

测试包含 URL/数值策略检查，以及启动真实本机服务器后通过子进程执行 CLI 的行为检查；不是只 mock Scrapy 返回。依赖清单只记录当前环境元数据、版本和许可文件哈希，不等于完整许可证审计或漏洞扫描。实际执行范围见[验证摘要](VALIDATION.md)。

需要发布前的组件和许可证据包时，使用全新输出路径：

```bash
uv run --locked python scripts/dependency_inventory.py \
  --output outputs/runtime-inventory.json --bundle-dir outputs/runtime-evidence
```

证据包包含 `bom.cdx.json`（CycloneDX 1.6）和逐字保留的许可证/NOTICE/AUTHORS文件；清单记录它们的SHA256。只报告实际安装的Python包，不虚构依赖边、原生库组件或完整性；没有明确SPDX表达式时不会凭BSD等笼统分类猜一个。当前PyDispatcher安装包缺失许可文件的情况仍如实报告，同版本源码包补充证据见[第三方说明](THIRD_PARTY.md)。

构建环境单独恢复并核验，不向运行时添加构建包：

```bash
uv venv --python 3.12 outputs/build-audit-env
uv pip sync --python outputs/build-audit-env/bin/python --require-hashes build-constraints.txt
outputs/build-audit-env/bin/python scripts/dependency_inventory.py \
  --build-constraints build-constraints.txt \
  --output outputs/build-inventory.json --bundle-dir outputs/build-evidence
```

以上构建核验命令已在macOS执行；不是Windows安装验收。运行时与构建清单应分开保存、去重后扫描漏洞，不能因SBOM可解析或许可文件齐全就宣布发布已获准。

本机资源与连续采集验证（仅macOS/Linux接口，实际验收环境为macOS）：

```bash
uv run --locked python scripts/resource_probe.py --output outputs/resource-probe
```

脚本执行22组真实loopback场景，包含7组编码路径的正常/4 MiB超限样本、损坏/未知编码、有无长度声明的超限响应、10,000链接、40,000 DOM节点、300页及带间隔的1,000页采集。每组独立进程记录CPU和峰值RSS，测试护栏为CPU20秒、墙钟90秒、采样RSS512 MiB；超限、缺失度量或行为不符均返回非零。RSS监视不是内核内存隔离，也不是生产CLI的资源上限。可用 `--case sequential-1000-paced` 单独复跑千页样本；输出必须使用新目录。当前实测范围及限制见[验证摘要](VALIDATION.md)。

运行时由 `uv.lock` 锁定；隔离构建的6个组件由 `build-constraints.txt` 固定版本与分发哈希，项目 `tool.uv.build-constraint-dependencies` 同步限制日常 uv 安装的构建版本。构建候选使用：

```bash
uv build --wheel --build-constraints build-constraints.txt --require-hashes --out-dir outputs/release-candidate
```

更新构建依赖时先审阅版本，再用 `uv pip compile build-requirements.in --python-version 3.12 --generate-hashes -o build-constraints.txt` 生成锁定，同步 pyproject.toml 的6项构建约束后运行 `uv lock`。`uv.lock` 本身不覆盖隔离构建环境；不能省略构建哈希参数后仍宣称同等校验。

公开前仍需：完成逐组件许可/安全复核、Linux/Windows验证、公开文案与仓库发布确认。当前不承诺跨平台安装、搜索收录或 AI 引用效果；自有站点小样本不替代长期或跨平台验收。

## Frequently asked questions

### Does this crawler bypass logins, paywalls, or bot protection?

No. It sends unauthenticated GET requests, does not import browser cookies or credentials, and does not solve challenges or bypass access controls.

### Does an allowlisted origin make it safe to expose as a public URL-fetching service?

No. Exact-origin checks limit crawl scope but do not prevent DNS rebinding and are not an SSRF isolation boundary. Keep this tool local or place it behind a separately reviewed network sandbox.

### Does `complete_within_scope` mean an entire website was captured?

No. It means the admitted queue was exhausted within the configured budgets without recorded failures. Hidden pages, JavaScript-rendered content, other origins, and unlinked documents are outside that claim.

## License and attribution

EveryInfra's original code in this repository is available under the [MIT License](LICENSE). Scrapy and every transitive dependency retain their own licenses and copyrights; see [THIRD_PARTY.md](THIRD_PARTY.md). The MIT license does not relicense third-party packages, websites, or collected content.
