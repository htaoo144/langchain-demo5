"""boss/hunt 模块示例：确定性批量投递全流程（无需 LLM Agent）。

流程: 搜索 → 抓详情 → 匹配度过滤 → 定制简历 → 自动投递，一条命令跑完。
本示例默认 --dry-run（只评估不投递），确认无误后去掉 dry_run 参数即可真投。

说明：
- 未配置 DEEPSEEK_API_KEY 时跳过匹配度评估与简历定制，仅演示搜索；
- 投递前会检测登录态，未登录则需扫码。
运行: python example/6_hunt_example.py
"""
from _bootstrap import *  # noqa: F401

from boss.hunt import HuntRunner
from config import load_config


def main() -> None:
    cfg = load_config()
    runner = HuntRunner(cfg)
    result = runner.run(
        keyword="Python实习生",
        city=None,          # None=用 .env 的 DEFAULT_CITY
        max_fetch=6,        # 最多抓 6 个职位
        max_apply=2,        # 最多投 2 家
        dry_run=True,       # 安全起见先模拟，去掉即真实投递
    )
    print("\n" + result.summary())


if __name__ == "__main__":
    main()
