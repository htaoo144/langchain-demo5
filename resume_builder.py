"""简历流水线：提取初始 PDF 文本 → LLM 按岗位要求定制 → 渲染输出 PDF。

同时提供：岗位匹配度打分、≤50字打招呼语生成。
"""
import re
from pathlib import Path

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from pypdf import PdfReader
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from config import Config


# ---------- 结构化输出模型 ----------

class TailoredResume(BaseModel):
    """针对单个岗位定制的完整简历内容。"""
    target_job: str = Field(..., description="目标职位名称")
    summary: str = Field(..., description="2~3句个人简介，突出与岗位匹配的技术栈")
    skills: list[str] = Field(..., description="按岗位相关性排序的技能列表（6~10项）")
    projects: list[str] = Field(..., description="项目经历（3~4条），每条基于 GitHub 仓库改写，突出与岗位要求匹配的关键词")
    experience: list[str] = Field(..., description="工作/实习经历（无则空列表）")
    education: list[str] = Field(..., description="教育经历")
    greeting: str = Field(..., description=f"给 HR 的打招呼语，不得超过50字，含个人信息，不得有换行")


class MatchScore(BaseModel):
    score: float = Field(..., ge=0, le=1, description="匹配度 0~1")
    reason: str = Field(..., description="一句话说明打分依据")


# ---------- 工具 ----------

def extract_pdf_text(path: str | Path) -> str:
    reader = PdfReader(str(path))
    parts = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    text = "\n".join(parts)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        raise ValueError(f"无法从 PDF 提取文本（可能是扫描件）: {path}")
    return text


def render_markdown_to_pdf(markdown_text: str, out_path: Path, title: str = "") -> Path:
    """将 Markdown 渲染为 PDF（reportlab，内置中文字体 STSong-Light，无需系统依赖）。"""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        title=title or "简历",
    )
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("H1", parent=styles["Title"], fontName="STSong-Light", fontSize=16, spaceAfter=8)
    h2 = ParagraphStyle(
        "H2", parent=styles["Heading2"], fontName="STSong-Light", fontSize=13,
        textColor="#0b57d0", spaceBefore=10, spaceAfter=4,
    )
    body = ParagraphStyle("Body", parent=styles["BodyText"], fontName="STSong-Light", fontSize=10.5, leading=16)

    story = []
    for line in markdown_text.splitlines():
        line = line.rstrip()
        if not line.strip():
            continue
        if line.startswith("## "):
            story.append(Paragraph(_escape(line[3:]), h2))
        elif line.startswith("# "):
            story.append(Paragraph(_escape(line[2:]), h1))
        elif line.startswith("- ") or line.startswith("* "):
            story.append(Paragraph("• " + _escape(line[2:]), body))
        elif re.match(r"^\d+\. ", line):
            story.append(Paragraph(_escape(re.sub(r"^\d+\. ", "", line)), body))
        else:
            story.append(Paragraph(_escape(line), body))
        story.append(Spacer(1, 2))
    doc.build(story)
    return out_path


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _tailored_resume_to_markdown(r: TailoredResume) -> str:
    lines = [
        f"# 简历 — {r.target_job}",
        "## 个人简介",
        r.summary,
        "## 技能",
    ]
    lines += [f"- {s}" for s in r.skills]
    lines.append("## 项目经历")
    lines += [f"- {p}" for p in r.projects]
    if r.experience:
        lines.append("## 工作/实习经历")
        lines += [f"- {e}" for e in r.experience]
    lines.append("## 教育经历")
    lines += [f"- {e}" for e in r.education]
    return "\n".join(lines)


def _make_model(config: Config) -> ChatOpenAI:
    return ChatOpenAI(
        model=config.deepseek_model,
        base_url=config.deepseek_base_url,
        api_key=config.deepseek_api_key,
        temperature=0.3,
        max_tokens=4096,
        timeout=90,
    )


# ---------- 核心类 ----------

