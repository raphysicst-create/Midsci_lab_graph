# -*- coding: utf-8 -*-
"""dist/ 앱의 전체 흐름을 자동으로 확인하는 스모크 테스트.

확인 항목 (CLAUDE.md 워크플로 5단계의 자동화):
  도입 씬 제목 → 조별 입력·점 생성 → 종합 씬 → 추세선(수식/smooth) →
  새로고침 후 저장 유지 → 조별 지우기 → 되돌리기 → CSV/PNG 내보내기

입력값은 configs/<slug>.json에서 모드를 읽어 자동 생성한다 — 고정 x(y만),
자유 입력((x,y) 쌍), y 2계열(조당 2값) 어느 앱이든 slug만 주면 된다.

사용법:  py -3.12 test_smoke.py            # 기본 5개 앱 (고정×2 + 자유×2 + 2계열×1)
        py -3.12 test_smoke.py <slug>     # 해당 앱만 (모드는 config에서 자동 감지)
사전 준비: py build.py 로 dist/ 최신화, pip install playwright + playwright install chromium
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).parent
DIST = ROOT / "dist"

# 세 입력 모드 × 추세선 수식/smooth/inverse를 모두 표본에 포함
DEFAULT_SLUGS = [
    "spring_force",    # 고정 x + proportional (수식 적합)
    "heating_curve",   # 고정 x + smooth (평균 곡선)
    "boyle_pv",        # 자유 입력 + inverse (반비례 곡선)
    "density",         # 자유 입력 + proportional
    "thermal_eq",      # y 2계열 + smooth (계열별 곡선 2개)
]


def make_plan(slug):
    """config에서 모드를 읽어 (입력값 목록, 기대 점 수, 기대 추세선 path 수) 생성.

    입력값은 #group-table의 input 순서대로 채운다:
      고정 x  → x별 y 1개        | 2계열 → x별 [계열1, 계열2]
      자유 입력 → 행별 [x, y]
    """
    cfg = json.loads((ROOT / "configs" / f"{slug}.json").read_text(encoding="utf-8"))
    ymax = cfg["yMaxHint"]
    ys = [round(ymax * f, 2) for f in (0.4, 0.7, 0.5, 0.6)]
    if cfg.get("entryMode") == "free":
        xs = [round(cfg["xMaxHint"] * f, 2) for f in (0.3, 0.6)]
        values, points = [xs[0], ys[0], xs[1], ys[1]], 2      # (x,y) 2쌍
    elif cfg.get("ySeries"):
        values, points = ys, 4                                # x 2개 × 2계열
    else:
        values, points = ys[:2], 2                            # 고정 x 2개의 y
    if cfg["trendline"] is False:
        paths = 0
    elif cfg.get("ySeries") and cfg["trendline"] == "smooth":
        paths = 2                                             # 계열별 곡선(실선+점선)
    else:
        paths = 1
    # 4.0 → "4": 앱이 숫자로 저장 후 "4"로 복원하므로 문자열도 맞춰야 5단계 비교가 성립
    return [str(int(v)) if float(v).is_integer() else str(v) for v in values], points, paths


def run_app(page, slug):
    values, points, trend_paths = make_plan(slug)
    url = (DIST / f"{slug}.html").as_uri()
    page.goto(url)
    page.evaluate("localStorage.clear()")   # 이전 실행의 저장값 제거
    page.reload()

    # 1. 도입 씬 — 제목·축이 그려졌는가
    expect(page.locator("#intro-title")).not_to_have_text("")
    assert page.locator("#svg-intro .axis line").count() == 2, "도입 씬 축 없음"

    # 2. 1조 입력 — 점이 생기고 표 행이 하이라이트되는가
    page.locator("#btn-next").click()
    inputs = page.locator("#group-table input")
    for k, v in enumerate(values):
        inputs.nth(k).fill(v)
        inputs.nth(k).press("Enter")
    page.wait_for_timeout(1000)             # 점 비행(0.82s) 착지 대기
    own = page.locator("#svg-group circle.pt:not(.ghost)")
    assert own.count() >= points, f"조별 씬 점 {own.count()}개 < {points}개"

    # 3. 종합 씬으로 이동 (다음 버튼 반복)
    while page.locator("#btn-next").is_enabled():
        page.locator("#btn-next").click()
    expect(page.locator("#scene-summary")).to_have_class("scene active")
    page.wait_for_timeout(1200)             # 조별 등장 시차 대기
    assert page.locator("#svg-summary circle.pt").count() >= points

    # 4. 추세선 토글 — 경로가 그려지고 읽어주기 문구가 나오는가
    if trend_paths:
        page.locator("#legend .trend-chip").click()
        page.wait_for_timeout(1400)
        got = page.locator("#svg-summary path.trendline").count()
        assert got >= trend_paths, f"추세선 경로 {got}개 < {trend_paths}개"
        expect(page.locator("#trend-readout")).to_contain_text("추세선")

    # 5. 새로고침 — 입력값이 localStorage에서 복원되는가
    page.reload()
    page.locator("#btn-next").click()
    expect(page.locator("#group-table input").first).to_have_value(values[0])

    # 6. 조별 지우기 → 되돌리기
    page.locator("#btn-clear-group").click()
    expect(page.locator("#group-table input").first).to_have_value("")
    page.locator("#btn-undo").click()
    expect(page.locator("#group-table input").first).to_have_value(values[0])

    # 7. 내보내기 — CSV·PNG 다운로드가 실제로 발생하는가
    for btn, ext in (("#btn-csv", ".csv"), ("#btn-png", ".png")):
        with page.expect_download() as dl:
            page.locator(btn).click()
        name = dl.value.suggested_filename
        assert name == slug + ext, f"내보내기 파일명 {name} != {slug}{ext}"

    print(f"  통과: {slug}")


def main():
    slugs = sys.argv[1:] if len(sys.argv) > 1 else DEFAULT_SLUGS
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        for slug in slugs:
            run_app(page, slug)
        browser.close()
    print("스모크 테스트 전부 통과")


if __name__ == "__main__":
    main()
