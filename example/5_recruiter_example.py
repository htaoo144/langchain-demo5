"""boss/recruiter 模块示例：搜索职位 → 抓取岗位详情。

展示：
1. search_jobs          按关键词/城市搜索职位卡片
2. extract_job_detail   打开详情页提取岗位要求文本与技能关键词
3. apply_stats          查看投递统计（apply_log.csv）
（投递动作不在此示例中执行）

运行: python example/5_recruiter_example.py [关键词]
"""
from _bootstrap import *  # noqa: F401

import sys

from boss.browser import BossBrowser
from boss.recruiter import BossRecruiter
from config import load_config


def main() -> None:
    keyword = sys.argv[1] if len(sys.argv) > 1 else "Python实习生"
    cfg = load_config()
    browser = BossBrowser(cfg)
    try:
        if not browser.ensure_logged_in():
            print("登录未完成，退出示例。")
            return
        recruiter = BossRecruiter(cfg, browser)

        print(f"== 搜索: {keyword}（城市: {cfg.default_city}）==")
        cards = recruiter.search_jobs(keyword, limit=5)
        if not cards:
            print("未找到职位。")
            return
        for i, card in enumerate(cards, 1):
            print(f"{i}. {card.brief()[:100]}")

        print(f"\n== 抓取第 1 个职位详情 ==")
        detail = recruiter.extract_job_detail(cards[0])
        if detail is None:
            print("抓取失败（可能已下架或需登录）。")
        else:
            print(f"公司: {detail.card.company} | 职位: {detail.card.title}")
            print(f"技术关键词: {', '.join(detail.skills) or '无'}")
            print(f"岗位要求(前500字):\n{detail.description[:500]}")

        print("\n== 投递统计 ==")
        print(recruiter.apply_stats())
    finally:
        browser.close()


if __name__ == "__main__":
    main()