class ResumeBuilder:
    """根据岗位要求 + 初始简历 + GitHub 资料，定制简历与打招呼语。"""

    TAILOR_PROMPT = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """你是资深求职简历优化师。根据【岗位要求】【我的简历】【我的GitHub项目】三份材料，
为指定岗位定制一份简历。原则：
1. 忠实于我的真实经历，不得虚构学历、公司、岗位；
2. 项目经历改写自 GitHub 仓库，突出与岗位要求匹配的技术栈、框架、量化成果；
3. 技能按岗位相关度排序；
4. 打招呼语不超过50字，包含姓名/技术栈亮点，用于 Boss直聘首条消息，不得有换行。

输出必须是一个合法的 JSON 对象，字段与结构必须严格符合以下示例（不要输出任何其他文字）：
{{
  "target_job": "目标职位名称（字符串）",
  "summary": "2~3句个人简介（字符串）",
  "skills": ["技能1", "技能2", "技能3"],
  "projects": ["项目经历1（字符串）", "项目经历2（字符串）", "项目经历3（字符串）"],
  "experience": ["工作或实习经历1（没有则为空列表 []）"],
  "education": ["教育经历1（字符串）"],
  "greeting": "不超过50字的打招呼语（字符串）"
}}""",
            ),
            ("human", "【岗位要求】\n{jd}\n\n【我的简历】\n{resume}\n\n【我的GitHub项目】\n{github}\n\n请输出定制结果。\n{correction}"),
        ]
    ).partial(correction="")

    MATCH_PROMPT = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """你是招聘匹配评估专家。根据求职者简历与岗位要求，评估匹配度。
评分考虑：技能重叠度、经验年限、行业背景。
输出必须是一个合法的 JSON 对象，字段与结构必须严格符合以下示例（不要输出任何其他文字）：
{{
  "score": 0.0,
  "reason": "一句话说明打分依据"
}}
score 取值范围 0~1。""",
            ),
            ("human", "【岗位要求】\n{jd}\n\n【我的简历】\n{resume}\n\n输出匹配度评分。\n{correction}"),
        ]
    ).partial(correction="")

    def __init__(self, config: Config):
        self.config = config
        self.model = _make_model(config)
        self._resume_text: str | None = None

    def load_resume(self) -> str:
        if self._resume_text is None:
            self._resume_text = extract_pdf_text(self.config.initial_resume_path)
        return self._resume_text

    def tailor(
        self,
        jd: str,
        github_markdown: str,
        company: str = "",
        job_title: str = "",
    ) -> tuple[TailoredResume, Path]:
        """定制简历。返回 (结构化结果, 生成的 PDF 路径)。

        DeepSeek 官方 API 不支持 json_schema 类型的 response_format，
        因此统一使用 json_mode（response_format={"type":"json_object"}）并显式要求 JSON 输出。
        """
        resume_text = self.load_resume()
        chain = self.TAILOR_PROMPT | self.model.with_structured_output(
            TailoredResume, method="json_mode"
        )
        result: TailoredResume = self._invoke_structured(
            chain, {"jd": jd, "resume": resume_text, "github": github_markdown}
        )
        result.greeting = result.greeting.replace("\n", "").replace("\r", "").strip()
        if len(result.greeting) > self.config.greeting_max_len:
            result.greeting = result.greeting[: self.config.greeting_max_len]

        safe_company = re.sub(r"[\\/:*?\"<>|\s]+", "_", company or result.target_job)
        safe_title = re.sub(r"[\\/:*?\"<>|\s]+", "_", job_title or result.target_job)
        md = _tailored_resume_to_markdown(result)
        out_dir = self.config.resume_output_dir
        out_pdf = out_dir / f"{safe_company}_{safe_title}.pdf"
        out_md = out_dir / f"{safe_company}_{safe_title}.md"
        out_md.write_text(md, encoding="utf-8")
        render_markdown_to_pdf(md, out_pdf, title=f"简历-{result.target_job}")
        return result, out_pdf

    def match_score(self, jd: str) -> tuple[float, str]:
        """评估岗位匹配度，返回 (分数, 理由)。"""
        resume_text = self.load_resume()
        chain = self.MATCH_PROMPT | self.model.with_structured_output(
            MatchScore, method="json_mode"
        )
        result: MatchScore = self._invoke_structured(
            chain, {"jd": jd, "resume": resume_text}
        )
        return result.score, result.reason

    def _invoke_structured(self, chain, inputs: dict):
        """调用结构化输出链。json_mode 下模型可能不遵循 schema，
        解析失败时带错误信息重试一次；仍失败则抛出异常。"""
        try:
            return chain.invoke(inputs)
        except Exception as first_exc:
            msg = str(first_exc)[:500]
            print(f"[resume] 结构化输出解析失败，重试一次: {msg}")
            return chain.invoke(
                {**inputs, "correction": f"上一次输出未通过校验，请严格按要求的 JSON 结构重新输出。错误信息: {msg}"}
            )
