"""Playwright 浏览器管理：持久化登录态、反检测、风险弹窗检测。

使用 launch_persistent_context 把登录态保存到 browser_data/，
登录流程见 login.LoginManager（首次需人工扫码一次，之后自动复用）。
"""
import random
import time
from pathlib import Path

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

from config import Config

# 风险弹窗常见特征文本（滑块验证、封禁提示等）
RISK_MARKERS = ["安全验证", "拖动滑块", "验证码", "操作频繁", "访问受限", "异常行为"]

# 模拟的 Chrome UA（仅首次优先用本机 Chrome 时携带）
_CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


class BossBrowserError(RuntimeError):
    """浏览器启动/运行失败，错误信息包含可操作的处理建议。"""


def _brief(exc: Exception) -> str:
    """把异常压成一行并截断，用于控制台提示。"""
    msg = str(exc).strip().replace("\n", " | ")
    return msg[:300] or exc.__class__.__name__


class BossBrowser:
    def __init__(self, config: Config):
        self.config = config
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    # ---------- 生命周期 ----------

    def start(self) -> Page:
        if self._page and not self._page.is_closed():
            return self._page
        # 先回收旧实例，确保每次启动都使用全新的 Playwright 实例
        self._dispose()

        data_dir = str(self.config.browser_data_dir)
        Path(data_dir).mkdir(parents=True, exist_ok=True)
        first_error: Exception | None = None

        attempts = (
            {"label": "本机 Chrome", "channel": "chrome", "user_agent": _CHROME_UA},
            {"label": "Playwright chromium", "channel": None, "user_agent": None},
        )
        for attempt in attempts:
            try:
                self._pw = sync_playwright().start()
                kwargs = {
                    "headless": self.config.headless,
                    "args": ["--disable-blink-features=AutomationControlled"],
                    "viewport": {"width": 1920, "height": 1080},
                    "locale": "zh-CN",
                }
                if attempt["channel"]:
                    kwargs["channel"] = attempt["channel"]
                if attempt["user_agent"]:
                    kwargs["user_agent"] = attempt["user_agent"]
                self._browser = self._pw.chromium.launch_persistent_context(data_dir, **kwargs)
                break
            except Exception as exc:
                # 启动失败会破坏该 Playwright 实例内部状态（greenlet/事件循环），
                # 必须销毁后重建，否则后续调用会抛 "Cannot switch to a different thread"
                first_error = exc
                self._stop_pw()
                print(f"[browser] 使用{attempt['label']}启动失败: {_brief(exc)}")
                if attempt["channel"]:
                    print("[browser] 降级为 Playwright chromium 重试...")
        else:
            raise BossBrowserError(
                "浏览器启动失败：browser_data/ 目录可能被残留的 Chrome 进程占用。\n"
                "请先关闭所有 Chrome 窗口/进程，或删除 browser_data/ 目录（会清除登录态）后重试。\n"
                f"原始错误: {first_error}"
            ) from first_error

        self._context = self._browser
        self._page = self._context.new_page()
        return self._page

    def close(self) -> None:
        self._dispose()

    def _dispose(self) -> None:
        """回收浏览器/Playwright 实例。幂等，任何异常路径都可安全调用。"""
        ctx, self._context = self._context, None
        if ctx is not None:
            try:
                ctx.close()
            except Exception:
                pass
        self._browser = None
        self._page = None
        self._stop_pw()

    def _stop_pw(self) -> None:
        """销毁 Playwright 实例（幂等），避免复用已损坏的 greenlet。"""
        pw, self._pw = self._pw, None
        if pw is not None:
            try:
                pw.stop()
            except Exception:
                pass

    # ---------- 登录与风控 ----------

    def ensure_logged_in(self, timeout_s: int = 0) -> bool:
        """登录入口：委托给 LoginManager。未登录则弹出扫码窗并阻塞等待人工扫码。"""
        from boss.login import LoginManager

        if timeout_s > 0:
            self.config.login_timeout = timeout_s
        return LoginManager(self.config, self).ensure_logged_in()

    def check_risk_popup(self) -> bool:
        """检测风险弹窗（滑块验证等）。返回 True 表示有风险弹窗。
        有弹窗时打印提示并等待用户人工处理完成后回车继续。"""
        page = self._page
        if not page or page.is_closed():
            return False
        try:
            body = page.locator("body").inner_text(timeout=2000)
        except Exception:
            return False
        if any(m in body for m in RISK_MARKERS):
            print(
                "[browser] ⚠ 检测到风险提示（可能为滑块验证）。"
                "请人工处理弹窗，完成后回车继续..."
            )
            try:
                input()
            except EOFError:
                pass
            time.sleep(2)
            return True
        return False

    # ---------- 人类化操作 ----------

    def human_delay(self, low: float = 1.5, high: float = 3.5) -> None:
        time.sleep(random.uniform(low, high))

    def human_type(self, page: Page, target, text: str) -> None:
        """逐字输入，模拟真人打字节奏。target 可为 CSS 选择器字符串或 Locator。"""
        locator = page.locator(target) if isinstance(target, str) else target
        locator.click()
        for ch in text:
            locator.press_sequentially(ch, delay=random.uniform(30, 120))

    def human_scroll(self, page: Page, delta: int = 300) -> None:
        page.mouse.wheel(0, delta)
        self.human_delay(0.3, 0.8)
