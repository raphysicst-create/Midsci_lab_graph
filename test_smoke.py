# -*- coding: utf-8 -*-
"""dist/ 앱의 전체 흐름을 자동으로 확인하는 스모크 테스트.

확인 항목 (CLAUDE.md 워크플로 5단계의 자동화):
  도입 씬 제목 → 조별 입력·점 생성 → 종합 씬 → 추세선(수식/smooth) →
  새로고침 후 저장 유지 → 조별 지우기 → 되돌리기 → CSV/PNG 내보내기
기본 실행이면 추가로:
  config 문자열 이스케이프(라벨에 <·& 있어도 마크업 안 깨짐) ·
  localStorage 쓰기가 막힌 환경(시크릿 모드 등)에서도 입력 흐름 유지 + 경고 토스트 ·
  total.html(단일 파일 모음)에서 내장 앱 열기·입력·재열람 유지

입력값은 configs/<slug>.json에서 모드를 읽어 자동 생성한다 — 고정 x(y만),
자유 입력((x,y) 쌍), y 2계열(조당 2값) 어느 앱이든 slug만 주면 된다.

사용법:  py -3.12 test_smoke.py            # 기본 5개 앱 (고정×2 + 자유×2 + 2계열×1)
        py -3.12 test_smoke.py <slug>     # 해당 앱만 (모드는 config에서 자동 감지)
사전 준비: py build.py 로 dist/ 최신화, pip install playwright + playwright install chromium
"""
import json
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

import build

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

    # 조별 추세선: 토글, 입력 변경, 다른 조 데이터 제외, 조별 보기 상태 유지
    group_trends = page.locator("#svg-group path.trendline")
    group_toggle = page.locator("#btn-group-trend")
    if trend_paths:
        group_toggle.click()
        expect(group_toggle).to_have_attribute("aria-pressed", "true")
        expect(group_trends).to_have_count(trend_paths)
        expect(page.locator("#group-trend-readout")).to_contain_text(f"점 {points}개로 계산")
        original_path = group_trends.last.get_attribute("d")
        # 마지막 입력은 모든 입력 모드에서 y값이다.
        inputs.nth(len(values) - 1).fill(str(float(values[-1]) * 0.8))
        inputs.nth(len(values) - 1).press("Tab")
        assert group_trends.last.get_attribute("d") != original_path
        inputs.nth(len(values) - 1).fill(values[-1])
        inputs.nth(len(values) - 1).press("Tab")
        group_toggle.click()
        expect(group_trends).to_have_count(0)
        expect(page.locator("#group-trend-readout")).to_be_empty()
        group_toggle.click()
        page.locator("#btn-next").click()
        expect(group_toggle).to_have_attribute("aria-pressed", "false")
        group_toggle.click()
        expect(group_trends).to_have_count(0)  # 1조 잔상은 계산에서 제외
        expect(page.locator("#group-trend-readout")).to_contain_text("2개 이상")
        for k, v in enumerate(values):
            inputs.nth(k).fill(str(float(v) * 0.5))
            inputs.nth(k).press("Tab")
        expect(group_trends).to_have_count(trend_paths)
        expect(page.locator("#group-trend-readout")).to_contain_text(f"점 {points}개로 계산")
        page.locator("#btn-prev").click()
        expect(group_toggle).to_have_attribute("aria-pressed", "true")
        assert group_trends.last.get_attribute("d") == original_path
    else:
        expect(group_toggle).to_be_hidden()

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
    if trend_paths:
        group_toggle.click()
    page.locator("#btn-clear-group").click()
    expect(page.locator("#group-table input").first).to_have_value("")
    expect(group_trends).to_have_count(0)
    page.locator("#btn-undo").click()
    expect(page.locator("#group-table input").first).to_have_value(values[0])
    if trend_paths:
        expect(group_trends).to_have_count(trend_paths)

    # 7. 내보내기 — CSV·PNG 다운로드가 실제로 발생하는가
    for btn, ext in (("#btn-csv", ".csv"), ("#btn-png", ".png")):
        with page.expect_download() as dl:
            page.locator(btn).click()
        name = dl.value.suggested_filename
        assert name == slug + ext, f"내보내기 파일명 {name} != {slug}{ext}"

    print(f"  통과: {slug}")


