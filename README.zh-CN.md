# searxng-windows

[English](README.md) | 简体中文

这是一套 Windows 原生 SearXNG 安装与维护工具，不需要 Docker。既可以直接在
浏览器中使用，也可以作为本地、兼容 SearXNG 接口的搜索后端，供工具和 AI
Agent 调用。

## 主要功能

- 在 Windows 上原生安装和运行 SearXNG，不依赖 Docker
- 本地监听地址：`http://127.0.0.1:8888`
- 提供可选的 API-first 故障切换网关，支持 Parallel、Tavily、Brave、
  Firecrawl 以及免费 SearXNG 引擎
- 第一家 API 返回有效结果后立即停止；仅在 API 层不可用或无结果时，才使用
  Bing、Sogou、Qwant、Mojeek 免费层
- 使用标准 Python 和虚拟环境
- 支持可选的出站代理
- 提供安装、启动、停止、更新、健康检查和登录自启动脚本
- 自动应用 SearXNG 所需的 Windows 兼容补丁
- API Key、本地状态、日志和生成配置都不会提交到 Git

## 适合谁？

- 想在 Windows 上原生运行 SearXNG、又不想安装 Docker Desktop 的用户
- 需要本地 SearXNG 兼容 HTTP 接口的开发者和 AI Agent 用户
- 希望自行控制配置、日志和代理出口的用户
- 需要 API 串行故障切换、且不希望缓存服务商结果的用户

> SearXNG 和可选 API Pool 是自托管网关，不是离线搜索索引。查询仍会发送给
> 配置的上游搜索引擎或 API 服务商，请勿在搜索词中包含密码、API Key 或其他
> 敏感信息。

## 系统要求

- Windows 10 或 Windows 11
- Python 3.11 或 3.12 x64
- 安装时可以访问互联网
- 不需要 Git；安装器直接下载上游源码 ZIP，并跳过 Windows 无法创建的文件名
- GitHub CI 实测覆盖 Windows Server 2022/2025 × Python 3.11/3.12；Windows 10/11 桌面环境仍可能存在差异

## 快速安装

1. 从最新 GitHub Release 下载下面两个文件，并放在同一目录：
   - `install-searxng-windows.cmd`
   - `install-searxng-windows.ps1`
2. 双击 `install-searxng-windows.cmd`。
3. 打开 `%USERPROFILE%\Apps\searxng-windows`，双击
   `start-searxng.cmd`。
4. 可选：双击 `check-searxng.cmd` 检查服务健康状态，默认不请求外部搜索 API。
5. 打开 `http://127.0.0.1:8888`。

`scripts\` 下的 PowerShell 脚本仍可用于自动化和高级参数。

默认安装目录：

```text
%USERPROFILE%\Apps\searxng-windows
```

bootstrap 安装器默认解析并下载最新 Release，再下载上游 SearXNG。源码 ZIP
解压时会跳过 Windows 无法创建的 Unix 模板文件名，并在确认 `setup.py`、
`requirements.txt` 和 `searx/webapp.py` 完整后才继续创建虚拟环境、安装依赖、
生成本地 `secret_key` 并应用 Windows 补丁。已有的 `config/settings.yml` 和 `config/api-pool.env` 会被保留。

## 客户端接入

普通本地 SearXNG 地址为：

```text
http://127.0.0.1:8888
```

兼容 SearXNG 的客户端可以直接调用标准 JSON 搜索接口，例如：

```text
http://127.0.0.1:8888/search?q=example&format=json
```

API Pool 未启用时，客户端保持使用 `8888`。启用下面的 API Pool 后，需要走
API-first 链路的客户端可改用 `8890`。如果客户端会缓存接口地址，修改后请重启。

## 可选 API Pool

API Pool 会随安装包部署，但**默认关闭**。关闭时不会启动本地 Broker，普通
SearXNG 搜索引擎照常工作。

启用步骤：

1. 编辑 `%USERPROFILE%\Apps\searxng-windows\config\settings.yml`。
2. 把 `api pool` 条目的 `disabled: true` 改为 `disabled: false`。
3. 按需在 `config\api-pool.env` 中填写 API Key。安装器会生成带空白占位符的配置文件；
   **不填写 Key 也能使用免费 SearXNG 搜索回退**：

```dotenv
BRAVE_API_KEY=
FIRECRAWL_API_KEY=
TAVILY_API_KEY=
PARALLEL_API_KEY=
API_POOL_PRIORITY=parallel,tavily,brave,firecrawl
```

4. 将需要使用 API-first 链路的客户端基础地址从 `8888` 改成 `8890`。
5. 重启 SearXNG，以及会缓存接口地址的客户端。

Broker 只在 API Pool 启用时启动，监听 `http://127.0.0.1:8890`，提供兼容
SearXNG 的搜索入口，并按以下顺序执行：

