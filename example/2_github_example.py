"""github_client 模块示例：拉取我的 GitHub 资料（简介 + 仓库列表）。

说明：
- 无 GITHUB_TOKEN 时匿名调用 GitHub API，限流 60 次/小时（可能被共享 IP 耗尽）；
  遇到 403 限流错误时请在 .env 中配置 GITHUB_TOKEN。
运行: python example/2_github_example.py
"""
from _bootstrap import *  # noqa: F401

from config import load_config
from github_client import GitHubClient


def main() -> None:
    cfg = load_config()
    print(f"拉取 GitHub 用户资料: {cfg.github_username} ...")
    try:
        profile = GitHubClient(cfg).fetch_profile(max_repos=10)
    except Exception as exc:
        print(f"拉取失败: {exc}")
        print("提示: 在 .env 中配置 GITHUB_TOKEN 可解决限流问题。")
        return
    print(profile.to_markdown(max_repos=5))


if __name__ == "__main__":
    main()
