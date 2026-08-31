"""LangGraph Agent 入口：把 LangChain 工具集编排成自动投简历助手。"""
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver

from config import load_config
from tools import all_tools

SYSTEM_PROMPT = """你是一个自动投简历助手，帮用户在 Boss直聘 上找工作并投递。

【工作流程】
1. 用户给出目标岗位关键词后，调用 search_boss_jobs 搜索职位；
2. 对感兴趣的职位调用 fetch_job_detail 抓取岗位要求并获取匹配度（0~1）；
3. 只选择匹配度 >= 0.6 的职位，调用 tailor_resume 定制简历并生成打招呼语；
4. 调用 apply_to_job 自动投递。

【规则】
- 投递前必须已对该职位执行过 fetch_job_detail 和 tailor_resume；
- 打招呼语已由 tailor_resume 生成，不要自己改写；
- 投递数量默认不超过 10 家，除非用户明确要求更多；
- 每次行动后用中文简短汇报结果（投了哪家、匹配度多少、简历生成在哪）。"""


def run(model: str, user_input: str, config: dict) -> str:
    cfg = load_config()
    agent_model = ChatOpenAI(
        model=model,
        api_key=cfg.deepseek_api_key,
        base_url=cfg.deepseek_base_url,
        temperature=0.1,
        max_tokens=2048,
        timeout=120,
    )
    agent = create_agent(
        model=agent_model,
        tools=all_tools(),
        system_prompt=SYSTEM_PROMPT,
        checkpointer=InMemorySaver(),
    )
    response = agent.invoke(
        {"messages": [{"role": "user", "content": user_input}]},
        config=config,
    )
    messages = response.get("messages", [])
    last = messages[-1] if messages else response
    content = getattr(last, "content", str(response))
    print(content)
    return content
