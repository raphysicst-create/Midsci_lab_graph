# 조별 실험 그래프 앱 생성기

교과서 위키(`c:\Users\22\Desktop\textbook_wiki`)의 실험 페이지를 수업용
그래프 프레젠테이션(단일 오프라인 HTML)으로 변환하는 워크플로우 프로젝트다.
위키 repo **밖**에 있으며, 위키를 읽기만 하고 절대 수정하지 않는다.

## 앱 모델

한 앱 = 한 실험. 씬 흐름: 도입(빈 좌표축) → 1~6조 입력(값 입력 시 표→그래프
점 비행 애니메이션) → 종합(전체 점 + 추세선). 고정된 x값 몇 개에서 각 조가
y값만 입력하는 구조만 지원한다. 입력값은 localStorage에 **slug별** 저장
(제목을 다듬어도 데이터 유지 — 구 제목 키는 최초 1회 자동 이전).

## 구조

```
src/            # 소스 — 여기를 고친다 (skeleton.html + template.css + template.js)
                # template.js 상단 "파일 지도" 주석에 섹션별 수정 지점 안내
template.html   # build.py가 src/에서 조립한 산출물 — 직접 수정 금지
                # __CONFIG_START__/__CONFIG_END__ 마커 사이를 빌드가 치환 — 마커 삭제 금지
                # (원본 뼈대: textbook_wiki/output/group_graph.html, cf87fd1)
configs/        # 실험 1개 = JSON 1개. 파일명 = slug.json
config.schema.json  # config 필드 문서(JSON Schema) — build.py validate()와 일치 유지
build.py        # src/ 조립 → template.html, configs → dist/<slug>.html + dist/index.html
dist/           # 산출물 (커밋함 — 교사가 빌드 없이 바로 쓰도록)
test_smoke.py   # Playwright E2E: 입력→점→종합→추세선→저장 유지→지우기/되돌리기→내보내기
coverage.md     # 위키 실험 전체 목록과 적합/조정필요/부적합 판정 — 백로그
```

다른 HTML 프레젠테이션에 넣을 땐 iframe이 가장 쉽다 — 방법 3가지가
`src/skeleton.html` 상단 주석에 있음.

## config 스키마 (configs/<slug>.json)

| 필드 | 설명 |
|---|---|
| `slug` | 파일명과 동일, `[a-z0-9_]+`. 위키 전체에서 유일. localStorage 키·내보내기 파일명 — 바꾸면 저장 데이터가 분리됨 |
| `title` | 앱 제목. 유일해야 함 |
| `grade` | 중1/중2/… (index.html 분류용) |
| `wiki` | 근거 실험 페이지 파일명 (예: `실험_용수철의_탄성력_측정.md`) |
| `xLabel`/`xUnit`, `yLabel`/`yUnit` | 축 이름·단위 |
| `xValues` | 고정 측정점 (숫자 2개 이상). `entryMode:"free"`면 생략 |
| `trendline` | `"proportional"`(원점 통과) / `"linear"`(절편) / `"inverse"`(반비례 y=a÷xⁿ) / `"smooth"`(학급 평균 곡선 — 플래토·수렴·포화 등 수식 적합이 안 되는 모양) / `false`(점만) |
| `yMaxHint` | 세로축 시작 최댓값 (데이터가 넘으면 자동 확장) |
| `groupNames` | 생략 시 1~6조 |
| `note` | 선택. 교사용 유의점 — index 카드에 표시 (예: "x값은 교과서에 없는 제안값") |

### 입력 모드 — 세 가지 (선택 필드로 전환)

기본은 **고정 x**(위 표 그대로): x값이 정해져 있고 각 조는 y만 입력.

- **자유 입력** `"entryMode": "free"` — x가 실험마다 달라 고정할 수 없을 때
  (밀도: 물체마다 부피 다름 / 샤를·증발: 교과서에 측정표 없음). 각 조가 (x, y)
  쌍을 자유 입력. `xValues` 대신 **`xMaxHint`**(가로축 시작 최댓값) 필수,
  `maxPoints`(조당 입력 행 수, 기본 5) 선택. x·y 둘 다 채워야 점이 찍힘.
- **y 2계열** `"ySeries": ["물", "식용유"]` — 고정 x에서 조당 y를 2개 입력
  (열평형·비열: 두 물질/물체를 한 그래프에 비교). 1번째는 채운 점(●),
  2번째는 링(○). 두 계열을 하나의 수식으로 적합하면 안 되므로 **`trendline`은
  `false` 또는 `"smooth"`만 허용** (smooth면 계열별 평균 곡선 2개 — 1번째 실선,
  2번째 점선). 2계열까지만 지원.
- **반비례 추세선** `"trendline": "inverse"` (+ `"trendPower": 1|2`) — 보일 법칙
  (y=a÷x), 광원 거리-조도(y=a÷x²)처럼 반비례 관계의 곡선 추세선. 고정 x·자유
  입력 어느 모드와도 조합 가능.
- **평균 곡선** `"trendline": "smooth"` — 가열/냉각(플래토), 열평형(수렴),
  광합성(포화)처럼 수식 하나로 적합할 수 없는 곡선 실험용. 각 x에서 학급
  평균을 구해 단조 3차 보간(출렁임 없음)으로 잇는다. 어느 입력 모드와도 조합 가능.

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

- **`src/`를 고친다** (template.html은 조립 산출물이라 재빌드 때 덮어써짐).
  고친 뒤 `py build.py`로 **전체 재빌드**해야 template.html·dist가 일관된다.
- 디자인 교체는 `src/template.css`의 디자인 토큰 블록만 바꾼다 — 다크 토큰이
  **A(OS 추종)·B(수동 토글) 두 블록**이므로 항상 둘 다 같은 값으로.
  차트 6색은 dataviz 검증(인접 CVD ΔE ≥ 12)을 통과한 팔레트 — 임의 교체 금지,
  바꿀 경우 dataviz 스킬의 validate_palette.js로 재검증한다.
- 기능 수정 후에는 `py -3.12 test_smoke.py`(Playwright E2E)를 돌린다 — 입력→
  점 비행→종합→추세선→새로고침 유지→조별 지우기/되돌리기→CSV/PNG 내보내기까지
  자동 확인. 새 기능이면 test_smoke.py에 확인 단계를 추가한다.

## 금지사항

- 위키 repo의 어떤 파일도 수정하지 않는다 (읽기 전용 참조).
  이 규칙은 `.claude/hooks/block_wiki.py`(PreToolUse 훅)가 기계적으로도 강제한다 —
  위키 경로 대상 Write/Edit는 거부되고, 위키 경로가 등장하는 셸 명령도 일괄
  차단된다(위키 읽기는 Read/Grep/Glob 도구 사용). 훅을 지우거나 우회하지 않는다.
- 템플릿의 `__CONFIG_START__`/`__CONFIG_END__` 마커를 지우지 않는다.
- 교과서에 없는 측정값·단위를 `note` 표기 없이 config에 넣지 않는다.
- `dist/`를 직접 손으로 편집하지 않는다 (항상 build.py 경유).