```text
Parallel → Tavily → Brave → Firecrawl → Bing/Sogou/Qwant/Mojeek 免费兜底
```

第一家 API 返回有效结果后立即停止，不会让一次搜索同时消耗所有 API 的额度；
空结果会继续尝试下一家。只有全部 API 都不可用或都没有结果时，网关才会调用
`8888` 上的 Bing、Sogou、Qwant、Mojeek 免费层。即使没有配置付费 API Key，
只要本地免费搜索后端可用，Broker 仍能走免费回退。API Pool 未启用时，
客户端应继续连接 `8888`，直接使用普通 SearXNG。

相对时间筛选支持 `time_range=day|week|month|year`，属于尽力过滤：支持原生
日期条件的引擎按范围搜索，不支持的引擎仍继续搜索（不带日期条件）。
结果可能包含旧网页或缺少发布日期。带日期条件的 Tavily 搜索会尽量返回
发布日期，但不会直接丢弃日期未知的结果。精确日期筛选使用 `date_after`、
`date_before`，格式为 `YYYY-MM-DD`。对于时效性重要的内容，应核对原网页日期。
接口、状态机和故障切换细节见 [`api_pool/README.md`](api_pool/README.md)。

## 代理配置

默认不使用代理。如果出站搜索超时，可以编辑 `config/settings.yml`，启用示例
代理配置：

```yaml
outgoing:
  request_timeout: 10.0
  max_request_timeout: 20.0
  extra_proxy_timeout: 10
  proxies:
    all://:
      - http://127.0.0.1:10808
```

请替换成自己的代理地址。启动时也传入同一个代理，让 API Pool 和相关工具获得
标准代理环境变量：

```powershell
powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\Apps\searxng-windows\scripts\start.ps1" -ProxyUrl "http://127.0.0.1:10808"
```

## 常用操作

日常桌面使用时，直接双击安装目录中的三个文件：

```text
start-searxng.cmd   启动 SearXNG 和已启用的 API Pool
stop-searxng.cmd    停止本地服务
check-searxng.cmd   检查服务健康状态（默认不执行实际搜索）
```

对应的命令行操作如下：

```powershell
$Root = "$env:USERPROFILE\Apps\searxng-windows"

# 启动 SearXNG；API Pool 启用时也会启动 Broker
powershell -ExecutionPolicy Bypass -File "$Root\scripts\start.ps1"

# 停止本地服务
powershell -ExecutionPolicy Bypass -File "$Root\scripts\stop.ps1"

# 检查服务健康状态（如需实际搜索，增加 -LiveSearch 参数）
powershell -ExecutionPolicy Bypass -File "$Root\scripts\check.ps1"

# 更新上游 SearXNG 源码和依赖
powershell -ExecutionPolicy Bypass -File "$Root\scripts\update.ps1"

# 注册 Windows 登录自启动
powershell -ExecutionPolicy Bypass -File "$Root\scripts\register-startup-task.ps1" -Root $Root
```

`update.ps1` 会下载并验证最新的上游 SearXNG 源码 ZIP，跳过 Windows 无法创建的
文件名；只有解压和完整性检查成功后才替换源码，并保留带时间戳的旧源码备份。
要更新本仓库的 Windows 脚本、API Pool 和配置模板，请重新运行最新 Release 中的
安装器；已有本地配置会被保留。

