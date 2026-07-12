# -*- coding: utf-8 -*-
"""PreToolUse 훅: textbook_wiki repo(읽기 전용 참조)를 수정하는 도구 호출 차단.

- Write/Edit/NotebookEdit: 대상 경로가 위키 repo 안이면 거부
- Bash/PowerShell: 명령 문자열에 위키 repo 경로가 등장하면 거부
  (읽기도 셸 대신 Read/Grep/Glob 도구를 쓰면 되므로 일괄 차단)
"""
import json
import re
import sys

WIKI = re.compile(r"textbook_wiki(?=[/\\\s\"'`]|$)", re.I)


def deny(reason):
    # ensure_ascii=True(기본값) 유지 — Windows 콘솔 코드페이지와 무관하게
    # 항상 ASCII JSON이 나가야 Claude Code가 훅 출력을 안정적으로 파싱한다.
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)  # 입력 해석 불가 시 통과 (차단은 위키 경로 확인 시에만)
    tool = data.get("tool_name", "")
    ti = data.get("tool_input") or {}

    if tool in ("Write", "Edit", "NotebookEdit"):
        path = str(ti.get("file_path") or ti.get("notebook_path") or "")
        if WIKI.search(path):
            deny("textbook_wiki는 읽기 전용 참조입니다 — graph_apps에서 위키 repo 파일을 "
                 "수정할 수 없습니다 (.claude/hooks/block_wiki.py). 위키 수정은 "
                 "textbook_wiki 폴더에서 여세요.")
    elif tool in ("Bash", "PowerShell"):
        if WIKI.search(str(ti.get("command") or "")):
            deny("textbook_wiki를 참조하는 셸 명령은 차단됩니다 — 위키 읽기는 "
                 "Read/Grep/Glob 도구를 사용하세요 (.claude/hooks/block_wiki.py).")
    sys.exit(0)


if __name__ == "__main__":
    main()
