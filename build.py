# -*- coding: utf-8 -*-
"""configs/*.json → dist/<slug>.html (+ dist/index.html) 생성.

사용법:  py build.py            # 전체 빌드
        py build.py <slug>     # 해당 config만 빌드 (index.html은 항상 재생성)
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
DIST = ROOT / "dist"
MARK = re.compile(r"// __CONFIG_START__.*?// __CONFIG_END__", re.S)

APP_FIELDS = ["title", "xLabel", "xUnit", "yLabel", "yUnit",
              "xValues", "groupNames", "trendline", "yMaxHint",
              "entryMode", "maxPoints", "xMaxHint", "ySeries", "trendPower"]
REQUIRED = ["slug", "title", "xLabel", "xUnit", "yLabel", "yUnit",
            "xValues", "trendline", "yMaxHint", "grade"]
DEFAULT_GROUPS = ["1조", "2조", "3조", "4조", "5조", "6조"]
GRADE_ORDER = {"중1": 0, "중2": 1, "중3": 2}


def load_configs():
    cfgs = []
    for p in sorted((ROOT / "configs").glob("*.json")):
        cfg = json.loads(p.read_text(encoding="utf-8"))
        free = cfg.get("entryMode") == "free"
        required = [k for k in REQUIRED if not (free and k == "xValues")]
        errs = [k for k in required if k not in cfg]
        if errs:
            sys.exit(f"[오류] {p.name}: 필수 필드 누락 {errs}")
        if cfg["trendline"] not in ("proportional", "linear", "inverse", False):
            sys.exit(f"[오류] {p.name}: trendline은 proportional|linear|inverse|false 여야 함")
        if cfg["trendline"] == "inverse" and cfg.get("trendPower") not in (None, 1, 2):
            sys.exit(f"[오류] {p.name}: trendPower는 1 또는 2")
        if free:
            if "xMaxHint" not in cfg:
                sys.exit(f"[오류] {p.name}: entryMode=free면 xMaxHint 필수")
            if "ySeries" in cfg:
                sys.exit(f"[오류] {p.name}: free 모드와 ySeries는 함께 쓸 수 없음")
        elif not (isinstance(cfg["xValues"], list) and len(cfg["xValues"]) >= 2
                  and all(isinstance(v, (int, float)) for v in cfg["xValues"])):
            sys.exit(f"[오류] {p.name}: xValues는 숫자 2개 이상의 리스트여야 함")
        if "ySeries" in cfg and not (isinstance(cfg["ySeries"], list)
                                     and len(cfg["ySeries"]) == 2
                                     and all(isinstance(s, str) for s in cfg["ySeries"])):
            sys.exit(f"[오류] {p.name}: ySeries는 문자열 2개 리스트 (마커 ●/○ 2계열만 지원)")
        if not re.fullmatch(r"[a-z0-9_]+", cfg["slug"]):
            sys.exit(f"[오류] {p.name}: slug는 소문자·숫자·밑줄만 ({cfg['slug']})")
        if p.stem != cfg["slug"]:
            sys.exit(f"[오류] {p.name}: 파일명과 slug 불일치 ({cfg['slug']})")
        cfgs.append(cfg)
    dup = {c["slug"] for c in cfgs if sum(x["slug"] == c["slug"] for x in cfgs) > 1}
    if dup:
        sys.exit(f"[오류] slug 중복: {dup}")
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
    return {"proportional": "비례(원점 통과)", "linear": "직선(절편)", False: "점만(추세선 없음)"}[t]


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
    template = (ROOT / "template.html").read_text(encoding="utf-8")
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
