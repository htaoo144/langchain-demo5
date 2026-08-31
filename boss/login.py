"""登录模块：负责 Boss直聘 扫码登录全流程。

流程：打开首页 → 检测登录态（Cookie / 页面元素）→ 未登录则自动弹出扫码登录窗
→ 轮询等待用户用手机 App 扫码 → 登录成功（登录态由持久化上下文保存到 browser_data/）。
"""
import time
from urllib.parse import urljoin

from playwright.sync_api import Page

from boss.browser import BossBrowserError
from config import Config

# 登录成功后 Boss直聘 设置的主登录态 Cookie
LOGIN_COOKIE = "__zp_stoken__"
# 登录后页面才会出现的元素（页头消息/用户信息入口）
LOGIN_SELECTORS = [
    "[ka='header-message']",
    ".user-info",
    ".user-message",
    ".geek-user",
    ".header-user",
]
# 未登录时页头的登录入口
LOGIN_BTN_SELECTORS = [
    "[ka='header-login']",
    "text=登录/注册",
    ".btn-login",
]
# 登录弹窗内的登录方式标签（出现即代表弹窗已打开）
MODAL_TABS = ["扫码登录", "二维码登录"]


class LoginError(RuntimeError):
    pass


class LoginManager:
    """扫码登录管理。首次使用需人工扫码，之后登录态自动复用。"""

    def __init__(self, config: Config, browser) -> None:
        self.config = config
        self.browser = browser

    # ---------- 登录态检测 ----------

    def is_logged_in(self) -> bool:
        """Cookie 与页面元素双通道检测，任一命中即视为已登录。"""
        page = self.browser.start()
        try:
            cookies = page.context.cookies()
            if any(c["name"] == LOGIN_COOKIE and c.get("value") for c in cookies):
                return True
        except Exception:
            pass
        try:
            for sel in LOGIN_SELECTORS:
                loc = page.locator(sel)
                if loc.count() > 0 and loc.first.is_visible():
                    return True
        except Exception:
            pass
        return False

    # ---------- 触发登录弹窗 ----------

    def _open_login_modal(self, page: Page) -> bool:
        """点击页头『登录/注册』打开扫码登录弹窗；失败则跳转登录链接。返回弹窗是否出现。"""
        try:
            for sel in LOGIN_BTN_SELECTORS:
                loc = page.locator(sel).first
                if loc.count() > 0 and loc.is_visible():
                    loc.click(timeout=5000)
                    self.browser.human_delay(1, 2)
                    if self._modal_visible(page):
                        return True
                    # 点击后未弹窗：可能跳转登录页，跟踪其链接
                    href = loc.get_attribute("href")
                    if href:
                        page.goto(
                            urljoin("https://www.zhipin.com", href),
                            wait_until="domcontentloaded",
                            timeout=30000,
                        )
                        self.browser.human_delay(1.5, 3)
                        return self._modal_visible(page)
        except Exception:
            pass
        return False

    @staticmethod
    def _modal_visible(page: Page) -> bool:
        try:
            body = page.locator("body").inner_text(timeout=2000)
        except Exception:
            return False
        return any(t in body for t in MODAL_TABS)

    # ---------- 主流程 ----------

    def ensure_logged_in(self) -> bool:
        """确保已登录。未登录则阻塞等待人工扫码，超时返回 False。"""
        try:
            page = self.browser.start()
        except BossBrowserError as exc:
            print(f"[login] 无法启动浏览器，登录检查中止: {exc}")
            raise
        page.goto(
            self.config.boss_search_url,
            wait_until="domcontentloaded",
            timeout=60000,
        )
        self.browser.human_delay(2, 4)
        self.browser.check_risk_popup()

        if self.is_logged_in():
            print("[login] 已检测到登录态（Cookie/页面元素命中），无需重复登录。")
            return True

        if not self._open_login_modal(page):
            print("[login] 未能自动弹出登录窗口，请在浏览器窗口内手动完成登录。")
        else:
            print("[login] 已弹出扫码登录窗口，请用 Boss直聘 App 扫码确认。")

        print(
            f"[login] 正在等待登录完成（最长 {self.config.login_timeout} 秒，"
            "期间可随时手动操作浏览器）..."
        )
        deadline = time.monotonic() + self.config.login_timeout
        while time.monotonic() < deadline:
            time.sleep(2)
            if page.is_closed():
                break
            if self.is_logged_in():
                print("[login] ✓ 登录成功，登录态已保存到 browser_data/，下次无需再扫码。")
                return True
        print(f"[login] 等待超时（{self.config.login_timeout} 秒），请重试或手动确认登录状态。")
        return False
