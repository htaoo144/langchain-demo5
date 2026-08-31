"""boss/browser + boss/login 模块示例：启动浏览器并确保登录。

说明：
- 首次运行会弹出浏览器窗口，请用 Boss直聘 App 扫码登录（登录态保存到 browser_data/，
  之后无需再扫码）；
- 登录超时时间取 .env 的 LOGIN_TIMEOUT。
运行: python example/4_login_example.py
"""
from _bootstrap import *  # noqa: F401

from boss.browser import BossBrowser
from config import load_config


def main() -> None:
    cfg = load_config()
    browser = BossBrowser(cfg)
    try:
        ok = browser.ensure_logged_in()
        print(f"\n登录结果: {'成功 ✓' if ok else '失败 ✗'}")
        if ok:
            print("已检测到登录态（Cookie/页面元素），可继续搜索与投递。")
    finally:
        browser.close()


if __name__ == "__main__":
    main()
