"""LangChain 工具集：封装 GitHub 拉取、简历定制、Boss直聘搜索/投递。

线程模型说明：LangGraph 1.x 把工具执行在每次 invoke 新建的线程池线程上，
而 Playwright 同步 API 要求所有调用都发生在创建它的同一线程。
因此所有工具逻辑统一经 Services.run_browser 投递到一个进程级常驻单线程执行器，
保证浏览器永远只在同一个线程上创建、使用、关闭。
"""
import atexit
import json
from concurrent.futures import ThreadPoolExecutor

from langchain.tools import tool

from boss.browser import BossBrowser
from boss.recruiter import BossLimitReached, BossRecruiter, JobCard
from config import load_config
from github_client import GitHubClient
from resume_builder import ResumeBuilder, TailoredResume


class Services:
    """全局服务容器（单例），供各工具共享浏览器与缓存。

    _executor 为进程级常驻单线程执行器：LangGraph 每次 invoke 的线程池会随调用结束
    销毁，若浏览器对象在那样的线程上创建，下次调用就会触发 greenlet 崩溃
    （cannot switch to a different thread）。因此浏览器相关操作必须全部经
    run_browser 投递到本常驻线程执行。
    """

    _instance: "Services | None" = None

    def __init__(self):
        self.config = load_config()
        self.github = GitHubClient(self.config)
        self.builder = ResumeBuilder(self.config)
        self.browser = BossBrowser(self.config)
        self.recruiter = BossRecruiter(self.config, self.browser)
        self._details: dict[str, object] = {}
        self._tailored: dict[str, TailoredResume] = {}
        self._applied_this_run = 0
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="browser")

    def run_browser(self, fn, *args, **kwargs):
        """把函数投递到常驻浏览器线程执行并同步等待结果。"""
        return self._executor.submit(fn, *args, **kwargs).result()

    def shutdown(self) -> None:
        """在浏览器线程上关闭浏览器并回收执行器（幂等）。"""
        try:
            self.run_browser(self.browser.close)
        except Exception:
            pass
        self._executor.shutdown(wait=True)

    @classmethod
    def get(cls) -> "Services":
        if cls._instance is None:
            cls._instance = Services()
            atexit.register(cls._instance.shutdown)
        return cls._instance


def _srv() -> Services:
    return Services.get()


# ---------- GitHub ----------

@tool
def fetch_github_profile() -> str:
    """获取我的 GitHub 账号资料（简介 + 仓库列表），用于简历定制时的项目经历素材。"""
    return _srv().run_browser(_fetch_github_profile)


def _fetch_github_profile() -> str:
    try:
        profile = _srv().github.fetch_profile()
        return profile.to_markdown()
    except Exception as exc:
        return f"GitHub 拉取失败: {exc}"


# ---------- Boss直聘 ----------

@tool
def search_boss_jobs(keyword: str, city: str = "", limit: int = 10) -> str:
    """在 Boss直聘上搜索职位。
    Args:
        keyword: 搜索关键词，如 'Python后端'、'算法工程师'
        city: 城市名，如 '北京'/'上海'，留空用默认城市
        limit: 最多返回的职位数（默认10）
    """
    return _srv().run_browser(_search_boss_jobs, keyword, city, limit)


def _search_boss_jobs(keyword: str, city: str, limit: int) -> str:
    srv = _srv()
    errors = srv.config.validate()
    if errors:
        return "配置错误: " + "；".join(errors)
    if not srv.browser.start():
        return "浏览器启动失败"
    try:
        if not srv.browser.ensure_logged_in():
            return "未完成登录，无法搜索"
        cards = srv.recruiter.search_jobs(keyword, city or None, limit=limit)
    except Exception as exc:
        return f"搜索失败: {exc}"
    if not cards:
        if srv.recruiter._is_blank_page(srv.browser._page):
            return "搜索页面未正常加载（可能被 BOSS直聘 风控屏蔽），请等待几分钟后重试或手动在浏览器中完成验证。"
        return "未找到任何职位"
    for c in cards:
        srv._details[c.url] = c
    return json.dumps(
        [
            {
                "title": c.title,
                "salary": c.salary,
                "company": c.company,
                "tags": c.tags,
                "url": c.url,
            }
            for c in cards
        ],
        ensure_ascii=False,
        indent=2,
    )


