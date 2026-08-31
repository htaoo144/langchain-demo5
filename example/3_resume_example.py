"""resume_builder 模块示例：PDF 提取 → LLM 定制简历 → PDF 输出。

展示三个能力：
1. extract_pdf_text     从初始简历 PDF 提取文本
2. tailor               按岗位要求 + GitHub 资料定制简历（生成打招呼语 + 定制 PDF）
3. match_score          评估简历与岗位的匹配度（0~1）

说明：需要 .env 中配置 DEEPSEEK_API_KEY 才会调用 LLM，否则只演示 PDF 提取与渲染。
运行: python example/3_resume_example.py
"""
from _bootstrap import *  # noqa: F401

from config import load_config
from resume_builder import ResumeBuilder, extract_pdf_text, render_markdown_to_pdf

# 示例岗位要求（真实使用时来自 boss/recruiter 抓取的 JD）
SAMPLE_JD = """岗位职责: 负责 Python 后端服务开发，使用 FastAPI/Django 构建 API，
维护 MySQL/Redis 数据层，熟悉 Docker 容器化部署。
任职要求: 有 LLM/Agent 应用经验优先，熟悉 LangChain 更佳。"""

# 示例 GitHub 资料（真实使用时来自 github_client.fetch_profile）
SAMPLE_GITHUB = """# GitHub: 示例用户
- 简介: Python / Rust 开发者
## 仓库
- **chatbot-api** (Python, ★12) 基于 LangChain 的聊天机器人 API
- **alagent** (Rust, ★8) 异步 LLM Agent 运行时，支持工具调用
- **spider-tools** (Python, ★5) 分布式爬虫工具集"""


def main() -> None:
    cfg = load_config()
    print(f"== 1. 提取初始简历文本 == 文件: {cfg.initial_resume_path}")
    text = extract_pdf_text(cfg.initial_resume_path)
    print(f"提取成功，共 {len(text)} 字符。开头预览: {text[:120]}...")

    print("\n== 2. 渲染测试 PDF（不调 LLM） ==")
    demo_pdf = render_markdown_to_pdf(
        "# 演示简历\n## 技能\n- Python\n- LangChain\n- Docker", cfg.output_dir / "demo.pdf", "演示"
    )
    print(f"已生成: {demo_pdf}")

    builder = ResumeBuilder(cfg)
    if not cfg.deepseek_api_key:
        print("\n[跳过 LLM 定制] .env 未配置 DEEPSEEK_API_KEY。")
        return

    print("\n== 3. LLM 定制简历 ==")
    result, pdf = builder.tailor(
        jd=SAMPLE_JD,
        github_markdown=SAMPLE_GITHUB,
        company="示例科技",
        job_title="Python后端",
    )
    print(f"目标岗位: {result.target_job}")
    print(f"打招呼语({len(result.greeting)}字): {result.greeting}")
    print(f"技能: {result.skills[:4]}")
    print(f"项目经历: {len(result.projects)} 条")
    print(f"定制简历 PDF: {pdf}")

    print("\n== 4. 匹配度评估 ==")
    score, reason = builder.match_score(SAMPLE_JD)
    print(f"匹配度: {score:.2f} | {reason}")


if __name__ == "__main__":
    main()
