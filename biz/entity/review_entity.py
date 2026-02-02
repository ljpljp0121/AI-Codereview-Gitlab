from dataclasses import dataclass, field
from enum import Enum
from typing import List


class IssueLevel(Enum):
    """问题级别枚举"""
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"
    NONE = "---"


@dataclass
class ReviewIssue:
    """单个审核问题的数据结构"""
    file_name: str = "未知文件"
    issue_level: IssueLevel = IssueLevel.NONE
    defect_code: str = ""
    issue_description: str = ""
    suggestion: str = ""
    raw_text: str = ""

    def is_valid(self) -> bool:
        """检查问题是否有效"""
        return bool(self.issue_description or self.defect_code)

    def to_markdown(self) -> str:
        """转换为 Markdown 格式"""
        output = f"文件名称: {self.file_name}\n"
        output += f"问题级别: {self.issue_level.value}\n"
        if self.defect_code:
            output += f"缺陷代码:\n{self.defect_code}\n"
        if self.issue_description:
            output += f"异常描述:\n{self.issue_description}\n"
        if self.suggestion:
            output += f"温馨提示: {self.suggestion}\n"
        return output


@dataclass
class ParsedReviewResult:
    """解析后的完整审核结果"""
    overview: str = ""
    issues: List[ReviewIssue] = field(default_factory=list)
    raw_text: str = ""
    parse_errors: List[str] = field(default_factory=list)

    @property
    def max_issue_level(self) -> IssueLevel:
        """获取最高问题级别"""
        if not self.issues:
            return IssueLevel.NONE
        level_order = [IssueLevel.P0, IssueLevel.P1, IssueLevel.P2, IssueLevel.P3, IssueLevel.P4, IssueLevel.NONE]
        for level in level_order:
            if any(issue.issue_level == level for issue in self.issues):
                return level
        return IssueLevel.NONE


class MergeRequestReviewEntity:
    def __init__(self, project_name: str, author: str, source_branch: str, target_branch: str, updated_at: int,
                 commits: list, score: float, url: str, review_result: str, url_slug: str, webhook_data: dict,
                 additions: int, deletions: int, last_commit_id: str):
        self.project_name = project_name
        self.author = author
        self.source_branch = source_branch
        self.target_branch = target_branch
        self.updated_at = updated_at
        self.commits = commits
        self.score = score
        self.url = url
        self.review_result = review_result
        self.url_slug = url_slug
        self.webhook_data = webhook_data
        self.additions = additions
        self.deletions = deletions
        self.last_commit_id = last_commit_id

    @property
    def commit_messages(self):
        # 合并所有 commit 的 message 属性，用分号分隔
        return "; ".join(commit["message"].strip() for commit in self.commits)


class PushReviewEntity:
    def __init__(self, project_name: str, author: str, branch: str, updated_at: int, commits: list, score: float,
                 review_result: str, url_slug: str, webhook_data: dict, additions: int, deletions: int):
        self.project_name = project_name
        self.author = author
        self.branch = branch
        self.updated_at = updated_at
        self.commits = commits
        self.score = score
        self.review_result = review_result
        self.url_slug = url_slug
        self.webhook_data = webhook_data
        self.additions = additions
        self.deletions = deletions

    @property
    def commit_messages(self):
        # 合并所有 commit 的 message 属性，用分号分隔
        return "; ".join(commit["message"].strip() for commit in self.commits)

