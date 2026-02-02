# -*- coding: utf-8 -*-
"""
AI 审核结果结构化解析器测试脚本
测试各种 AI 输出格式的解析能力
"""

import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from biz.utils.code_reviewer import ReviewResultParser
from biz.entity.review_entity import IssueLevel


def print_separator(title=""):
    """打印分隔线"""
    if title:
        print(f"\n{'=' * 60}")
        print(f"  {title}")
        print('=' * 60)
    else:
        print('-' * 60)


def test_case_1_standard_format():
    """测试用例1：标准格式"""
    print_separator("测试用例1: 标准格式")

    review_text = """
## 审核概述
本次提交存在2个代码质量问题，包括1个P1级别的空引用风险和1个P3级别的命名规范问题。

## 审核详情
文件名称: Assets/Scripts/Player/PlayerController.cs
问题级别: P1
缺陷代码:
```csharp
private Rigidbody rb;
void Start() {
    rb.velocity = new Vector3(1, 0, 0); // 未检查rb是否为空
}
```
异常描述:
在Start方法中直接使用rb组件，但没有通过GetComponent或SerializeField初始化，可能导致NullReferenceException。
温馨提示: 建议添加 [SerializeField] private Rigidbody rb; 并在Inspector中赋值

文件名称: Assets/Scripts/Utils/Helper.cs
问题级别: P3
缺陷代码:
```csharp
public class helper {
    public void DoStuff() {}
}
```
异常描述:
类名不符合C#命名规范，应该使用PascalCase。
温馨提示: 将类名改为 Helper
"""

    parser = ReviewResultParser()
    result = parser.parse_review_result(review_text)

    print(f"概述: {result.overview}")
    print(f"问题数量: {len(result.issues)}")
    print(f"最高问题级别: {result.max_issue_level.value}")

    for i, issue in enumerate(result.issues, 1):
        print(f"\n问题 {i}:")
        print(f"  文件名称: {issue.file_name}")
        print(f"  问题级别: {issue.issue_level.value}")
        defect_preview = issue.defect_code[:50] + "..." if len(issue.defect_code) > 50 else issue.defect_code
        print(f"  缺陷代码: {defect_preview}")
        desc_preview = issue.issue_description[:50] + "..." if len(issue.issue_description) > 50 else issue.issue_description
        print(f"  异常描述: {desc_preview}")

    # 验证结果
    assert len(result.issues) == 2, f"期望2个问题，实际{len(result.issues)}个"
    assert result.issues[0].issue_level == IssueLevel.P1, "第一个问题应该是P1"
    assert result.issues[0].file_name == "Assets/Scripts/Player/PlayerController.cs"
    assert "NullReferenceException" in result.issues[0].issue_description

    print("\n✅ 测试用例1 通过")
    return True


def test_case_2_no_issues():
    """测试用例2：无问题情况"""
    print_separator("测试用例2: 无问题情况")

    review_text = """
## 审核概述
本次代码审查未发现问题，代码质量良好。

## 审核详情
本次代码审查未发现问题，代码质量良好。
"""

    parser = ReviewResultParser()
    result = parser.parse_review_result(review_text)

    print(f"概述: {result.overview}")
    print(f"问题数量: {len(result.issues)}")
    print(f"最高问题级别: {result.max_issue_level.value}")

    assert len(result.issues) == 0, "无问题情况下issues应该为空"
    assert "未发现问题" in result.overview or "代码质量良好" in result.overview

    print("\n✅ 测试用例2 通过")
    return True


