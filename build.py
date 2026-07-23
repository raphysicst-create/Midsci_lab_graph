# -*- coding: utf-8 -*-
"""src/ 조립 + configs/*.json → dist/<slug>.html (+ dist/index.html) 생성.

빌드 흐름:
  1. src/skeleton.html 의 자리표시자에 src/template.css·template.js 를 인라인
     → template.html (조립본, 직접 수정 금지 — src/ 를 고칠 것)
  2. template.html 의 __CONFIG_START__/__CONFIG_END__ 사이를 config로 치환
     → dist/<slug>.html (실험별 단일 오프라인 HTML)
  3. dist/index.html (실험 선택 화면, 학년·단원순 정렬)
  4. dist/total.html (전 실험을 한 파일에 내장한 단일 파일 모음)

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

# 앱(HTML)에 주입되는 필드 — 나머지(grade, wiki, note, unit, summary)는 index.html 전용
APP_FIELDS = ["slug", "title", "xLabel", "xUnit", "yLabel", "yUnit",
              "xValues", "groupNames", "trendline", "yMaxHint",
              "entryMode", "maxPoints", "xMaxHint", "ySeries", "trendPower"]
REQUIRED = ["slug", "title", "xLabel", "xUnit", "yLabel", "yUnit",
            "xValues", "trendline", "yMaxHint", "grade", "unit", "summary"]
# config에 올 수 있는 전체 필드 — 이 밖의 키는 오타로 간주해 거부
KNOWN_FIELDS = APP_FIELDS + ["grade", "wiki", "note", "unit", "summary"]
UNIT_RE = re.compile(r"(\d+)단원_.+")   # index 카드 표기·단원순 정렬 근거
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
    def num(v):
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    unknown = [k for k in cfg if k not in KNOWN_FIELDS]
    if unknown:
        errs.append(f"알 수 없는 필드 {unknown} — 오타 확인 (config.schema.json 참조)")
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
    if cfg["grade"] not in GRADE_ORDER:
        errs.append(f"grade는 {'|'.join(GRADE_ORDER)} 중 하나 ({cfg['grade']!r})")
    if not num(cfg["yMaxHint"]):
        errs.append("yMaxHint는 숫자여야 함")
    if "maxPoints" in cfg and not (isinstance(cfg["maxPoints"], int)
                                   and not isinstance(cfg["maxPoints"], bool)
                                   and cfg["maxPoints"] >= 1):
        errs.append("maxPoints는 1 이상의 정수여야 함")
    if "groupNames" in cfg and not (isinstance(cfg["groupNames"], list)
                                    and all(isinstance(g, str) for g in cfg["groupNames"])):
        errs.append("groupNames는 문자열 리스트여야 함")
    if free:
        if "xMaxHint" not in cfg:
            errs.append("entryMode=free면 xMaxHint 필수")
        elif not num(cfg["xMaxHint"]):
            errs.append("xMaxHint는 숫자여야 함")
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
    if not UNIT_RE.fullmatch(str(cfg["unit"])):
        errs.append(f"unit은 'N단원_이름' 형식이어야 함 (예: 3단원_열) — {cfg['unit']!r}")
    if not (isinstance(cfg["summary"], str) and cfg["summary"].strip()):
        errs.append("summary는 비어 있지 않은 문자열이어야 함 (index 카드 설명)")
    if not re.fullmatch(r"[a-z0-9_]+", str(cfg["slug"])):
        errs.append(f"slug는 소문자·숫자·밑줄만 ({cfg['slug']})")
    elif name != cfg["slug"]:
        errs.append(f"파일명과 slug 불일치 ({cfg['slug']})")
    return errs


def find_duplicates(cfgs):
    """slug·title 중복 문제 목록 — 파일 간 유일성 검사라 validate() 밖에 둔다.
    (title은 구 버전 localStorage 키라 중복 시 저장 데이터가 섞인다)"""
    probs = []
    for field in ("slug", "title"):
        vals = [c[field] for c in cfgs if field in c]
        dup = {v for v in vals if vals.count(v) > 1}
        if dup:
            probs.append(f"{field} 중복: {dup}")
    return probs


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
    problems += find_duplicates(cfgs)
    if problems:
        print("[오류] config 검증 실패:", file=sys.stderr)
        for msg in problems:
            print(f"  - {msg}", file=sys.stderr)
        sys.exit(1)
    return cfgs


def esc(s):
    """HTML 이스케이프 — config 문자열이 index 카드 마크업을 깨지 않도록."""
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def render_config_block(cfg):
    c = {k: cfg[k] for k in APP_FIELDS if k in cfg}
    c.setdefault("groupNames", DEFAULT_GROUPS)
    body = ",\n".join(f"  {k}: {json.dumps(v, ensure_ascii=False)}" for k, v in c.items())
    # 값에 </script> 등이 있어도 스크립트 블록이 깨지지 않도록 (JS 문자열 의미는 동일)
    body = body.replace("</", "<\\/")
    return "// __CONFIG_START__\nconst CONFIG = {\n" + body + ",\n};\n// __CONFIG_END__"


def build_app_html(template, cfg):
    """마커 구간을 config로 치환한 HTML 문자열.
    치환문은 함수로 넘긴다 — 문자열로 주면 re가 값 속 백슬래시를 이스케이프로 해석."""
    html, n = MARK.subn(lambda m: render_config_block(cfg), template)
    if n != 1:
        sys.exit("[오류] template.html에서 __CONFIG_START__/__CONFIG_END__ 마커를 찾지 못함")
    return html


def build_app(template, cfg):
    out = DIST / f"{cfg['slug']}.html"
    out.write_text(build_app_html(template, cfg), encoding="utf-8")
    return out


def unit_no(cfg):
    """'3단원_열' → 3 (단원순 정렬 키). validate()가 형식을 보장한다."""
    return int(UNIT_RE.fullmatch(str(cfg["unit"])).group(1))


def card_html(c, total=False):
    """index/total의 실험 카드 1개: 제목 / 단원 / (점선) / 설명.
    title·summary 속 \n은 카드에서 줄바꿈으로 표시 (앱 화면에서는 공백으로 접힘).
    note는 config 기록용일 뿐 카드에 표시하지 않는다.
    total이면 파일 링크 대신 내장 앱을 여는 data-slug 카드가 된다."""
    link = (f'href="#{c["slug"]}" data-slug="{c["slug"]}"' if total
            else f'href="./{c["slug"]}.html"')
    title = esc(c["title"]).replace("\n", "<br>")
    summary = esc(c["summary"]).replace("\n", "<br>")
    return (f'<a class="card" {link}>'
            f'<h3>{title}</h3>'
            f'<p class="unit">{esc(c["unit"])}</p>'
            f'<p class="summary">{summary}</p></a>')


def grade_sections(cfgs, total=False):
    """학년(중1/중2)별 h2 + 단원순 카드 그리드 마크업 — index/total 공용."""
    cfgs = sorted(cfgs, key=lambda c: (GRADE_ORDER.get(c["grade"], 9), unit_no(c), c["title"]))
    rows_by_grade = {}
    for c in cfgs:
        rows_by_grade.setdefault(c["grade"], []).append(card_html(c, total))
    return "\n".join(
        f'<h2>{g}</h2>\n<div class="grid">\n' + "\n".join(rows) + "\n</div>"
        for g, rows in rows_by_grade.items())


# index.html·total.html 공용 페이지 스타일
PAGE_CSS = """:root { --bg:#f7f8fa; --card:#fff; --ink:#1c2733; --sub:#5b6b7c; --line:#dde3ea; --accent:#2a78d6; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#12161c; --card:#1b222b; --ink:#e8edf3; --sub:#9aa8b8; --line:#2c3642; --accent:#6aa9e8; }
}
* { box-sizing:border-box; margin:0; }
body { background:var(--bg); color:var(--ink); font-family:"Malgun Gothic","Noto Sans KR",sans-serif; padding:40px 5vw 80px; }
h1 { font-size:1.9rem; margin-bottom:6px; }
.sub { color:var(--sub); margin-bottom:34px; }
h2 { font-size:1.25rem; margin:30px 0 14px; border-bottom:2px solid var(--line); padding-bottom:8px; }
.grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(300px,1fr)); gap:14px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:18px 20px;
        text-decoration:none; color:inherit; transition:transform .12s, border-color .12s; }
