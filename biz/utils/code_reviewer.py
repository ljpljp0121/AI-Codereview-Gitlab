import abc
import json
import os
import re
from typing import Dict, Any, List, Tuple, Optional

import yaml
from jinja2 import Template

from biz.entity.review_entity import IssueLevel, ReviewIssue, ParsedReviewResult
from biz.llm.factory import Factory
from biz.utils.log import logger
from biz.utils.token_util import count_tokens, truncate_text_by_tokens
from biz.utils.review_format_converter import ReviewFormatConverter


class BaseReviewer(abc.ABC):
    """代码审查基类"""

    def __init__(self, prompt_key: str):
        self.client = Factory().getClient()
        self.prompts = self._load_prompts(prompt_key, os.getenv("REVIEW_STYLE", "professional"))

    def _load_prompts(self, prompt_key: str, style="professional") -> Dict[str, Any]:
        """加载提示词配置"""
        prompt_templates_file = "conf/prompt_templates.yml"
        try:
            # 在打开 YAML 文件时显式指定编码为 UTF-8，避免使用系统默认的 GBK 编码。
            with open(prompt_templates_file, "r", encoding="utf-8") as file:
                prompts = yaml.safe_load(file).get(prompt_key, {})

                # 使用Jinja2渲染模板
                def render_template(template_str: str) -> str:
                    return Template(template_str).render(style=style)

                system_prompt = render_template(prompts["system_prompt"])
                user_prompt = render_template(prompts["user_prompt"])

                return {
                    "system_message": {"role": "system", "content": system_prompt},
                    "user_message": {"role": "user", "content": user_prompt},
                }
        except (FileNotFoundError, KeyError, yaml.YAMLError) as e:
            logger.error(f"加载提示词配置失败: {e}")
            raise Exception(f"提示词配置加载失败: {e}")

    def call_llm(self, messages: List[Dict[str, Any]]) -> str:
        """调用 LLM 进行代码审核"""
        logger.info(f"向 AI 发送代码 Review 请求, messages: {messages}")
        review_result = self.client.completions(messages=messages)
        logger.info(f"收到 AI 返回结果: {review_result}")
        return review_result

    @abc.abstractmethod
    def review_code(self, *args, **kwargs) -> str:
        """抽象方法，子类必须实现"""
        pass


class ReviewResultParser:
    """AI 审核结果解析器 - 新格式"""

    # 新格式正则表达式
    PATTERN_FILE_PATH = re.compile(r'代码文件全路径名[:：]\s*(.+?)(?:\n|$)')
    PATTERN_ISSUE_LEVEL = re.compile(r'问题级别[:：]\s*(P[0-3]|---)')
    PATTERN_DEFECT_CODE = re.compile(r'异常代码[:：]\s*\n(.+?)(?=异常描述：|问题级别：|代码文件全路径名：|\Z)', re.DOTALL)
    PATTERN_ISSUE_DESCRIPTION = re.compile(r'异常描述[:：]\s*\n(.+?)(?=问题级别：|问题分类：|解决方案：|代码文件全路径名：|\Z)', re.DOTALL)
    PATTERN_ISSUE_CATEGORY = re.compile(r'问题分类[:：]\s*(.+?)(?:\n|$)')
    PATTERN_SOLUTION = re.compile(r'解决方案[:：]\s*\n(.+?)(?=代码文件全路径名：|-----------------------------|\Z)', re.DOTALL)

    def __init__(self):
        self.parse_errors = []

    def parse_review_result(self, review_text: str) -> ParsedReviewResult:
        """解析新格式的 AI 审核结果"""
        result = ParsedReviewResult(raw_text=review_text)

        if not review_text or not review_text.strip():
            result.overview = "审核结果为空"
            return result

        # 提取概述（分隔符前的内容）
        overview = self._extract_overview(review_text)
        result.overview = overview

        # 检查是否无问题
        if self._is_no_issues(review_text):
            if not result.overview:
                result.overview = "代码质量优秀，无任何明显代码异常错误、性能安全、代码规范等问题。"
            return result

        # 按分隔符分块解析问题
        blocks = re.split(r'-{30,}', review_text)
        for block in blocks:
            if '代码文件全路径名' in block:
                issue = self._parse_single_issue(block.strip())
                if issue and issue.is_valid():
                    result.issues.append(issue)

        return result

    def _extract_overview(self, text: str) -> str:
        """提取概述部分"""
        lines = text.strip().split('\n')
        overview_lines = []
        for line in lines:
            if '代码文件全路径名' in line:
                break
            if line.strip():
                overview_lines.append(line)
        return '\n'.join(overview_lines).strip()

    def _is_no_issues(self, text: str) -> bool:
        """检查是否无问题"""
        return bool(re.search(r'代码质量优秀|无任何明显|审核总览', text))

    def _parse_single_issue(self, block: str) -> Optional[ReviewIssue]:
        """解析单个问题块"""
        issue = ReviewIssue(raw_text=block)

        # 提取各字段
        match = self.PATTERN_FILE_PATH.search(block)
        issue.file_name = match.group(1).strip() if match else "未知文件"

        match = self.PATTERN_DEFECT_CODE.search(block)
        issue.defect_code = match.group(1).strip() if match else ""

        match = self.PATTERN_ISSUE_DESCRIPTION.search(block)
        issue.issue_description = match.group(1).strip() if match else ""

        match = self.PATTERN_ISSUE_LEVEL.search(block)
        if match:
            try:
                issue.issue_level = IssueLevel(match.group(1))
            except ValueError:
                issue.issue_level = IssueLevel.P3

        match = self.PATTERN_ISSUE_CATEGORY.search(block)
        issue.category = match.group(1).strip() if match else ""

        match = self.PATTERN_SOLUTION.search(block)
        issue.suggestion = match.group(1).strip() if match else ""

        return issue if issue.is_valid() else None


