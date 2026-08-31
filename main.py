import argparse
import sys

from agent import run
from config import load_config

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def cli_hunt(args: argparse.Namespace) -> None:
    """无 LLM 的确定性批量投递模式。"""
    from boss.browser import BossBrowserError
    from boss.hunt import HuntRunner

    cfg = load_config()
    try:
        result = HuntRunner(cfg).run(
            args.keyword,
            city=args.city or None,
            max_fetch=args.max_fetch,
            max_apply=args.max_apply,
            threshold=args.threshold,
            dry_run=args.dry_run,
        )
    except BossBrowserError as exc:
        print(f"[错误] {exc}")
        return
    print("\n" + result.summary())


def cli_repl() -> None:
    cfg = load_config()
    print(f"模型: {cfg.deepseek_model} | 城市: {cfg.default_city} | 投递上限: {cfg.max_apply_per_run} | 自动投递: {cfg.apply_auto}")
    print("输入 /exit 退出。示例：'找5个 Python 后端岗位并投递'（或退出后用 python main.py --hunt 'Python后端' 走无 LLM 模式）")
    agent_config = {"configurable": {"thread_id": "1"}}
    while True:
        try:
            user_input = input("你: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user_input:
            continue
        if user_input in ("/exit", "exit", "退出"):
            break
        try:
            run(cfg.deepseek_model, user_input, agent_config)
        except Exception as exc:
            print(f"[错误] {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Boss直聘 自动投简历 Agent")
    parser.add_argument("--hunt", metavar="关键词", default=None, help="确定性批量投递模式（无需 LLM Key）")
    parser.add_argument("--city", default="", help="城市名（仅 --hunt 生效）")
    parser.add_argument("--max-fetch", type=int, default=20, help="最多抓取职位数（仅 --hunt）")
    parser.add_argument("--max-apply", type=int, default=None, help="最多投递数（仅 --hunt）")
    parser.add_argument("--threshold", type=float, default=None, help="匹配度阈值（仅 --hunt）")
    parser.add_argument("--dry-run", action="store_true", help="只评估不投递（仅 --hunt）")
    args = parser.parse_args()

    if args.hunt:
        cli_hunt(args)
    else:
        cli_repl()


if __name__ == "__main__":
    main()
