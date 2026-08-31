"""tools 模块示例：不经过 LLM Agent，直接调用各个 LangChain 工具。

展示每个工具的输入输出（apply_to_job 为保护起见默认跳过）：
1. fetch_github_profile   GitHub 资料
2. search_boss_jobs       搜索职位
3. fetch_job_detail       抓详情 + 匹配度
4. tailor_resume          定制简历 + 打招呼语
5. apply_stats            投递统计
6. apply_to_job           自动投递（示例中跳过）

运行: python example/7_tools_example.py
"""
from _bootstrap import *  # noqa: F401

from tools import (
    apply_stats,
    fetch_github_profile,
    fetch_job_detail,
    search_boss_jobs,
    tailor_resume,
)


def main() -> None:
    print("== 1. fetch_github_profile ==")
    print(fetch_github_profile.invoke({})[:300])
    print()

    print("== 2. search_boss_jobs ==")
    raw = search_boss_jobs.invoke({"keyword": "Python实习生", "city": "北京", "limit": 3})
    print(raw[:800])
    print()

    import json

    try:
        cards = json.loads(raw)
    except Exception:
        cards = []
    if not cards:
        print("未拿到职位卡片，后续步骤跳过。")
        return
    url = cards[0]["url"]

    print("== 3. fetch_job_detail ==")
    print(fetch_job_detail.invoke({"url": url})[:600])
    print()

    print("== 4. tailor_resume ==")
    print(tailor_resume.invoke({"url": url})[:400])
    print()

    print("== 5. apply_stats ==")
    print(apply_stats.invoke({}))

    print("\n（apply_to_job 为保护起见不在示例中执行；需要时在 REPL 或 hunt 中使用。）")


if __name__ == "__main__":
    main()
