import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _env_bool(name: str, default: bool) -> bool:
    val = _env(name)
    if not val:
        return default
    return val.lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


@dataclass
class Config:
    # LLM
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # GitHub
    github_username: str = ""
    github_token: str = ""

    # Boss直聘
    boss_search_url: str = "https://www.zhipin.com/web/geek/job"
    headless: bool = False
    apply_auto: bool = True
    max_apply_per_run: int = 10
    match_threshold: float = 0.6
    greeting_max_len: int = 50
    default_city: str = "北京"
    login_timeout: int = 300

    # 简历
    initial_resume_path: str = "resume/initial_resume.pdf"

    # 运行期路径（派生）
    browser_data_dir: Path = field(default_factory=lambda: BASE_DIR / "browser_data")
    output_dir: Path = field(default_factory=lambda: BASE_DIR / "output")
    resume_dir: Path = field(default_factory=lambda: BASE_DIR / "resume")
    resume_output_dir: Path = field(default_factory=lambda: BASE_DIR / "output" / "resumes")

    def resolve(self) -> None:
        for d in (self.output_dir, self.resume_output_dir, self.resume_dir):
            d.mkdir(parents=True, exist_ok=True)
        self.initial_resume_path = str(
            Path(self.initial_resume_path)
            if Path(self.initial_resume_path).is_absolute()
            else BASE_DIR / self.initial_resume_path
        )

    def validate(self) -> list[str]:
        errors = []
        if not self.deepseek_api_key:
            errors.append("缺少 DEEPSEEK_API_KEY，请在 .env 中配置")
        if not self.github_username:
            errors.append("缺少 GITHUB_USERNAME，请在 .env 中配置")
        if not Path(self.initial_resume_path).exists():
            errors.append(f"初始简历不存在: {self.initial_resume_path}")
        return errors


def load_config() -> Config:
    cfg = Config(
        deepseek_api_key=_env("DEEPSEEK_API_KEY") or _env("OPENAI_API_KEY"),
        deepseek_base_url=_env("DEEPSEEK_BASE_URL")
        or _env("OPENAI_BASE_URL", "https://api.deepseek.com"),
        deepseek_model=_env("DEEPSEEK_MODEL", "deepseek-chat"),
        github_username=_env("GITHUB_USERNAME"),
        github_token=_env("GITHUB_TOKEN"),
        boss_search_url=_env("BOSS_SEARCH_URL", "https://www.zhipin.com/web/geek/job"),
        headless=_env_bool("HEADLESS", False),
        apply_auto=_env_bool("APPLY_AUTO", True),
        max_apply_per_run=_env_int("MAX_APPLY_PER_RUN", 10),
        match_threshold=_env_float("MATCH_THRESHOLD", 0.6),
        greeting_max_len=_env_int("GREETING_MAX_LEN", 50),
        default_city=_env("DEFAULT_CITY", "北京"),
        login_timeout=_env_int("LOGIN_TIMEOUT", 300),
        initial_resume_path=_env("INITIAL_RESUME_PATH", "resume/initial_resume.pdf"),
    )
    cfg.resolve()
    return cfg
