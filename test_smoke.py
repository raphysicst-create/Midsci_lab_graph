# -*- coding: utf-8 -*-
"""dist/ 앱의 전체 흐름을 자동으로 확인하는 스모크 테스트.

확인 항목 (CLAUDE.md 워크플로 5단계의 자동화):
  도입 씬 제목 → 조별 입력·점 생성 → 종합 씬 → 추세선(수식/smooth) →
  새로고침 후 저장 유지 → 조별 지우기 → 되돌리기 → CSV/PNG 내보내기

사용법:  py test_smoke.py            # 기본 2개 앱(직선 적합 1 + smooth 1)
        py test_smoke.py <slug>     # 해당 앱만
사전 준비: py build.py 로 dist/ 최신화, pip install playwright + playwright install chromium
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).parent
DIST = ROOT / "dist"

# (slug, 첫 조에 넣을 y값 2개) — 추세선엔 점 2개 이상 필요
DEFAULT_TARGETS = [
    ("spring_force", ["2.5", "5"]),      # 고정 x + proportional (수식 적합)
    ("heating_curve", ["25", "60"]),     # 고정 x + smooth (평균 곡선)
]


def run_app(page, slug, values):
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
    assert own.count() >= len(values), f"조별 씬 점 {own.count()}개 < {len(values)}개"

    # 3. 종합 씬으로 이동 (다음 버튼 반복)
    while page.locator("#btn-next").is_enabled():
        page.locator("#btn-next").click()
    expect(page.locator("#scene-summary")).to_have_class("scene active")
    page.wait_for_timeout(1200)             # 조별 등장 시차 대기
    assert page.locator("#svg-summary circle.pt").count() >= len(values)

    # 4. 추세선 토글 — 경로가 그려지고 읽어주기 문구가 나오는가
    page.locator("#legend .trend-chip").click()
    page.wait_for_timeout(1400)
    assert page.locator("#svg-summary path.trendline").count() >= 1, "추세선 경로 없음"
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
    only = sys.argv[1] if len(sys.argv) > 1 else None
    targets = ([(only, ["2.5", "5"])] if only else DEFAULT_TARGETS)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        for slug, values in targets:
            run_app(page, slug, values)
        browser.close()
    print("스모크 테스트 전부 통과")


if __name__ == "__main__":
    main()
