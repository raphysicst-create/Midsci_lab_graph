# 조별 실험 그래프 앱 생성기

교과서 위키(`c:\Users\22\Desktop\textbook_wiki`)의 실험 페이지를 수업용
그래프 프레젠테이션(단일 오프라인 HTML)으로 변환하는 워크플로우 프로젝트다.
위키 repo **밖**에 있으며, 위키를 읽기만 하고 절대 수정하지 않는다.

## 앱 모델

한 앱 = 한 실험. 씬 흐름: 도입(빈 좌표축) → 1~6조 입력(값 입력 시 표→그래프
점 비행 애니메이션) → 종합(전체 점 + 추세선). 고정된 x값 몇 개에서 각 조가
y값만 입력하는 구조만 지원한다. 입력값은 localStorage에 실험 제목별로 저장.

## 구조

```
template.html   # 검증된 뼈대 (원본: textbook_wiki/output/group_graph.html, cf87fd1)
                # __CONFIG_START__/__CONFIG_END__ 마커 사이를 빌드가 치환 — 마커 삭제 금지
configs/        # 실험 1개 = JSON 1개. 파일명 = slug.json
build.py        # configs → dist/<slug>.html + dist/index.html
dist/           # 산출물 (커밋함 — 교사가 빌드 없이 바로 쓰도록)
coverage.md     # 위키 실험 전체 목록과 적합/조정필요/부적합 판정 — 백로그
```

## config 스키마 (configs/<slug>.json)

| 필드 | 설명 |
|---|---|
| `slug` | 파일명과 동일, `[a-z0-9_]+` |
| `title` | 앱 제목 (localStorage 키에도 쓰이므로 바꾸면 저장 데이터가 분리됨) |
| `grade` | 중1/중2/… (index.html 분류용) |
| `wiki` | 근거 실험 페이지 파일명 (예: `실험_용수철의_탄성력_측정.md`) |
| `xLabel`/`xUnit`, `yLabel`/`yUnit` | 축 이름·단위 |
| `xValues` | 고정 측정점 (숫자 2개 이상) |
| `trendline` | `"proportional"`(원점 통과) / `"linear"`(절편) / `false`(점만 — 반비례·곡선·플래토) |
| `yMaxHint` | 세로축 시작 최댓값 (데이터가 넘으면 자동 확장) |
| `groupNames` | 생략 시 1~6조 |
| `note` | 선택. 교사용 유의점 — index 카드에 표시 (예: "x값은 교과서에 없는 제안값") |

## 워크플로 — 실험 추가

1. 위키의 `wiki/experiments/실험_<주제>.md`를 정독한다 (과정·결과 표가 근거).
2. 적합성 판정: 고정 x → 숫자 y 측정 구조인가? `coverage.md`의 판정 기준 참조.
3. `configs/<slug>.json` 작성. **xValues는 교과서 과정/결과에 있는 값만 쓴다.**
   교과서에 고정값이 없어 임의로 정했다면 반드시 `note`에 "제안값"임을 명시한다.
4. `py build.py <slug>` → `dist/<slug>.html` 생성 확인.
5. 브라우저(또는 Playwright)로 열어 도입 씬 제목·축 라벨·조별 입력·추세선을 확인한다.
   추세선 모드가 실험의 관계(비례/선형/그 외)와 맞는지 특히 확인.
6. `coverage.md`의 해당 행을 갱신하고 git 커밋: `feat: <실험명> 앱 추가`.

## 템플릿 수정 시

- `template.html`을 고치면 `py build.py`로 **전체 재빌드**해야 dist가 일관된다.
- 디자인 교체는 `:root` CSS 변수 블록(+다크 모드 블록)만 바꾼다.
  차트 6색은 dataviz 검증(인접 CVD ΔE ≥ 12)을 통과한 팔레트 — 임의 교체 금지,
  바꿀 경우 dataviz 스킬의 validate_palette.js로 재검증한다.
- 기능 수정 후에는 최소 1개 앱을 Playwright로 구동해 전체 흐름(입력→점 비행→
  종합→추세선→새로고침 유지)을 확인한다.

## 금지사항

- 위키 repo의 어떤 파일도 수정하지 않는다 (읽기 전용 참조).
- 템플릿의 `__CONFIG_START__`/`__CONFIG_END__` 마커를 지우지 않는다.
- 교과서에 없는 측정값·단위를 `note` 표기 없이 config에 넣지 않는다.
- `dist/`를 직접 손으로 편집하지 않는다 (항상 build.py 경유).
