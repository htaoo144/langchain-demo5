"""Boss直聘页面操作：搜索职位、提取岗位要求、自动打招呼投递。

选择器基于 zhipin.com 当前页面结构，若改版失败会抛出 BossPageError，
需要按新结构更新对应选择器。
"""
import csv
import random
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from boss.browser import BossBrowser
from config import Config

# 常用城市 -> 城市 code（Boss直聘 URL 参数）
CITY_CODES = {
    "": "",
    "全国": "",
    "北京": "101010100",
    "上海": "101020100",
    "广州": "101280100",
    "深圳": "101280600",
    "杭州": "101210100",
    "成都": "101270100",
    "武汉": "101200100",
    "南京": "101190100",
    "西安": "101110100",
    "苏州": "101190400",
}


class BossPageError(RuntimeError):
    pass


class BossLimitReached(Exception):
    """打招呼次数已达上限，应停止本轮投递。"""


@dataclass
class JobCard:
    title: str = ""
    salary: str = ""
    company: str = ""
    tags: str = ""
    url: str = ""
    score: float = 0.0

    def brief(self) -> str:
        return f"{self.title} | {self.salary} | {self.company} | {self.tags} | {self.url}"


@dataclass
class JobDetail:
    card: JobCard
    description: str = ""
    skills: list[str] = field(default_factory=list)

    def to_text(self) -> str:
        return f"职位: {self.card.title}\n公司: {self.card.company}\n薪资: {self.card.salary}\n{self.description}"


@dataclass
class ApplyResult:
    status: str  # ok / already_applied / blocked / limit_reached / failed / skipped
    message: str


