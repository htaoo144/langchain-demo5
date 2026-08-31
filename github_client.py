"""GitHub 资料拉取：通过 REST API 获取用户公开仓库与简介，供简历定制使用。"""
from dataclasses import dataclass, field

import requests

from config import Config

API_BASE = "https://api.github.com"


@dataclass
class RepoInfo:
    name: str
    description: str = ""
    language: str = ""
    topics: list[str] = field(default_factory=list)
    stars: int = 0
    forks: int = 0
    pushed_at: str = ""
    html_url: str = ""


@dataclass
class GitHubProfile:
    username: str
    bio: str = ""
    company: str = ""
    location: str = ""
    blog: str = ""
    public_repos: int = 0
    followers: int = 0
    repos: list[RepoInfo] = field(default_factory=list)

    def to_markdown(self, max_repos: int = 15) -> str:
        lines = [
            f"# GitHub 用户: {self.username}",
            f"- 简介: {self.bio or '无'}",
            f"- 公司: {self.company or '无'}",
            f"- 所在地: {self.location or '无'}",
            f"- 公开仓库数: {self.public_repos}，关注者: {self.followers}",
            "",
            "## 代表性仓库（按最近更新排序）",
        ]
        for repo in self.repos[:max_repos]:
            lines.append(
                f"- **{repo.name}** ({repo.language or '未知语言'}, ★{repo.stars}) "
                f"最近更新 {repo.pushed_at[:10]}\n"
                f"  描述: {repo.description or '无'} | 标签: {', '.join(repo.topics) or '无'}\n"
                f"  链接: {repo.html_url}"
            )
        return "\n".join(lines)


class GitHubClient:
    def __init__(self, config: Config):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "User-Agent": "job-agent/1.0",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )
        if config.github_token:
            self.session.headers["Authorization"] = f"Bearer {config.github_token}"

    def _get(self, url: str, params: dict | None = None) -> dict | list:
        resp = self.session.get(url, params=params, timeout=20)
        if resp.status_code == 404:
            raise ValueError(f"GitHub 资源不存在: {url}")
        if resp.status_code == 403:
            raise PermissionError(
                f"GitHub 限流或被拒绝（无 token 时匿名限流 60 次/小时），"
                f"可在 .env 中配置 GITHUB_TOKEN 解决。响应: {resp.text[:200]}"
            )
        resp.raise_for_status()
        return resp.json()

    def fetch_profile(self, max_repos: int = 30) -> GitHubProfile:
        user = self._get(f"{API_BASE}/users/{self.config.github_username}")
        repos = self._get(
            f"{API_BASE}/users/{self.config.github_username}/repos",
            params={"per_page": max_repos, "sort": "pushed", "page": 1},
        )
        repo_list = [
            RepoInfo(
                name=r["name"],
                description=r.get("description") or "",
                language=r.get("language") or "",
                topics=r.get("topics") or [],
                stars=r.get("stargazers_count") or 0,
                forks=r.get("forks_count") or 0,
                pushed_at=r.get("pushed_at") or "",
                html_url=r.get("html_url") or "",
            )
            for r in repos
            if not r.get("fork")  # 排除 fork 的仓库
        ]
        return GitHubProfile(
            username=self.config.github_username,
            bio=user.get("bio") or "",
            company=user.get("company") or "",
            location=user.get("location") or "",
            blog=user.get("blog") or "",
            public_repos=user.get("public_repos") or 0,
            followers=user.get("followers") or 0,
            repos=repo_list,
        )