@tool
def fetch_job_detail(url: str) -> str:
    """获取指定职位（用 search_boss_jobs 返回的 url）的完整岗位要求文本，并评估与我简历的匹配度（0~1）。"""
    return _srv().run_browser(_fetch_job_detail, url)


def _fetch_job_detail(url: str) -> str:
    srv = _srv()
    if url not in srv._details:
        card = _card_from_url(url)
        if card is None:
            return f"未找到该 url 对应的职位卡片: {url}，请先调用 search_boss_jobs"
        srv._details[url] = card
    card = srv._details[url]
    detail = srv.recruiter.extract_job_detail(card)
    if detail is None:
        return f"提取岗位详情失败（可能已下架或需登录）: {url}"
    srv._details[url] = detail
    try:
        score, reason = srv.builder.match_score(detail.description)
    except Exception as exc:
        score, reason = -1.0, f"匹配度评估失败: {exc}"
    return (
        f"匹配度: {score:.2f}（理由: {reason}）\n"
        f"技术关键词: {', '.join(detail.skills) or '无'}\n\n"
        f"岗位要求:\n{detail.description}"
    )


@tool
def tailor_resume(url: str, company: str = "", job_title: str = "") -> str:
    """根据岗位要求定制我的简历并生成打招呼语。
    Args:
        url: 职位 url（来自 search_boss_jobs）
        company: 公司名（可选）
        job_title: 职位名（可选）
    返回打招呼语与简历 PDF 路径。
    """
    return _srv().run_browser(_tailor_resume, url, company, job_title)


def _tailor_resume(url: str, company: str, job_title: str) -> str:
    srv = _srv()
    detail = srv._details.get(url)
    if detail is None:
        return f"该 url 尚未抓取岗位详情: {url}，请先调用 fetch_job_detail"
    try:
        github_md = srv.github.fetch_profile().to_markdown()
        tailored, pdf_path = srv.builder.tailor(
            jd=detail.description,
            github_markdown=github_md,
            company=company or getattr(detail.card, "company", ""),
            job_title=job_title or getattr(detail.card, "title", ""),
        )
    except Exception as exc:
        return f"简历定制失败: {exc}"
    srv._tailored[url] = tailored
    return f"简历已生成: {pdf_path}\n打招呼语（{len(tailored.greeting)}字）: {tailored.greeting}"


@tool
def apply_to_job(url: str) -> str:
    """向指定职位自动打招呼投递（使用 tailor_resume 生成的打招呼语）。
    若 .env 中 APPLY_AUTO=false，则发送前会请求人工确认。
    """
    return _srv().run_browser(_apply_to_job, url)


def _apply_to_job(url: str) -> str:
    srv = _srv()
    detail = srv._details.get(url)
    tailored = srv._tailored.get(url)
    if detail is None or tailored is None:
        return f"缺少该 url 的岗位详情或打招呼语（请先 fetch_job_detail + tailor_resume）: {url}"
    if srv._applied_this_run >= srv.config.max_apply_per_run:
        return "已达本次运行投递上限，不再投递。"
    if not srv.config.apply_auto:
        print(f"\n[确认] 将向 {detail.card.company} {detail.card.title} 发送:\n  {tailored.greeting}")
        try:
            reply = input("回车确认发送，输入 n 跳过: ").strip().lower()
        except EOFError:
            reply = ""
        if reply == "n":
            return "已跳过该岗位。"
    try:
        result = srv.recruiter.apply_to_job(detail, tailored.greeting)
    except BossLimitReached as exc:
        return f"{exc}，本轮投递终止。"
    if result.status == "ok":
        srv._applied_this_run += 1
    return f"[{result.status}] {result.message}"


@tool
def apply_stats() -> str:
    """查看本轮及历史投递统计（按状态汇总 + 最近记录）。"""
    return _srv().run_browser(_apply_stats)


def _apply_stats() -> str:
    return _srv().recruiter.apply_stats()


def _card_from_url(url: str):
    """从缓存中按 url 找卡片（用于 fetch_job_detail 补录）。"""
    for v in _srv()._details.values():
        if isinstance(v, JobCard) and v.url == url:
            return v
    return None


def all_tools():
    return [
        fetch_github_profile,
        search_boss_jobs,
        fetch_job_detail,
        tailor_resume,
        apply_to_job,
        apply_stats,
    ]