class BossRecruiter:
    def __init__(self, config: Config, browser: BossBrowser):
        self.config = config
        self.browser = browser
        self.apply_log_path: Path = config.output_dir / "apply_log.csv"
        self._init_log()

    # ---------- 日志 ----------

    def _init_log(self) -> None:
        if not self.apply_log_path.exists():
            with open(self.apply_log_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["时间", "公司", "职位", "薪资", "状态", "备注", "链接"])

    def _log(self, card: JobCard, status: str, note: str = "") -> None:
        with open(self.apply_log_path, "a", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    card.company,
                    card.title,
                    card.salary,
                    status,
                    note,
                    card.url,
                ]
            )

    def apply_stats(self) -> str:
        """汇总投递日志：按状态统计。"""
        counts: dict[str, int] = {}
        recent: list[str] = []
        if self.apply_log_path.exists():
            with open(self.apply_log_path, newline="", encoding="utf-8-sig") as f:
                for row in csv.reader(f):
                    if len(row) < 5 or row[0] == "时间":
                        continue
                    counts[row[4]] = counts.get(row[4], 0) + 1
                    if len(recent) < 5:
                        recent.append(f"{row[0]} | {row[1]} | {row[2]} | {row[4]}")
        lines = ["== 投递统计 =="]
        for status, n in sorted(counts.items(), key=lambda x: -x[1]):
            lines.append(f"  {status}: {n}")
        lines.append("== 最近记录 ==")
        lines += [f"  {r}" for r in recent] or ["  （暂无投递记录）"]
        return "\n".join(lines)

    def _already_applied(self, card: JobCard) -> bool:
        if not self.apply_log_path.exists():
            return False
        with open(self.apply_log_path, newline="", encoding="utf-8-sig") as f:
            for row in csv.reader(f):
                if len(row) >= 7 and row[4] in ("ok", "already_applied") and row[6] == card.url:
                    return True
        return False

    # ---------- 搜索职位 ----------

    @staticmethod
    def _is_blank_page(page: Page) -> bool:
        """页面是否为空壳（zhipin 风控软屏蔽时返回空 body 或跳转 about:blank）。"""
        try:
            if page.url.startswith("about:blank"):
                return True
            body = page.locator("body").inner_text(timeout=3000)
            return not body.strip()
        except Exception:
            return True

    def search_jobs(self, keyword: str, city: str | None = None, limit: int = 10) -> list[JobCard]:
        """搜索职位，返回职位卡片列表。

        zhipin 会间歇性对自动化浏览器做风控软屏蔽（页面变空壳/about:blank），
        检测到后等待冷却并自动重试。
        """
        city = city or self.config.default_city
        code = CITY_CODES.get(city, "")
        url = self.config.boss_search_url
        url += f"?query={keyword}"
        if code:
            url += f"&city={code}"

        page = self.browser.start()
        for attempt in range(1, 4):
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            self.browser.human_delay(2, 4)
            self.browser.check_risk_popup()
            if not self._is_blank_page(page):
                break
            print(
                f"[recruiter] 搜索页为空壳（可能被风控），"
                f"第 {attempt} 次尝试失败，冷却 {attempt * 20} 秒后重试..."
            )
            time.sleep(attempt * 20)

        cards: list[JobCard] = []
        seen: set[str] = set()
        while len(cards) < limit:
            for wrapper in page.locator(".job-card-wrapper").all():
                if len(cards) >= limit:
                    break
                try:
                    card = self._parse_card(wrapper)
                except Exception:
                    continue
                if not card.url or card.url in seen:
                    continue
                seen.add(card.url)
                cards.append(card)
            if len(cards) >= limit or not self._next_page(page):
                break
            self.browser.human_delay(3, 6)

        if not cards and self._is_blank_page(page):
            print(
                "[recruiter] 搜索页始终未正常加载（可能被 zhipin 风控屏蔽）。"
                "请等待几分钟后重试，或在打开的浏览器窗口中手动完成一次验证。"
            )
        return cards

    def _parse_card(self, wrapper) -> JobCard:
        link = wrapper.locator("a.job-card-left").first
        href = link.get_attribute("href") or ""
        title = link.locator(".job-title").inner_text().strip() or link.inner_text().strip()
        salary = wrapper.locator(".salary").inner_text().strip()
        company = wrapper.locator(".company-name").inner_text().strip()
        info = wrapper.locator(".job-info").inner_text().replace("\n", " ").strip()
        tags = wrapper.locator(".tag-list").inner_text().replace("\n", " ").strip()
        if href and not href.startswith("http"):
            href = "https://www.zhipin.com" + href
        return JobCard(title=title, salary=salary, company=company, tags=f"{info} {tags}".strip(), url=href)

    def _next_page(self, page: Page) -> bool:
        next_btn = page.locator(".options-pagination a:has-text('下一页')").first
        try:
            if next_btn.count() == 0 or not next_btn.is_enabled():
                return False
            next_btn.click()
            return True
        except Exception:
            return False

    # ---------- 提取岗位详情 ----------

    def extract_job_detail(self, card: JobCard) -> JobDetail | None:
        """打开职位详情，提取岗位要求文本。

        直聘详情页可能开新标签页，也可能同页 SPA 导航；
        只有真正的新标签页才关闭，避免误关主页面。
        """
        page = self.browser.start()
        detail_page = None
        try:
            with page.context.expect_page(timeout=15000) as page_info:
                page.goto(card.url, wait_until="domcontentloaded", timeout=60000)
            detail_page = page_info.value
        except Exception:
            try:
                detail_page = page.context.pages[-1]
            except Exception:
                return None
        if detail_page is None:
            return None
        detail_page.wait_for_load_state("domcontentloaded", timeout=60000)
        self.browser.human_delay(1.5, 3)
        self.browser.check_risk_popup()

        try:
            text = detail_page.locator("body").inner_text(timeout=10000)
        except Exception:
            self._safe_close(detail_page, page)
            return None

        if not text.strip():
            self._safe_close(detail_page, page)
            return None

        desc = self._extract_jd_section(text)
        skills = self._extract_skills(desc)
        self._safe_close(detail_page, page)
        if not desc:
            return None
        return JobDetail(card=card, description=desc, skills=skills)

    @staticmethod
    def _safe_close(detail_page: Page, main_page: Page) -> None:
        """仅当详情页是独立标签页时才关闭，避免误关主页面。"""
        try:
            if detail_page is not main_page and not detail_page.is_closed():
                detail_page.close()
        except Exception:
            pass

    @staticmethod
    def _extract_jd_section(text: str) -> str:
        """从整页文本中切出岗位职责/任职要求部分。"""
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        start = 0
        for i, line in enumerate(lines):
            if re.search(r"岗位职责|工作内容|职位描述|职位信息", line):
                start = i
                break
        section = "\n".join(lines[start:])
        if len(section) > 3000:
            section = section[:3000]
        return section

    @staticmethod
    def _extract_skills(desc: str) -> list[str]:
        """粗提取 JD 中的技术关键词。"""
        known = [
            "python", "java", "go", "golang", "c++", "c#", "javascript", "typescript",
            "react", "vue", "django", "flask", "fastapi", "spring", "mysql", "redis",
            "postgresql", "mongodb", "docker", "kubernetes", "k8s", "aws", "linux",
            "git", "langchain", "llm", "机器学习", "深度学习", "nlp", "算法", "微服务",
            "爬虫", "数据分析", "flink", "kafka", "hadoop", "spark",
        ]
        found = []
        lower = desc.lower()
        for k in known:
            if k.lower() in lower and k not in found:
                found.append(k)
        return found

    # ---------- 自动投递 ----------

    def apply_to_job(self, detail: JobDetail, greeting: str) -> ApplyResult:
        """全自动投递：打开职位页 → 立即沟通 → 发送打招呼语。"""
        card = detail.card
        if self._already_applied(card):
            self._log(card, "already_applied", "历史日志命中，跳过")
            return ApplyResult("already_applied", "已投递过，跳过")

        page = self.browser.start()
        page.goto(card.url, wait_until="domcontentloaded", timeout=60000)
        self.browser.human_delay(2, 4)
        self.browser.check_risk_popup()

        # 立即沟通
        start_btn = page.get_by_text("立即沟通").first
        try:
            start_btn.click(timeout=10000)
        except Exception:
            self._log(card, "failed", "未找到立即沟通按钮")
            return ApplyResult("failed", "未找到立即沟通按钮")

        self.browser.human_delay(2, 4)
        self.browser.check_risk_popup()

        # 检查是否已沟通/受限
        body_text = page.locator("body").inner_text(timeout=8000)
        if any(m in body_text for m in ["沟通人数已达上限", "今日沟通次数已达上限", "已达上限"]):
            raise BossLimitReached("今日打招呼次数已达上限")

        # 发送打招呼语
        textarea = page.locator(".chat-input textarea, textarea[placeholder*='打招呼'], textarea[placeholder*='说点什么']").first
        try:
            textarea.wait_for(state="visible", timeout=10000)
        except PlaywrightTimeout:
            self._log(card, "failed", "聊天输入框未出现")
            return ApplyResult("failed", "聊天输入框未出现")

        try:
            self.browser.human_type(page, textarea, greeting)
        except Exception as exc:
            self._log(card, "failed", f"输入打招呼语失败: {exc}")
            return ApplyResult("failed", f"输入打招呼语失败: {exc}")
        self.browser.human_delay(0.5, 1.5)

        send_btn = page.locator(".btn-send, button:has-text('发送')").first
        sent = False
        try:
            if send_btn.count() > 0 and send_btn.is_visible():
                send_btn.click()
                sent = True
        except Exception:
            pass
        if not sent:
            try:
                textarea.press("Enter")
                sent = True
            except Exception as exc:
                self._log(card, "failed", f"发送失败: {exc}")
                return ApplyResult("failed", f"发送失败: {exc}")
        time.sleep(2)

        self._log(card, "ok", f"打招呼: {greeting[:20]}...")
        return ApplyResult("ok", f"已发送招呼 → {card.company} {card.title}")
