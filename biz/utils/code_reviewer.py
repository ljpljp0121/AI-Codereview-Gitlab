import abc
import os
import re
from typing import Dict, Any, List

import yaml
from jinja2 import Template

from biz.llm.factory import Factory
from biz.utils.log import logger
from biz.utils.token_util import count_tokens, truncate_text_by_tokens


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


class CodeReviewer(BaseReviewer):
    """代码 Diff 级别的审查"""

    def __init__(self):
        super().__init__("code_review_prompt")

    def review_and_strip_code(self, changes_text: str, commits_text: str = "") -> str:
        """
        Review判断changes_text超出取前REVIEW_MAX_TOKENS个token，超出则截断changes_text，
        调用review_code方法，返回review_result，如果review_result是markdown格式，则去掉头尾的```
        :param changes_text:
        :param commits_text:
        :return:
        """
        # 如果超长，取前REVIEW_MAX_TOKENS个token
        review_max_tokens = int(os.getenv("REVIEW_MAX_TOKENS", 10000))
        # 如果changes为空,打印日志
        if not changes_text:
            logger.info("代码为空, diffs_text = %", str(changes_text))
            return "代码为空"

        # 计算tokens数量，如果超过REVIEW_MAX_TOKENS，截断changes_text
        tokens_count = count_tokens(changes_text)
        if tokens_count > review_max_tokens:
            changes_text = truncate_text_by_tokens(changes_text, review_max_tokens)

        review_result = self.review_code(changes_text, commits_text).strip()
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
        match = re.search(r"问题级别[:：]\s*(P[0-4]|---)", review_text)
        return match.group(1) if match else "---"

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
        格式化代码审查输出

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
        # 计算注释比例
        total_lines = additions + deletions
        comment_ratio = (comment_lines / total_lines * 100) if total_lines > 0 else 0

        # 解析问题级别
        level = CodeReviewer.parse_review_level(review_result)

        # 分离审核概述和审核详情
        overview = ""
        details = ""
        if "## 审核概述" in review_result:
            parts = review_result.split("## 审核概述")
            if len(parts) > 1:
                remaining = parts[1]
                if "## 审核详情" in remaining:
                    overview_parts = remaining.split("## 审核详情")
                    overview = overview_parts[0].strip()
                    if len(overview_parts) > 1:
                        details = overview_parts[1].strip()
                else:
                    overview = remaining.strip()
        elif "审核概述" in review_result:
            parts = review_result.split("审核概述")
            if len(parts) > 1:
                remaining = parts[1]
                if "审核详情" in remaining:
                    overview_parts = remaining.split("审核详情")
                    overview = overview_parts[0].strip()
                    if len(overview_parts) > 1:
                        details = overview_parts[1].strip()
                else:
                    overview = remaining.strip()

        # 如果没有找到概述和详情，把整个结果作为详情
        if not overview and not details:
            details = review_result

        # 拼接输出
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

        if overview:
            output += f"审核概述\n{overview}\n\n"
        if details and not details.startswith("本次代码审查未发现问题"):
            output += f"审核详情\n{details}"

        return output

