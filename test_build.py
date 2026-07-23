# -*- coding: utf-8 -*-
"""build.py의 config 검증 규칙 단위 테스트 (Playwright 불필요 — py test_build.py).

확인 항목:
  validate() — 타입·enum·모드별 필수/금지 필드
  find_duplicates() — slug·title 유일성
  config.schema.json — build.py 상수와의 드리프트 감지 (스키마 문서가 곧 검증 규칙)
"""
import json
import sys
from pathlib import Path

import build

ROOT = Path(__file__).parent


def base(**over):
    """검증을 통과하는 최소 고정 x config. over로 필드를 덮거나 None으로 제거."""
    cfg = {
        "slug": "spring_test", "title": "테스트 실험", "grade": "중1",
        "xLabel": "늘어난 길이", "xUnit": "cm", "yLabel": "힘", "yUnit": "N",
        "xValues": [5, 10, 15], "trendline": "proportional", "yMaxHint": 10,
    }
    for k, v in over.items():
        if v is None:
            cfg.pop(k, None)
        else:
            cfg[k] = v
    return cfg


def errs(cfg):
    return "\n".join(build.validate(cfg["slug"], cfg))


def test_valid_fixed_passes():
    assert errs(base()) == ""


def test_valid_free_passes():
    cfg = base(entryMode="free", xMaxHint=20, maxPoints=5, xValues=None)
    assert errs(cfg) == ""


def test_grade_enum():
    assert "grade" in errs(base(grade="고1"))
    assert "grade" in errs(base(grade=1))


def test_yMaxHint_number():
    assert "yMaxHint" in errs(base(yMaxHint="10"))


def test_xMaxHint_number():
    cfg = base(entryMode="free", xValues=None, xMaxHint="20")
    assert "xMaxHint" in errs(cfg)


def test_maxPoints_positive_int():
    cfg = base(entryMode="free", xValues=None, xMaxHint=20)
    assert "maxPoints" in errs({**cfg, "maxPoints": 0})
    assert "maxPoints" in errs({**cfg, "maxPoints": "5"})


def test_groupNames_string_list():
    assert "groupNames" in errs(base(groupNames="1조"))
    assert "groupNames" in errs(base(groupNames=[1, 2]))
    assert errs(base(groupNames=["A반", "B반"])) == ""


def test_unknown_field_rejected():
    assert "trendine" in errs(base(trendine="linear"))   # 오타 필드 감지


def test_duplicate_slug():
    probs = "\n".join(build.find_duplicates([base(), base(title="다른 제목")]))
    assert "slug" in probs


def test_duplicate_title():
    probs = "\n".join(build.find_duplicates(
        [base(), base(slug="spring_test2")]))
    assert "title" in probs


def test_no_duplicates():
    assert build.find_duplicates(
        [base(), base(slug="other", title="다른 제목")]) == []


def test_schema_matches_build():
    """config.schema.json이 build.py 검증 규칙과 어긋나면 실패 (드리프트 감지)."""
    schema = json.loads((ROOT / "config.schema.json").read_text(encoding="utf-8"))
    assert set(schema["required"]) == set(build.REQUIRED) - {"xValues"}
    props = schema["properties"]
    assert set(props) == set(build.KNOWN_FIELDS)
    assert set(props["trendline"]["enum"]) == set(build.TRENDLINES)
    assert set(props["grade"]["enum"]) == set(build.GRADE_ORDER)
    # 조건부 필수: free면 xMaxHint, 아니면 xValues
    conds = schema.get("allOf", [])
    assert any(c.get("then", {}).get("required") == ["xMaxHint"] for c in conds)
    assert any(c.get("else", {}).get("required") == ["xValues"] for c in conds)


def test_real_configs_all_pass():
    """실제 configs 18건이 강화된 검증을 전부 통과해야 함."""
    for p in sorted((ROOT / "configs").glob("*.json")):
        cfg = json.loads(p.read_text(encoding="utf-8"))
        assert build.validate(p.stem, cfg) == [], f"{p.name}: {build.validate(p.stem, cfg)}"


def main():
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  통과: {name}")
        except Exception as e:
            failed += 1
            print(f"  실패: {name} — {type(e).__name__}: {e}")
    if failed:
        sys.exit(f"단위 테스트 {failed}/{len(tests)}개 실패")
    print(f"단위 테스트 전부 통과 ({len(tests)}개)")


if __name__ == "__main__":
    main()
