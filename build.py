# -*- coding: utf-8 -*-
"""src/ 조립 + configs/*.json → dist/<slug>.html (+ dist/index.html) 생성.

빌드 흐름:
  1. src/skeleton.html 의 자리표시자에 src/template.css·template.js 를 인라인
     → template.html (조립본, 직접 수정 금지 — src/ 를 고칠 것)
  2. template.html 의 __CONFIG_START__/__CONFIG_END__ 사이를 config로 치환
     → dist/<slug>.html (실험별 단일 오프라인 HTML)
  3. dist/index.html (실험 선택 화면, 학년·제목순 정렬)

사용법:  py build.py            # 전체 빌드
        py build.py <slug>     # 해당 config만 빌드 (index.html은 항상 재생성)

config 스키마는 config.schema.json 참조. 검증 오류는 전부 모아 한 번에 보고한다.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
SRC = ROOT / "src"
DIST = ROOT / "dist"
MARK = re.compile(r"// __CONFIG_START__.*?// __CONFIG_END__", re.S)

# 앱(HTML)에 주입되는 필드 — 나머지(grade, wiki, note)는 index.html 전용
APP_FIELDS = ["slug", "title", "xLabel", "xUnit", "yLabel", "yUnit",
              "xValues", "groupNames", "trendline", "yMaxHint",
              "entryMode", "maxPoints", "xMaxHint", "ySeries", "trendPower"]
REQUIRED = ["slug", "title", "xLabel", "xUnit", "yLabel", "yUnit",
            "xValues", "trendline", "yMaxHint", "grade"]
TRENDLINES = ("proportional", "linear", "inverse", "smooth", False)
DEFAULT_GROUPS = ["1조", "2조", "3조", "4조", "5조", "6조"]
GRADE_ORDER = {"중1": 0, "중2": 1, "중3": 2}


def assemble_template():
    """src/ 세 파일을 한 HTML로 조립해 template.html에 쓰고 그 내용을 반환."""
    skel = (SRC / "skeleton.html").read_text(encoding="utf-8")
    parts = [("/* __CSS_INLINE__ */", (SRC / "template.css").read_text(encoding="utf-8")),
             ("// __JS_INLINE__", (SRC / "template.js").read_text(encoding="utf-8"))]
    for marker, content in parts:
        if skel.count(marker) != 1:
            sys.exit(f"[오류] src/skeleton.html에 자리표시자 '{marker}'가 정확히 1개 있어야 함")
        skel = skel.replace(marker, content.rstrip("\n"))
    (ROOT / "template.html").write_text(skel, encoding="utf-8")
    return skel


def validate(name, cfg):
    """config 1개의 오류 메시지 목록을 반환 (비어 있으면 통과)."""
    errs = []
    free = cfg.get("entryMode") == "free"
    required = [k for k in REQUIRED if not (free and k == "xValues")]
    missing = [k for k in required if k not in cfg]
    if missing:
        errs.append(f"필수 필드 누락 {missing}")
        return errs                      # 필수가 빠지면 나머지 검사는 무의미
    if cfg["trendline"] not in TRENDLINES:
        errs.append("trendline은 proportional|linear|inverse|smooth|false 여야 함")
    if cfg["trendline"] == "inverse" and cfg.get("trendPower") not in (None, 1, 2):
        errs.append("trendPower는 1 또는 2")
    if free:
        if "xMaxHint" not in cfg:
            errs.append("entryMode=free면 xMaxHint 필수")
        if "ySeries" in cfg:
            errs.append("free 모드와 ySeries는 함께 쓸 수 없음")
    elif not (isinstance(cfg["xValues"], list) and len(cfg["xValues"]) >= 2
              and all(isinstance(v, (int, float)) for v in cfg["xValues"])):
        errs.append("xValues는 숫자 2개 이상의 리스트여야 함")
    if "ySeries" in cfg:
        if not (isinstance(cfg["ySeries"], list) and len(cfg["ySeries"]) == 2
                and all(isinstance(s, str) for s in cfg["ySeries"])):
            errs.append("ySeries는 문자열 2개 리스트 (마커 ●/○ 2계열만 지원)")
        # 두 계열을 하나의 수식으로 적합하면 안 됨 — 계열별 평균 곡선(smooth)만 허용
        if cfg["trendline"] not in (False, "smooth"):
            errs.append("ySeries에는 trendline: false 또는 \"smooth\"만 가능")
    if not re.fullmatch(r"[a-z0-9_]+", str(cfg["slug"])):
        errs.append(f"slug는 소문자·숫자·밑줄만 ({cfg['slug']})")
    elif name != cfg["slug"]:
        errs.append(f"파일명과 slug 불일치 ({cfg['slug']})")
    return errs


def load_configs():
    """configs/*.json 전부 읽고 검증. 오류는 모아서 한 번에 보고 후 종료."""
    cfgs, problems = [], []
    for p in sorted((ROOT / "configs").glob("*.json")):
        try:
            cfg = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            problems.append(f"{p.name}: JSON 문법 오류 — {e}")
            continue
        for msg in validate(p.stem, cfg):
            problems.append(f"{p.name}: {msg}")
        cfgs.append(cfg)
    dup = {c["slug"] for c in cfgs if "slug" in c
           and sum(x.get("slug") == c["slug"] for x in cfgs) > 1}
    if dup:
        problems.append(f"slug 중복: {dup}")
    if problems:
        print("[오류] config 검증 실패:", file=sys.stderr)
        for msg in problems:
            print(f"  - {msg}", file=sys.stderr)
        sys.exit(1)
    return cfgs


def render_config_block(cfg):
    c = {k: cfg[k] for k in APP_FIELDS if k in cfg}
    c.setdefault("groupNames", DEFAULT_GROUPS)
    body = ",\n".join(f"  {k}: {json.dumps(v, ensure_ascii=False)}" for k, v in c.items())
    return "// __CONFIG_START__\nconst CONFIG = {\n" + body + ",\n};\n// __CONFIG_END__"


def build_app(template, cfg):
    html, n = MARK.subn(render_config_block(cfg), template)
    if n != 1:
        sys.exit("[오류] template.html에서 __CONFIG_START__/__CONFIG_END__ 마커를 찾지 못함")
    out = DIST / f"{cfg['slug']}.html"
    out.write_text(html, encoding="utf-8")
    return out


def trend_label(cfg):
    t = cfg["trendline"]
    if t == "inverse":
        return "반비례 곡선(y=a÷x²)" if cfg.get("trendPower") == 2 else "반비례 곡선(y=a÷x)"
    return {"proportional": "비례(원점 통과)", "linear": "직선(절편)",
            "smooth": "평균 곡선(부드러운 추세)", False: "점만(추세선 없음)"}[t]


def build_index(cfgs):
    cfgs = sorted(cfgs, key=lambda c: (GRADE_ORDER.get(c["grade"], 9), c["title"]))
    rows_by_grade = {}
    for c in cfgs:
        note = f'<div class="note">{c["note"]}</div>' if c.get("note") else ""
        xv = ("자유 입력" if c.get("entryMode") == "free"
              else ", ".join(str(v) for v in c["xValues"]))
        series = f' [{c["ySeries"][0]}·{c["ySeries"][1]}]' if c.get("ySeries") else ""
        rows_by_grade.setdefault(c["grade"], []).append(
            f'<a class="card" href="./{c["slug"]}.html">'
            f'<h3>{c["title"]}</h3>'
            f'<p>{c["xLabel"]}({c["xUnit"]}) {xv} → {c["yLabel"]}({c["yUnit"]}){series}</p>'
            f'<p class="trend">{trend_label(c)}</p>{note}</a>')
    sections = "\n".join(
        f'<h2>{g}</h2>\n<div class="grid">\n' + "\n".join(rows) + "\n</div>"
        for g, rows in rows_by_grade.items())
    html = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>조별 실험 그래프 — 실험 선택</title>
<style>
:root {{ --bg:#f7f8fa; --card:#fff; --ink:#1c2733; --sub:#5b6b7c; --line:#dde3ea; --accent:#2a78d6; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg:#12161c; --card:#1b222b; --ink:#e8edf3; --sub:#9aa8b8; --line:#2c3642; --accent:#6aa9e8; }}
}}
* {{ box-sizing:border-box; margin:0; }}
body {{ background:var(--bg); color:var(--ink); font-family:"Malgun Gothic","Noto Sans KR",sans-serif; padding:40px 5vw 80px; }}
h1 {{ font-size:1.9rem; margin-bottom:6px; }}
.sub {{ color:var(--sub); margin-bottom:34px; }}
h2 {{ font-size:1.25rem; margin:30px 0 14px; border-bottom:2px solid var(--line); padding-bottom:8px; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(300px,1fr)); gap:14px; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:18px 20px;
        text-decoration:none; color:inherit; transition:transform .12s, border-color .12s; }}
.card:hover {{ transform:translateY(-2px); border-color:var(--accent); }}
.card h3 {{ font-size:1.08rem; margin-bottom:8px; }}
.card p {{ font-size:.88rem; color:var(--sub); line-height:1.5; }}
.card .trend {{ margin-top:6px; color:var(--accent); font-weight:600; }}
.card .note {{ margin-top:8px; font-size:.8rem; color:var(--sub); border-top:1px dashed var(--line); padding-top:8px; }}
</style></head><body>
<h1>조별 실험 그래프</h1>
<p class="sub">실험을 고르면 프레젠테이션이 열립니다. 입력값은 실험별로 브라우저에 자동 저장됩니다.</p>
{sections}
</body></html>
"""
    (DIST / "index.html").write_text(html, encoding="utf-8")


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    template = assemble_template()
    DIST.mkdir(exist_ok=True)
    cfgs = load_configs()
    if only and only not in {c["slug"] for c in cfgs}:
        sys.exit(f"[오류] slug '{only}' 에 해당하는 config 없음")
    built = 0
    for cfg in cfgs:
        if only and cfg["slug"] != only:
            continue
        out = build_app(template, cfg)
        print(f"  {out.relative_to(ROOT)}  ← {cfg['title']} ({cfg['grade']})")
        built += 1
    build_index(cfgs)
    print(f"완료: 앱 {built}개 빌드, index.html 갱신 (전체 config {len(cfgs)}개)")


if __name__ == "__main__":
    main()