## 从 Git 仓库安装

```powershell
git clone https://github.com/Kerberos255/searxng-windows.git
cd searxng-windows
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1 -Root "$env:USERPROFILE\Apps\searxng-windows"
```

当 `config/settings.yml` 不存在时，安装脚本会自动创建它并生成本地 secret；不需
手工生成。系统 PATH 中没有 `python` 时，可用 `-RuntimePython` 指定完整路径。
需要固定某个版本时，bootstrap 安装器支持传入 `-Ref v0.2.7`。

## 故障排查

**安装完成本身不会生成运行日志。** 首次安装后，先双击 `start-searxng.cmd`。
若启动在创建后台进程前就失败（如安装路径无效、辅助脚本缺失），
日志文件**可能根本不存在**；此时应先查看并保存 CMD 窗口显示的完整错误，
不要把「没有日志」误认为另一项故障。

成功进入后台启动阶段后，日志会写入**安装根目录**（默认
`%USERPROFILE%\Apps\searxng-windows`）：

```text
searxng-run.log          SearXNG 启动器标准输出
searxng-run.err.log      SearXNG 启动器标准错误
broker-run.log          API Pool 启动器标准输出（启用时）
broker-console.err.log  API Pool 启动器标准错误（启用时）
broker-run.err.log      API Pool 诊断警告与错误（启用时）
```

启动正常时，错误日志可能为空文件；未启用 API Pool 时也不会产生它的运行日志。
启动后可用 `check-searxng.cmd` 检查本地健康状态（不调用外部搜索）；
需要实际测试搜索时，可运行 `scripts\check.ps1 -LiveSearch`，这可能消耗 API 额度。

安装目录包含空格、中文等非 ASCII 字符通常可正常使用；但应避免方括号
（`[`、`]`）：Windows PowerShell 5.1 对这类路径的进程日志重定向不可靠，
启动器会在创建后台进程前直接提示错误。

- `8888` 是 SearXNG 端口；`8890` 是可选 API Pool Broker 端口。
- 某个搜索引擎失败时，通常不会阻止其他引擎返回结果。
- 模板默认禁用 DuckDuckGo 系列，因为共享出口或代理环境较容易触发验证码。
- SearXNG 自带的 Brave 引擎抓取公开网页结果，不使用官方 API Key；API Pool 中
  的 Brave provider 才使用官方 Key。

## 仓库边界

本仓库不会包含：

- Python 虚拟环境或 SearXNG 源码副本
- 生成后的 `config/settings.yml` 或真实 API Key
- `config/api-pool.env`、SQLite 状态、日志、PID 或下载文件
- 机器特定的客户端配置

## CI 与 Release

每次 push 和 pull request 都会运行 Windows CI：PowerShell 启动器回归测试、
Python 编译、API Pool 单元测试、公开包防泄漏检查，以及实际 Windows
安装、启动、健康检查、停止、重装保留配置、上游更新测试。

此外，安装矩阵会从 GitHub 下载真正的 CMD/PowerShell 安装器，覆盖
Windows Server 2022/2025 × Python 3.11/3.12。扩展测试还会启动
SearXNG + API Pool 双服务、验证无 Key 时的免费回退、模拟更新失败并
验证回滚，最后确认停止后端口释放。

推送 `v0.2.7` 这类语义化版本标签后，会触发 Release 工作流。
工作流验证该提交属于 `main`，并且**必须先通过从 GitHub 下载安装器、
启动双服务及更新失败回滚的实际验收**，才构建正式 ZIP、安装器及
SHA-256 校验文件并自动发布。

## 许可证

部署脚本、独立 API Pool Broker 和文档使用 MIT 许可证。

SearXNG 从上游项目下载，使用 AGPL-3.0-or-later 许可证；小型
`patches/api_pool.py` 引擎适配器同样标注为 AGPL-3.0-or-later。分发包含
SearXNG 源码或修改文件的整包时，需要遵守其上游许可证。
