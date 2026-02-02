# -*- coding: utf-8 -*-
"""代码审查格式转换器 - 支持多平台"""

import json
import os
from typing import List, Dict, Any
from enum import Enum
from urllib.parse import quote

import requests

from biz.utils.log import logger


class PlatformType(Enum):
    """Git 平台类型"""
    GITLAB = "gitlab"
    GITHUB = "github"
    GITEA = "gitea"


class ReviewFormatConverter:
    """将 changes 列表转换为 AI 输入格式（包含 context）"""

    @staticmethod
    def convert_changes_to_ai_format(
        changes: List[Dict[str, Any]],
        platform: str,
        repo_info: Dict[str, Any],
        access_token: str
    ) -> str:
        """
        将 changes 列表转换为 JSON 格式（包含 context）

        Args:
            changes: 当前格式的 changes 列表
            platform: 平台类型 (gitlab/github/gitea)
            repo_info: 仓库信息
                - GitLab: {project_id, ref}
                - GitHub: {owner, repo, ref}
                - Gitea: {owner, repo, ref, gitea_url}
            access_token: 访问令牌

        Returns:
            JSON 格式的字符串
        """
        items = []

        # 根据平台创建对应的 API 客户端
        if platform == PlatformType.GITLAB.value:
            api_client = GitLabFileApi(repo_info['project_id'], access_token)
        elif platform == PlatformType.GITHUB.value:
            api_client = GitHubFileApi(repo_info['owner'], repo_info['repo'], access_token)
        elif platform == PlatformType.GITEA.value:
            api_client = GiteaFileApi(
                repo_info['owner'],
                repo_info['repo'],
                access_token,
                repo_info.get('gitea_url', os.getenv("GITEA_URL", "https://gitea.com"))
            )
        else:
            api_client = None

        for change in changes:
            file_path = change.get('new_path', '')
            # 通过 API 获取文件内容
            context = api_client.get_file_content(file_path, repo_info['ref']) if api_client else ""

            item = {
                "context": context,
                "diff": change.get('diff', ''),
                "filePath": file_path
            }
            items.append(item)

        return json.dumps(items, ensure_ascii=False)


class GitLabFileApi:
    """GitLab 文件 API 客户端"""

    def __init__(self, project_id: int, access_token: str):
        self.project_id = project_id
        self.access_token = access_token
        self.gitlab_url = os.getenv("GITLAB_URL", "https://gitlab.com")

    def get_file_content(self, file_path: str, ref: str) -> str:
        """获取文件内容"""
        # URL 编码文件路径
        encoded_path = quote(file_path, safe='')

        url = f"{self.gitlab_url}/api/v4/projects/{self.project_id}/repository/files/{encoded_path}/raw"
        params = {"ref": ref}
        headers = {"PRIVATE-TOKEN": self.access_token}

        try:
            response = requests.get(url, params=params, headers=headers, timeout=10)
            if response.status_code == 200:
                return response.text
            else:
                logger.warning(f"GitLab API 返回状态码 {response.status_code}，文件: {file_path}")
                return ""
        except Exception as e:
            logger.warning(f"GitLab API 请求失败: {e}，文件: {file_path}")
            return ""


class GitHubFileApi:
    """GitHub 文件 API 客户端"""

    def __init__(self, owner: str, repo: str, access_token: str):
        self.owner = owner
        self.repo = repo
        self.access_token = access_token
        self.github_url = os.getenv("GITHUB_URL", "https://api.github.com")

    def get_file_content(self, file_path: str, ref: str) -> str:
        """获取文件内容"""
        encoded_path = quote(file_path, safe='')

        url = f"{self.github_url}/repos/{self.owner}/{self.repo}/contents/{encoded_path}"
        params = {"ref": ref}
        headers = {
            "Authorization": f"token {self.access_token}",
            "Accept": "application/vnd.github.v3.raw"
        }

        try:
            response = requests.get(url, params=params, headers=headers, timeout=10)
            if response.status_code == 200:
                return response.text
            else:
                logger.warning(f"GitHub API 返回状态码 {response.status_code}，文件: {file_path}")
                return ""
        except Exception as e:
            logger.warning(f"GitHub API 请求失败: {e}，文件: {file_path}")
            return ""


class GiteaFileApi:
    """Gitea 文件 API 客户端"""

    def __init__(self, owner: str, repo: str, access_token: str, gitea_url: str):
        self.owner = owner
        self.repo = repo
        self.access_token = access_token
        self.gitea_url = gitea_url

    def get_file_content(self, file_path: str, ref: str) -> str:
        """获取文件内容"""
        encoded_path = quote(file_path, safe='')

        url = f"{self.gitea_url}/api/v1/repos/{self.owner}/{self.repo}/contents/{encoded_path}"
        params = {"ref": ref}
        headers = {
            "Authorization": f"token {self.access_token}",
            "Accept": "application/vnd.gitea.v1.raw"
        }

        try:
            response = requests.get(url, params=params, headers=headers, timeout=10)
            if response.status_code == 200:
                return response.text
            else:
                logger.warning(f"Gitea API 返回状态码 {response.status_code}，文件: {file_path}")
                return ""
        except Exception as e:
            logger.warning(f"Gitea API 请求失败: {e}，文件: {file_path}")
            return ""