def check_escaping(browser):
    """config 문자열에 <·&·따옴표가 있어도 앱 마크업이 깨지지 않는가."""
    cfg = {
        "slug": "esc_probe",
        "title": "제목</script><b>주입</b>",     # </script>로 CONFIG 블록이 깨지는지도 겸사 확인
        "xLabel": "속도<m>", "xUnit": "m/s&s",
        "yLabel": '힘"f"', "yUnit": "N",
        "xValues": [1, 2], "trendline": "linear", "yMaxHint": 10,
        "groupNames": ["1조<i>주입</i>", "2조", "3조", "4조", "5조", "6조"],
    }
    template = (ROOT / "template.html").read_text(encoding="utf-8")
    html, n = build.MARK.subn(lambda m: build.render_config_block(cfg), template)
    assert n == 1
    page = browser.new_page()
    with tempfile.TemporaryDirectory() as td:
        probe = Path(td) / "esc_probe.html"
        probe.write_text(html, encoding="utf-8")
        page.goto(probe.as_uri())
        # 제목이 통째로 살아 있으면 </script> 방어가 동작한 것
        expect(page.locator("#intro-title")).to_have_text(cfg["title"])
        assert "속도<m>" in page.locator("#intro-hint").inner_text(), "도입 안내에서 라벨 태그 소실"
        page.locator("#btn-next").click()
        head = page.locator("#group-table th").first.inner_text()
        assert head == "속도<m>(m/s&s)", f"표 머리글 깨짐: {head!r}"
        while page.locator("#btn-next").is_enabled():
            page.locator("#btn-next").click()
        assert page.locator("#legend i").count() == 0, "조 이름의 <i>가 실제 태그로 주입됨"
        assert "1조<i>주입</i>" in page.locator("#legend").inner_text()
    page.close()
    print("  통과: 이스케이프 (esc_probe)")


def check_storage_blocked(browser):
    """localStorage 쓰기가 막혀도 입력·점 생성이 계속되고 경고 토스트가 1회 뜨는가."""
    ctx = browser.new_context()
    page = ctx.new_page()
    page.add_init_script(
        "Storage.prototype.setItem = function () { throw new Error('blocked'); };")
    page.goto((DIST / "spring_force.html").as_uri())
    page.locator("#btn-next").click()
    inputs = page.locator("#group-table input")
    inputs.nth(0).fill("2.5")
    inputs.nth(0).press("Enter")
    page.wait_for_timeout(1000)
    assert page.locator("#svg-group circle.pt:not(.ghost)").count() >= 1, \
        "저장 실패가 입력 흐름을 끊음 (점 없음)"
    expect(page.locator("#toast")).to_be_visible()
    assert "저장" in page.locator("#toast-msg").inner_text(), "저장 실패 경고 토스트 없음"
    expect(page.locator("#btn-undo")).to_be_hidden()   # 경고 토스트엔 되돌리기 버튼 없음
    inputs.nth(1).fill("5")
    inputs.nth(1).press("Enter")
    page.wait_for_timeout(1000)
    assert page.locator("#svg-group circle.pt:not(.ghost)").count() >= 2, "두 번째 입력 실패"
    ctx.close()
    print("  통과: 저장 차단 환경 (spring_force)")


def check_total(browser):
    """total.html — 카드로 내장 앱이 열리고, 입력이 재열람 시 유지되는가."""
    page = browser.new_page()
    page.goto((DIST / "total.html").as_uri())
    page.evaluate("localStorage.clear()")
    page.reload()
    assert page.locator(".card[data-slug]").count() >= 18, "카드 수 부족"
    expect(page.locator("#viewer")).to_be_hidden()

    page.locator('[data-slug="spring_force"]').click()
    expect(page.locator("#viewer")).to_be_visible()
    app = page.frame_locator("#viewer-frame")
    expect(app.locator("#intro-title")).not_to_have_text("")
    app.locator("#btn-next").click()
    inp = app.locator("#group-table input").first
    inp.fill("4")
    inp.press("Enter")
    page.wait_for_timeout(1000)
    assert app.locator("#svg-group circle.pt:not(.ghost)").count() >= 1, "내장 앱 점 없음"

    page.locator("#btn-back").click()          # 목록으로 → 다시 열면 저장값 복원
    expect(page.locator("#viewer")).to_be_hidden()
    page.locator('[data-slug="spring_force"]').click()
    app.locator("#btn-next").click()
    expect(app.locator("#group-table input").first).to_have_value("4")
    page.close()
    print("  통과: 단일 파일 모음 (total.html)")


def main():
    slugs = sys.argv[1:] if len(sys.argv) > 1 else DEFAULT_SLUGS
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        for slug in slugs:
            run_app(page, slug)
        page.close()
        if len(sys.argv) <= 1:                 # 기본 실행에서만 공통 점검 3종
            check_escaping(browser)
            check_storage_blocked(browser)
            check_total(browser)
        browser.close()
    print("스모크 테스트 전부 통과")


if __name__ == "__main__":
    main()
