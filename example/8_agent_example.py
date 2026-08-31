"""agent 模块示例：让 LLM Agent 自主完成一次「搜索-评估-汇报」任务。

Agent 会自主调用 tools（搜索/抓详情/匹配度评估），并向用户汇报。
投递类动作不在本示例中执行（提示词中要求只评估不投递）。

说明：需要 .env 中配置 DEEPSEEK_API_KEY。
运行: python example/8_agent_example.py
"""
from _bootstrap import *  # noqa: F401

from agent import run
from config import load_config


def main() -> None:
    cfg = load_config()
    if not cfg.deepseek_api_key:
        print("未配置 DEEPSEEK_API_KEY，无法运行 Agent。")
        return
    prompt = "在北京找3个Python实习岗位，抓取岗位要求并评估与我简历的匹配度，按匹配度从高到低汇报，不要投递。"
    print(f"用户: {prompt}\n")
    run(
        cfg.deepseek_model,
        prompt,
        {"configurable": {"thread_id": "example-1"}},
    )


if __name__ == "__main__":
    main()
