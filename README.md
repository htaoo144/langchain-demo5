# Boss直聘 自动投简历 Agent

基于 **LangChain + LangGraph** 的求职自动化工具：在 Boss直聘 上搜索职位、抓取岗位要求、评估匹配度、按岗位定制简历（PDF）并自动投递打招呼语。

## 功能特性

- **LLM Agent 模式**：自然语言对话，由 LangGraph Agent 自动编排「搜索 → 抓详情 → 匹配评估 → 定制简历 → 投递」全流程
- **确定性批量模式（`--hunt`）**：一条命令完成全流程，不依赖 LLM API Key（无 Key 时跳过匹配评估与简历定制，仅支持搜索/投递流程）
- **简历定制流水线**：基于初始简历 PDF + GitHub 公开仓库资料，按岗位要求定制简历并渲染为 PDF（内置中文字体，无需系统依赖）
- **匹配度打分**：LLM 对岗位要求与简历评估 0~1 匹配度，低于阈值自动过滤
- **打招呼语生成**：自动生成 ≤50 字打招呼语并自动发送（可配置人工确认）
- **GitHub 资料拉取**：通过 REST API 获取用户简介与仓库列表，作为简历项目经历素材
- **投递统计**：投递结果记录到 `output/apply_log.csv`

## 项目结构

```
├── main.py              # CLI 入口：Agent 对话模式 / --hunt 批量模式
├── agent.py             # LangGraph Agent 编排（系统提示词 + 工具集）
├── tools.py             # LangChain 工具集（搜索/详情/定制/投递/统计）
├── config.py            # .env 配置加载与校验
├── resume_builder.py    # 简历流水线：PDF 提取 → LLM 定制 → PDF 渲染 + 匹配度/打招呼语
├── github_client.py     # GitHub REST API 客户端
├── boss/
│   ├── browser.py       # Playwright 浏览器封装（常驻单线程）
│   ├── login.py         # Boss直聘 登录流程
│   ├── recruiter.py     # 页面操作：搜索、抓详情、自动投递
│   └── hunt.py          # 确定性批量投递编排器
├── example/             # 按模块拆分的可运行示例（1~8）
├── resume/              # 初始简历（PDF）
└── output/              # 生成结果：定制简历 PDF/MD + 投递日志
```

## 环境要求

- Python 3.10+
- 已安装 Chromium（Playwright）：`playwright install chromium`
- 可选：DeepSeek API Key、GitHub Token

## 安装

```bash
pip install -r requirements.txt
playwright install chromium
```

## 配置

复制 `.env`（参考 `config.py` 中的配置项）：

```env
# LLM（兼容 OpenAI 协议）
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

# GitHub（不配置仅读取公开仓库，匿名限流 60 次/小时）
GITHUB_USERNAME=your_github_username
GITHUB_TOKEN=ghp_xxx

# Boss直聘
HEADLESS=false            # 首次使用需 false 手动登录（登录态保存于 browser_data/）
APPLY_AUTO=true           # false 时每次投递前人工确认
MAX_APPLY_PER_RUN=10      # 单次运行投递上限
MATCH_THRESHOLD=0.6       # 匹配度阈值 0~1
GREETING_MAX_LEN=50       # 打招呼语最大字数
DEFAULT_CITY=北京
LOGIN_TIMEOUT=300

# 简历
INITIAL_RESUME_PATH=resume/initial_resume.pdf
```

> 首次运行会打开浏览器窗口，请扫码/手机验证登录 Boss直聘；登录态保存在 `browser_data/`，后续运行自动复用。

## 使用

### Agent 对话模式（需配置 DEEPSEEK_API_KEY）

```bash
python main.py
```

示例输入：

```
找5个 Python 后端岗位并投递
```

Agent 按以下流程工作：

1. `search_boss_jobs` 搜索职位
2. `fetch_job_detail` 抓取岗位要求并评估匹配度（≥0.6）
3. `tailor_resume` 定制简历 + 生成打招呼语
4. `apply_to_job` 自动投递

输入 `/exit` 退出。

### 确定性批量模式（无需 LLM Key）

```bash
# 评估不投递
python main.py --hunt "Python后端" --dry-run

# 完整投递（最多抓取 20 条、投递 10 家）
python main.py --hunt "Python后端" --city 北京 --max-fetch 20 --max-apply 10

# 调整匹配阈值
python main.py --hunt "算法工程师" --threshold 0.7
```

参数说明：

| 参数 | 说明 | 默认值 |
| --- | --- | --- |
| `--hunt 关键词` | 批量模式搜索关键词 | 必填 |
| `--city` | 城市名（北京/上海/广州/深圳/杭州/成都/武汉/南京/西安/苏州） | `.env` 中 `DEFAULT_CITY` |
| `--max-fetch` | 最多抓取职位数 | 20 |
| `--max-apply` | 最多投递数 | `.env` 中 `MAX_APPLY_PER_RUN` |
| `--threshold` | 匹配度阈值 0~1 | `.env` 中 `MATCH_THRESHOLD` |
| `--dry-run` | 只评估不投递 | 关闭 |

也可直接运行：`python -m boss.hunt <关键词> [参数...]`

## 示例脚本

按模块递进的运行示例（在项目根目录执行）：

```bash
python example/1_config_example.py   # 配置加载与校验
python example/2_github_example.py   # GitHub 资料拉取
python example/3_resume_example.py   # 简历定制与 PDF 渲染
python example/4_login_example.py    # Boss直聘 登录
python example/5_recruiter_example.py# 搜索/抓详情/投递
python example/6_hunt_example.py     # 批量投递编排
python example/7_tools_example.py    # LangChain 工具集
python example/8_agent_example.py    # Agent 编排
```

## 输出

- 定制简历：`output/resumes/<公司>_<职位>.pdf`（同目录保留 `.md` 源稿）
- 投递日志：`output/apply_log.csv`
- 浏览器登录态：`browser_data/`（勿提交到版本库）

## 注意事项

- Boss直聘 页面结构可能改版，若选择器失效会抛出 `BossPageError`，需更新 `boss/recruiter.py` 中对应选择器
- 频繁投递可能触发风控（如验证码、打招呼上限），程序检测到上限会停止本轮投递；建议控制投递频率与数量
- 简历定制原则：忠实于真实经历，不虚构学历、公司、岗位；请在使用前核对生成内容
- 打招呼语 ≤50 字（超出自动截断）

## License

[MIT](LICENSE)
