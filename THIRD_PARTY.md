# 第三方来源与原创边界

本项目依赖 Scrapy，不是将 Scrapy 改名后宣称为 EveryInfra 全部自研。

## 核心上游

- 原仓：[scrapy/scrapy](https://github.com/scrapy/scrapy)。
- 本机安装版：Scrapy **2.18.0**，来自 [PyPI 版本页](https://pypi.org/project/Scrapy/2.18.0/)；不是上一轮候选预审的开发分支。
- 上游 tag `2.18.0` 的 annotated tag object 为 `7efcc1387a1581e26882208cf45364bc04b77ab1`，指向 commit `2216063c063027d541eafbf5e098557ce732528f`。
- 该版本 PyPI wheel SHA256：`7cd2eaa6fb013247ca259fd4cad75208a2b37cd65fbdd3a6c3fbc75cdf61f3d9`，下载分发哈希纳入 uv.lock。
- 许可声明 BSD-3-Clause，原文保存在 [Scrapy LICENSE](third_party/scrapy-LICENSE.txt)；原作者列于[上游 AUTHORS](https://github.com/scrapy/scrapy/blob/2216063c063027d541eafbf5e098557ce732528f/AUTHORS)。不暗示 Scrapy 或其作者为 EveryInfra 背书。

## 本项目实际新增

`src/everyinfra_docs/` 是本轮新写的适配代码：精确 origin 校验、只读请求和预算控制、显式 robots 预检、来源与错误记录、JSON/CSV 导出。`tests/`、`examples/` 与 `scripts/demo.py` 是本轮新写的测试及合成样本站，没有复制第三方平台数据或原仓测试冒作实测。

通过官方依赖导入 Scrapy，不 vendoring 或改写其源码；本地环境中仍保留其 LICENSE/AUTHORS。Echo于2026-09-05确认原创代码采用MIT，见根目录[LICENSE](LICENSE)；该决定不扩展至Scrapy、传递依赖、目标网站或采集内容。

## 传递依赖与发布限制

运行时解析以 uv.lock 为准。`scripts/dependency_inventory.py` 从当前安装包读取名称、版本、许可证元数据及许可证文件哈希；空值就是未声明，不推断为可任意使用。Python 构建后端及其隔离构建依赖不由此运行时清单完整覆盖；另有 `build-constraints.txt` 锁定6个构建组件的版本和哈希，锁定不等于完成许可审查。

这里没有逐项确认所有再分发义务，也没有完成完整安全、商标或采集内容权利审查。已对36个已安装公开运行时包做 OSV 版本查询，仍有1条来源范围不一致的告警待复核，详见[验证摘要](VALIDATION.md)。禁止仅凭顶层 BSD 声明就把整个环境重新标成单一许可。当前未发布仓库、wheel、容器或安装包；公开前按实际分发文件检查每个组件。

## 2026-09-05 组件证据补齐

- 运行时清单覆盖36个第三方包及本项目，收集44份许可证/NOTICE/AUTHORS原文；隔离构建环境严格按既有哈希约束恢复6个包，收集8份原文，没有新增或升级版本。两个环境的`packaging`重叠，去重为41个第三方包/版本组合，不相加冒称42个不同组件。
- 生成器现按文件名识别许可文档，不把`packaging/licenses/_spdx.py`等实现代码算成许可；缺失声明和文件继续显式记录。清单不覆盖原生库子组件、操作系统、未安装平台变体或完整依赖关系，不等于完整法律/安全审查。
- **PyDispatcher 2.0.7**：安装wheel中没有许可证文件。已从[同版本PyPI源码包](https://files.pythonhosted.org/packages/21/db/030d0700ae90d2f9d52c2f3c1f864881e19cef8cba3b0a08759c8494c19c/PyDispatcher-2.0.7.tar.gz)读取`license.txt`，源码包SHA256=`b777c6ad080dc1bad74a4c29d6a46914fa6701ac70f94b0d66fbcfde62f5be31`，许可证SHA256=`aeec9c40c508ce52e66e3eb087c062d8ecf49622a4abd3af79410506b43b698b`。原文副本见[PyDispatcher LICENSE](third_party/pydispatcher-LICENSE.txt)，逐字比对通过，保留版权、条款与非背书条件；未改第三方安装目录，不能把补充证据说成wheel本身已携带许可。
- **需按分发内容继续审查**：lxml的`LICENSES.txt`除BSD外，还列出ElementTree/PSF、特定测试文件GPL、二进制捆绑库（含iconv的LGPL 2.1）及部分schema资源许可问题；不能把所有lxml文件概括为BSD，也不由该总声明推断当前wheel每项内容已逐一核实。certifi原文指向MPL 2.0；backports.zstd另含Zstandard条款；zope.interface的ZPL要求保留修改/商标边界。不得将整个第三方环境放入单一EveryInfra许可证。
- 本次只补许可证据与预审结论，不自动批准源码仓、原型wheel、完整运行环境或容器的公开分发。逐组件/原生依赖义务及其当前边界详见[验证摘要](VALIDATION.md)。

## 2026-09-05 候选安装包范围核对

修复未知压缩编码后，两次哈希约束构建得到相同wheel，SHA256为`060bb6ccbb39a9ae9aa49b0e98ffc0d2b0630829881487143a8b693bd5f2809f`。逐条核对ZIP与RECORD，只有4个当前原创Python模块和4个dist-info文件；模块与源码字节一致，没有Scrapy、lxml等第三方代码、原生库、环境目录或测试数据。第三方依赖只在Requires-Dist中声明，安装时另按原锁恢复。

这是**当时具体候选wheel的文件范围证据**，不是“第三方许可无需遵守”的结论，更不批准把完整环境打包。该旧候选元数据没有许可字段；Echo随后确认原创代码采用MIT，新候选必须同时含`License-Expression: MIT`、`License-File: LICENSE`及逐字许可文件后才可替代旧候选。公开源码仓还需单独列出文档、锁文件和原始第三方声明等实际文件，不用wheel清单替代源码分发审查。新候选状态见[验证摘要](VALIDATION.md)。

最终MIT候选已按上述要求重建：两份wheel字节相同，SHA256=`8e024e3f15149ab2d282efcc312957efb410aae01595eb6fbd6de48d058d0b14`；9个成员包括原4个原创模块、4个构建元数据文件和`dist-info/licenses/LICENSE`。RECORD、源码及许可字节均通过，隔离环境重装后元数据和Scrapy依赖导入通过。它仍不打包第三方环境，也不表示完整环境的第三方/原生许可义务已经消失。

## 技术依据与文档来源

- [Scrapy downloader middleware](https://docs.scrapy.org/en/latest/topics/downloader-middleware.html)：请求链扩展点；本轮读到的文档版本为2.18.0。
- [Scrapy settings](https://docs.scrapy.org/en/latest/topics/settings.html)：并发、重试、缓存、Cookie、响应大小等设置。
- 本项目严格 robots 前置流程是本轮适配实现，不将 Scrapy 默认 robots 策略描述为同样的失败处理。
