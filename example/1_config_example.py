"""config 模块示例：加载 .env 配置并校验。

运行: python example/1_config_example.py
"""
from _bootstrap import *  # noqa: F401

from config import load_config


def main() -> None:
    cfg = load_config()
    print("== 配置总览 ==")
    print(f"LLM:      {cfg.deepseek_model} @ {cfg.deepseek_base_url} (key: {'已配置' if cfg.deepseek_api_key else '缺失'})")
    print(f"GitHub:   {cfg.github_username} (token: {'已配置' if cfg.github_token else '未配置(仅读公开仓库)'})")
    print(f"Boss:     {cfg.boss_search_url}")
    print(f"投递上限: {cfg.max_apply_per_run} | 匹配阈值: {cfg.match_threshold} | 打招呼≤{cfg.greeting_max_len}字 | 自动投递: {cfg.apply_auto}")
    print(f"城市:     {cfg.default_city} | 登录超时: {cfg.login_timeout}s")
    print(f"简历:     {cfg.initial_resume_path}")

    errors = cfg.validate()
    if errors:
        print("\n== 配置校验未通过 ==")
        for e in errors:
            print(f"  - {e}")
    else:
        print("\n配置校验通过。")


if __name__ == "__main__":
    main()