.card:hover { transform:translateY(-2px); border-color:var(--accent); }
.card h3 { font-size:1.08rem; margin-bottom:8px; }
.card p { font-size:.88rem; color:var(--sub); line-height:1.5; }
.card .unit { font-size:.8rem; color:var(--accent); font-weight:600; }
.card .summary { margin-top:8px; border-top:1px dashed var(--line); padding-top:8px; word-break:keep-all; }"""


def build_index(cfgs):
    html = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>조별 실험 그래프 — 실험 선택</title>
<style>
{PAGE_CSS}
</style></head><body>
<h1>조별 실험 그래프</h1>
<p class="sub">실험을 고르면 프레젠테이션이 열립니다. 입력값은 실험별로 브라우저에 자동 저장됩니다.</p>
{grade_sections(cfgs)}
</body></html>
"""
    (DIST / "index.html").write_text(html, encoding="utf-8")


# total.html 뼈대 — JS 중괄호가 많아 f-string 대신 자리표시자 치환 방식
TOTAL_PAGE = """<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>조별 실험 그래프 — 전체 모음</title>
<style>
__CSS__
#viewer { position:fixed; inset:0; background:var(--bg); z-index:10; display:flex; flex-direction:column; }
#viewer[hidden] { display:none; }
#viewer-bar { display:flex; align-items:center; gap:12px; padding:8px 12px; border-bottom:1px solid var(--line); }
#btn-back { font:inherit; padding:6px 14px; border:1px solid var(--line); border-radius:8px;
            background:var(--card); color:var(--ink); cursor:pointer; }
#btn-back:hover { border-color:var(--accent); color:var(--accent); }
#viewer-title { font-weight:600; }
#viewer-frame { flex:1; width:100%; border:0; }
</style></head><body>
<h1>조별 실험 그래프</h1>
<p class="sub">실험을 고르면 이 화면에서 바로 열립니다. 이 파일 하나로 전체 실험이 동작하며,
입력값은 실험별로 브라우저에 자동 저장됩니다.</p>
__SECTIONS__
<div id="viewer" hidden>
  <div id="viewer-bar"><button id="btn-back" type="button">← 실험 목록</button><span id="viewer-title"></span></div>
  <iframe id="viewer-frame" title="실험 앱"></iframe>
</div>
<script>
const DATA = __PAYLOAD__;
const viewer = document.getElementById("viewer");
const frame = document.getElementById("viewer-frame");
for (const card of document.querySelectorAll(".card[data-slug]")) {
  card.addEventListener("click", e => {
    e.preventDefault();
    const slug = card.dataset.slug;
    document.getElementById("viewer-title").textContent = DATA.titles[slug];
    frame.srcdoc = DATA.apps[slug];
    viewer.hidden = false;
    document.body.style.overflow = "hidden";   // 뒤 목록 스크롤 잠금
    frame.addEventListener("load", () => frame.contentWindow.focus(), { once: true });
  });
}
document.getElementById("btn-back").addEventListener("click", () => {
  viewer.hidden = true;
  frame.removeAttribute("srcdoc");   // 앱 정지 — 다시 열면 저장값으로 복원
  document.body.style.overflow = "";
});
</script>
</body></html>
"""


def build_total(template, cfgs):
    """전 실험 + 선택 화면을 한 파일에 담은 dist/total.html.
    각 앱 HTML을 JSON으로 내장, 카드 클릭 시 iframe(srcdoc)으로 연다.
    저장 키는 개별 앱과 같은 slug 기반 localStorage라 데이터가 서로 이어진다."""
    apps = {c["slug"]: build_app_html(template, c) for c in cfgs}
    titles = {c["slug"]: c["title"].replace("\n", " ") for c in cfgs}
    payload = json.dumps({"apps": apps, "titles": titles}, ensure_ascii=False)
    payload = payload.replace("</", "<\\/")   # 스크립트 블록 보호 (JS 문자열 의미는 동일)
    html = (TOTAL_PAGE
            .replace("__CSS__", PAGE_CSS)
            .replace("__SECTIONS__", grade_sections(cfgs, total=True))
            .replace("__PAYLOAD__", payload))
    (DIST / "total.html").write_text(html, encoding="utf-8")


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
    build_total(template, cfgs)
    print(f"완료: 앱 {built}개 빌드, index.html·total.html 갱신 (전체 config {len(cfgs)}개)")


if __name__ == "__main__":
    main()