def test_case_3_missing_file_name():
    """测试用例3：文件名称缺失（容错）"""
    print_separator("测试用例3: 文件名称缺失（容错）")

    review_text = """
## 审核概述
发现1个性能问题。

## 审核详情
问题级别: P2
缺陷代码:
```csharp
void Update() {
    GameObject.Find("Player"); // 每帧查找
}
```
异常描述:
在Update中每帧使用GameObject.Find会造成严重性能问题。
温馨提示: 缓存Player的引用或使用单例模式
"""

    parser = ReviewResultParser()
    result = parser.parse_review_result(review_text)

    print(f"概述: {result.overview}")
    print(f"问题数量: {len(result.issues)}")

    if result.issues:
        issue = result.issues[0]
        print(f"文件名称: {issue.file_name} (应该是'未知文件')")
        print(f"问题级别: {issue.issue_level.value}")
        assert issue.file_name == "未知文件", "缺失文件名时应使用默认值"

    print("\n✅ 测试用例3 通过")
    return True


def test_case_4_alternative_code_format():
    """测试用例4：缺陷代码使用替代格式"""
    print_separator("测试用例4: 缺陷代码使用替代格式（无代码块）")

    review_text = """
## 审核概述
存在1个代码规范问题。

## 审核详情
文件名称: Assets/Scripts/GameManager.cs
问题级别: P4
缺陷代码:
public int score;void SetScore(int s){score=s;}
异常描述:
代码格式不规范，缺少换行和空格。
温馨提示: 遵循C#代码格式规范
"""

    parser = ReviewResultParser()
    result = parser.parse_review_result(review_text)

    print(f"问题数量: {len(result.issues)}")

    if result.issues:
        issue = result.issues[0]
        print(f"文件名称: {issue.file_name}")
        print(f"缺陷代码: {issue.defect_code[:50]}...")
        assert issue.file_name == "Assets/Scripts/GameManager.cs"
        assert issue.issue_level == IssueLevel.P4

    print("\n✅ 测试用例4 通过")
    return True


def test_case_5_empty_result():
    """测试用例5：空结果"""
    print_separator("测试用例5: 空结果")

    parser = ReviewResultParser()
    result = parser.parse_review_result("")

    print(f"概述: {result.overview}")
    assert result.overview == "审核结果为空", "空结果应返回特定提示"
    assert len(result.issues) == 0

    print("\n✅ 测试用例5 通过")
    return True


def test_case_6_format_review_output():
    """测试用例6：完整格式化输出"""
    print_separator("测试用例6: format_review_output 方法")

    review_text = """
## 审核概述
本次提交存在1个P0级别严重问题。

## 审核详情
文件名称: Assets/Scripts/Core/BattleSystem.cs
问题级别: P0
缺陷代码:
```csharp
void DealDamage(int damage) {
    playerHealth -= damage; // 可能为负
}
```
异常描述:
没有验证damage参数的有效性，可能导致玩家血量异常。
温馨提示: 添加damage参数验证，确保为正数
"""

    from biz.utils.code_reviewer import CodeReviewer

    output = CodeReviewer.format_review_output(
        project_name="UnityGame",
        author="developer",
        branch="feature/battle-system",
        additions=150,
        deletions=50,
        comment_lines=30,
        total_files=5,
        filtered_files=1,
        abnormal_files=1,
        normal_files=3,
        commit_message="实现战斗系统",
        review_result=review_text
    )

    print("\n格式化输出结果:")
    print(output)

    assert "UnityGame" in output
    assert "developer" in output
    assert "P0" in output
    assert "BattleSystem.cs" in output

    print("\n✅ 测试用例6 通过")
    return True


def run_all_tests():
    """运行所有测试"""
    print_separator("开始测试 AI 审核结果结构化解析器")

    tests = [
        test_case_1_standard_format,
        test_case_2_no_issues,
        test_case_3_missing_file_name,
        test_case_4_alternative_code_format,
        test_case_5_empty_result,
        test_case_6_format_review_output,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            failed += 1
            print(f"\n❌ {test.__name__} 失败: {e}")
            import traceback
            traceback.print_exc()

    print_separator("测试结果汇总")
    print(f"总计: {len(tests)} 个测试")
    print(f"通过: {passed} 个 ✅")
    print(f"失败: {failed} 个 ❌")

    return failed == 0


if __name__ == "__main__":
    # 设置 UTF-8 编码输出
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    success = run_all_tests()
    sys.exit(0 if success else 1)