class CodeReviewer(BaseReviewer):
    """代码 Diff 级别的审查"""

    # 创建解析器实例（类级别的单例）
    _parser = ReviewResultParser()

    def __init__(self):
        super().__init__("code_review_prompt")

    @classmethod
    def parse_review_result_structured(cls, review_text: str) -> ParsedReviewResult:
        """解析 AI 审核结果为结构化数据"""
        return cls._parser.parse_review_result(review_text)

    def review_and_strip_code(
        self,
        changes_text: str,
        commits_text: str = "",
        platform: str = None,
        repo_info: Dict[str, Any] = None,
        access_token: str = None
    ) -> str:
        """
        Review判断changes_text超出取前REVIEW_MAX_TOKENS个token，超出则截断changes_text，
        调用review_code方法，返回review_result，如果review_result是markdown格式，则去掉头尾的```

        :param changes_text: 代码变更内容（列表的字符串表示）
        :param commits_text: 提交信息
        :param platform: 平台类型 (gitlab/github/gitea)
        :param repo_info: 仓库信息
        :param access_token: 访问令牌
        :return: 审核结果
        """
        # 如果超长，取前REVIEW_MAX_TOKENS个token
        review_max_tokens = int(os.getenv("REVIEW_MAX_TOKENS", 10000))
        # 如果changes为空,打印日志
        if not changes_text:
            logger.info("代码为空, diffs_text = %", str(changes_text))
            return "代码为空"

        # 将字符串转换为列表
        changes = eval(changes_text)

        # 将 changes 转换为 JSON 格式（包含 context）
        if platform and repo_info and access_token:
            changes_json = ReviewFormatConverter.convert_changes_to_ai_format(
                changes, platform, repo_info, access_token
            )
        else:
            # 没有凭证时，context 留空
            items = [
                {"context": "", "diff": c.get('diff', ''), "filePath": c.get('new_path', '')}
                for c in changes
            ]
            changes_json = json.dumps(items, ensure_ascii=False)

        # 计算tokens数量，如果超过REVIEW_MAX_TOKENS，截断changes_json
        tokens_count = count_tokens(changes_json)
        if tokens_count > review_max_tokens:
            changes_json = truncate_text_by_tokens(changes_json, review_max_tokens)

        review_result = self.review_code(changes_json, commits_text).strip()
        if review_result.startswith("```markdown") and review_result.endswith("```"):
            return review_result[11:-3].strip()
        return review_result

    def review_code(self, diffs_text: str, commits_text: str = "") -> str:
        """Review 代码并返回结果"""
        messages = [
            self.prompts["system_message"],
            {
                "role": "user",
                "content": self.prompts["user_message"]["content"].format(
                    diffs_text=diffs_text, commits_text=commits_text
                ),
            },
        ]
        return self.call_llm(messages)

    @staticmethod
    def parse_review_level(review_text: str) -> str:
        """解析 AI 返回的 Review 结果，返回问题级别"""
        if not review_text:
            return "---"
        # 使用结构化解析获取最高级别
        parsed = CodeReviewer.parse_review_result_structured(review_text)
        return parsed.max_issue_level.value

    @staticmethod
    def parse_review_score(review_text: str) -> int:
        """解析 AI 返回的 Review 结果，返回评分（保留兼容性）"""
        if not review_text:
            return 0
        match = re.search(r"总分[:：]\s*(\d+)分?", review_text)
        return int(match.group(1)) if match else 0

    @staticmethod
    def format_review_output(
        project_name: str,
        author: str,
        branch: str,
        additions: int,
        deletions: int,
        comment_lines: int,
        total_files: int,
        filtered_files: int,
        abnormal_files: int,
        normal_files: int,
        commit_message: str,
        review_result: str,
    ) -> str:
        """
        格式化代码审查输出（增强版 - 使用结构化解析）

        Args:
            project_name: 项目名称
            author: 操作人员
            branch: 分支名称
            additions: 新增行数
            deletions: 删减行数
            comment_lines: 注释行数
            total_files: 本次提交文件数量
            filtered_files: 审核过滤文件数量
            abnormal_files: 代码异常文件数量
            normal_files: 代码正常文件数量
            commit_message: 提交消息
            review_result: AI 审核结果

        Returns:
            格式化后的输出字符串
        """
        # 使用结构化解析
        parsed = CodeReviewer.parse_review_result_structured(review_result)

        # 计算注释比例
        total_lines = additions + deletions
        comment_ratio = (comment_lines / total_lines * 100) if total_lines > 0 else 0

        # 使用解析后的级别
        level = parsed.max_issue_level.value

        # 拼接统计信息头部
        output = f"""项目名称：{project_name}
操作人员：@{author}
分支名称：{branch}
新增行数：{additions}
删减行数：{deletions}
注释行数：{comment_lines}
注释比例：{comment_ratio:.2f}%
本次提交文件数量：{total_files}
审核过滤文件数量：{filtered_files}
代码异常文件数量：{abnormal_files}
代码正常文件数量：{normal_files}
问题级别：{level}
提交消息
{commit_message}

"""

        if parsed.overview:
            output += f"审核概述\n{parsed.overview}\n\n"

        if parsed.issues:
            output += f"审核详情\n"
            for issue in parsed.issues:
                output += "\n" + issue.to_markdown() + "\n" + "-" * 50 + "\n"

        return output

