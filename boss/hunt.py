"""确定性批量投递编排器：不依赖 LLM Agent，一条命令完成
搜索 → 抓详情 → 匹配度过滤 → 定制简历 → 自动投递 全流程。

适合：无 API Key 的日常使用 / 批处理 / 与 Agent 模式互为备份。
"""
import time
from dataclasses import dataclass, field

from boss.browser import BossBrowser
from boss.login import LoginError
from boss.recruiter import ApplyResult, BossLimitReached, BossRecruiter, JobCard, JobDetail
from config import Config, load_config
from github_client import GitHubClient
from resume_builder import ResumeBuilder


@dataclass
class HuntResult:
    keyword: str
    city: str
    found: list[JobCard] = field(default_factory=list)
    shortlisted: list[tuple[JobDetail, float, str]] = field(default_factory=list)
    applied: list[ApplyResult] = field(default_factory=list)
    resume_pdfs: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"== 投递报告：{self.keyword}（{self.city or '默认城市'}）==",
            f"搜索到职位: {len(self.found)}",
            f"通过匹配度过滤（入选）: {len(self.shortlisted)}",
        ]
        for detail, score, reason in self.shortlisted:
            lines.append(
                f"  - {detail.card.title} | {detail.card.company} | {detail.card.salary} "
                f"| 匹配度 {score:.2f} | {reason}"
            )
        lines.append(f"投递结果: {len(self.applied)}")
        for r in self.applied:
            lines.append(f"  [{r.status}] {r.message}")
        lines.append("定制简历:")
        lines += [f"  - {p}" for p in self.resume_pdfs] or ["  （无）"]
        return "\n".join(lines)


class HuntRunner:
    """执行一轮批量投递。"""

    def __init__(self, config: Config):
        self.config = config

    def run(
        self,
        keyword: str,
        city: str | None = None,
        max_fetch: int = 20,
        max_apply: int | None = None,
        threshold: float | None = None,
        dry_run: bool = False,
    ) -> HuntResult:
        cfg = self.config
        max_apply = cfg.max_apply_per_run if max_apply is None else max_apply
        threshold = cfg.match_threshold if threshold is None else threshold
        result = HuntResult(keyword=keyword, city=city or cfg.default_city)

        browser = BossBrowser(cfg)
        try:
            print(f"[hunt] 登录检查（{result.city}）...")
            if not browser.ensure_logged_in():
                raise LoginError("登录未完成，中止投递")

            recruiter = BossRecruiter(cfg, browser)
            builder = ResumeBuilder(cfg)
            github = GitHubClient(cfg)
            has_llm = bool(cfg.deepseek_api_key)

            print(f"[hunt] 搜索 '{keyword}'（最多 {max_fetch} 条）...")
            result.found = recruiter.search_jobs(keyword, city or None, limit=max_fetch)
            print(f"[hunt] 搜索到 {len(result.found)} 个职位")

            # 阶段1：抓详情 + 匹配度过滤
            for i, card in enumerate(result.found, 1):
                print(f"[hunt] ({i}/{len(result.found)}) 抓取详情: {card.brief()[:80]}...")
                detail = recruiter.extract_job_detail(card)
                if detail is None:
                    continue
                if has_llm:
                    try:
                        score, reason = builder.match_score(detail.description)
                    except Exception as exc:
                        score, reason = 0.0, f"LLM 评估失败: {exc}"
                else:
                    score, reason = 1.0, "未配置 DEEPSEEK_API_KEY，跳过 LLM 评估"
                print(f"        匹配度 {score:.2f}（{reason}）")
                if score >= threshold:
                    result.shortlisted.append((detail, score, reason))
                time.sleep(0.5)

            result.shortlisted.sort(key=lambda x: -x[1])
            result.shortlisted = result.shortlisted[:max_apply]
            print(f"[hunt] 入选 {len(result.shortlisted)} 个，开始投递（dry_run={dry_run}）...")

            # 阶段2：定制简历 + 投递
            for detail, score, _ in result.shortlisted:
                if dry_run:
                    result.applied.append(ApplyResult("skipped", f"[dry-run] 模拟投递 {detail.card.company} {detail.card.title}"))
                    continue
                if not has_llm:
                    result.applied.append(ApplyResult("skipped", "未配置 DEEPSEEK_API_KEY，无法生成打招呼语"))
                    continue
                print(f"[hunt] 定制简历: {detail.card.company} {detail.card.title}")
                try:
                    tailored, pdf = builder.tailor(
                        jd=detail.description,
                        github_markdown=github.fetch_profile().to_markdown(),
                        company=detail.card.company,
                        job_title=detail.card.title,
                    )
                    result.resume_pdfs.append(str(pdf))
                except Exception as exc:
                    result.applied.append(ApplyResult("failed", f"简历定制失败: {exc}"))
                    continue
                try:
                    res = recruiter.apply_to_job(detail, tailored.greeting)
                except BossLimitReached as exc:
                    result.applied.append(ApplyResult("limit_reached", str(exc)))
                    print(f"[hunt] {exc}，终止本轮投递。")
                    break
                result.applied.append(res)
                print(f"[hunt] {res.message}")
                browser.human_delay(3, 6)
            return result
        finally:
            browser.close()


def main_cli() -> None:
    """命令行入口：python -m boss.hunt <关键词> [--city 北京] [--max-apply 5] [--dry-run]"""
    import argparse
    import sys

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Boss直聘 批量投递（确定性编排）")
    parser.add_argument("keyword", help="搜索关键词，如 'Python后端'")
    parser.add_argument("--city", default="", help="城市名，如 北京/上海，默认读 .env")
    parser.add_argument("--max-fetch", type=int, default=20, help="最多抓取职位数")
    parser.add_argument("--max-apply", type=int, default=None, help="最多投递数（默认读 .env）")
    parser.add_argument("--threshold", type=float, default=None, help="匹配度阈值 0~1")
    parser.add_argument("--dry-run", action="store_true", help="只评估不投递")
    args = parser.parse_args()

    cfg = load_config()
    result = HuntRunner(cfg).run(
        args.keyword,
        city=args.city or None,
        max_fetch=args.max_fetch,
        max_apply=args.max_apply,
        threshold=args.threshold,
        dry_run=args.dry_run,
    )
    print("\n" + result.summary())


if __name__ == "__main__":
    main_cli()
