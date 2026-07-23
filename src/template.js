"use strict";
/* ============================================================
   조별 실험 그래프 — 메인 스크립트 (소스: src/template.js)

   ◆ 파일 지도 — 무엇을 고치려면 어디를 보나
   §1 환경·상태·저장   조 수(G)·입력 모드(MODE)·localStorage 읽고 쓰기
   §2 좌표계·축        SVG 좌표 변환, 눈금 계산, 빈 차트 그리기(drawChart)
   §3 점 그리기        drawPoint(마커·툴팁 데이터), 안내선(drawGuides)
   §4 추세선           fitTrend(수식 적합) / smooth(평균 곡선) / drawTrend
   §5 씬 렌더링        도입(renderIntro)·조별(renderGroup)·종합(renderSummary)
   §6 내보내기         CSV(exportCSV)·PNG(exportPNG)
   §7 지우기·되돌리기  doClear + 토스트(undo)
   §8 내비게이션·전역  씬 전환, 키보드, 테마 토글, 툴팁

   ◆ 자주 하는 수정
   - 추세선 종류 추가: §4 computeTrend·drawTrend·trendReadout 세 곳
     + build.py의 trendline 화이트리스트·trend_label + config.schema.json
   - 입력 모드 추가: MODE 판정(§1) → allPoints(§1) → 표 생성(renderGroup §5)
   - 데이터 저장 형식: emptyCell/loadData(§1)의 주석 참조 (모드별 셀 모양)

   ◆ 전제
   - CONFIG 전역 객체가 이 스크립트보다 먼저 선언돼 있어야 한다
     (skeleton.html의 __CONFIG_START__ 블록. build.py가 실험별로 치환).
   - 외부 라이브러리 없음. 이 파일 하나가 앱 로직 전부다.
   ============================================================ */

/* ============================================================
   §1 환경·상태·저장
   ============================================================ */
const G = CONFIG.groupNames.length;          // 조 수
/* 입력 모드: fixed(고정 x, y 1개) | dual(고정 x, y 2계열) | free(x·y 자유 입력) */
const MODE = CONFIG.entryMode === "free" ? "free"
  : (Array.isArray(CONFIG.ySeries) && CONFIG.ySeries.length === 2 ? "dual" : "fixed");
const N = MODE === "free" ? (CONFIG.maxPoints || 5) : CONFIG.xValues.length;   // 행 수
const SCENES = 1 + G + 1;                    // 도입 + 조별 + 종합

/* OS "움직임 줄이기" 설정 — 켜져 있으면 점 비행·드로잉 애니메이션을 건너뜀 */
const REDUCED_MOTION = matchMedia("(prefers-reduced-motion: reduce)").matches;

/* 저장 키는 slug 기반 (제목을 다듬어도 데이터가 유지되도록).
   예전 버전은 제목 기반 키였으므로 있으면 1회 옮겨온다. */
const STORE_KEY = "group_graph::" + (CONFIG.slug || CONFIG.title);
const LEGACY_KEY = "group_graph::" + CONFIG.title;

/* localStorage가 막힌 환경(시크릿 모드·잠긴 프로필)에서도 앱은 계속 동작해야 한다 */
const store = {
  get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); return true; } catch (e) { return false; } },
};

if (LEGACY_KEY !== STORE_KEY && !store.get(STORE_KEY)) {
  const legacy = store.get(LEGACY_KEY);
  if (legacy) store.set(STORE_KEY, legacy);
}

/* 저장 셀 모양 — fixed: y값|null, dual: [y1,y2], free: [x,y] */
const emptyCell = () => (MODE === "fixed" ? null : [null, null]);
const emptyRow = () => Array.from({ length: N }, emptyCell);
const emptyData = () => Array.from({ length: G }, emptyRow);

const state = {
  scene: 0,
  group: 0,                                  // 현재 조 (0-based)
  data: loadData(),
  visible: Array(G).fill(true),              // 종합 씬 조별 토글
  trendOn: false,
};

function loadData() {
  try {
    const raw = JSON.parse(store.get(STORE_KEY));
    const cellOk = c => MODE === "fixed"
      ? (c === null || typeof c === "number")
      : (Array.isArray(c) && c.length === 2 &&
         c.every(v => v === null || typeof v === "number"));
    if (Array.isArray(raw) && raw.length === G &&
        raw.every(r => Array.isArray(r) && r.length === N && r.every(cellOk)))
      return raw;
  } catch (e) { /* 깨진 저장값은 무시하고 초기화 */ }
  return emptyData();
}
let saveWarned = false;
function saveData() {
  if (store.set(STORE_KEY, JSON.stringify(state.data)) || saveWarned) return;
  saveWarned = true;                             // 경고는 1회만 — 입력 자체는 계속된다
  showToast("이 브라우저에선 저장이 안 됩니다 — 입력값은 새로고침하면 사라져요", false);
}

/* 표의 한 입력칸 값 — f: fixed는 0(y), dual은 계열 번호, free는 0(x)/1(y) */
function getField(g, i, f) { return MODE === "fixed" ? state.data[g][i] : state.data[g][i][f]; }
function setField(g, i, f, v) {
  if (MODE === "fixed") state.data[g][i] = v; else state.data[g][i][f] = v;
}

const groupColor = g => `var(--series-${g + 1})`;
/* 점 목록 — {g(조), i(행), s(계열), x, y}. free는 x·y 둘 다 있어야 점이 된다 */
const allPoints = (visibleOnly = false) => {
  const pts = [];
  state.data.forEach((row, g) => {
    if (visibleOnly && !state.visible[g]) return;
    row.forEach((cell, i) => {
      if (MODE === "fixed") {
        if (cell != null) pts.push({ g, i, s: 0, x: CONFIG.xValues[i], y: cell });
      } else if (MODE === "dual") {
        cell.forEach((y, s) => { if (y != null) pts.push({ g, i, s, x: CONFIG.xValues[i], y }); });
      } else if (cell[0] != null && cell[1] != null) {
        pts.push({ g, i, s: 0, x: cell[0], y: cell[1] });
      }
    });
  });
  return pts;
};

/* ============================================================
   §2 좌표계·축
   ============================================================ */
const VB = { w: 920, h: 620 };               // SVG viewBox 크기 (PNG 내보내기 기준 크기)
const M = { l: 90, r: 30, t: 24, b: 78 };    // 플롯 여백
const plotW = VB.w - M.l - M.r, plotH = VB.h - M.t - M.b;

function niceCeil(v) {                        // 보기 좋은 값으로 올림
  if (v <= 0) return 1;
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  for (const m of [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) if (m * p >= v) return m * p;
  return 10 * p;
}
function tickStep(max) {                      // 눈금 4~6개가 되는 간격
  const rough = max / 5;
  const p = Math.pow(10, Math.floor(Math.log10(rough)));
  for (const m of [1, 2, 2.5, 3, 5, 10]) if (m * p >= rough) return m * p;
  return 10 * p;
}
function xMaxNow() {
  if (MODE !== "free") return niceCeil(Math.max(...CONFIG.xValues) * 1.1);
  const xs = allPoints().map(p => p.x);
  return niceCeil(Math.max(CONFIG.xMaxHint || 1, ...(xs.length ? xs : [0]).map(v => v * 1.12)));
}
function yMaxNow() {
  const ys = allPoints().map(p => p.y);
  return niceCeil(Math.max(CONFIG.yMaxHint || 1, ...(ys.length ? ys : [0]).map(v => v * 1.12)));
}
/* 데이터 값 → SVG 좌표 변환 함수 쌍 (px: x→가로, py: y→세로) */
const scales = (xmax, ymax) => ({
  px: x => M.l + (x / xmax) * plotW,
  py: y => M.t + plotH - (y / ymax) * plotH,
});

const SVGNS = "http://www.w3.org/2000/svg";
function el(name, attrs = {}, parent = null) {
  const node = document.createElementNS(SVGNS, name);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (parent) parent.appendChild(node);
  return node;
}
function fmt(v) { return (+v.toFixed(2)).toLocaleString("ko-KR"); }

/* 축·격자·라벨을 그리고 { s, xmax, ymax, ptLayer, trendLayer, guideLayer } 반환 */
function drawChart(svg, xmax, ymax) {
  svg.setAttribute("viewBox", `0 0 ${VB.w} ${VB.h}`);
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label",
    `${CONFIG.title} 그래프 — 가로축 ${CONFIG.xLabel}(${CONFIG.xUnit}), 세로축 ${CONFIG.yLabel}(${CONFIG.yUnit})`);
  svg.innerHTML = "";
  const s = scales(xmax, ymax);
  const grid = el("g", { class: "grid" }, svg);
  const ticksG = el("g", { class: "ticks" }, svg);
  const axis = el("g", { class: "axis" }, svg);

  for (let x = tickStep(xmax); x <= xmax + 1e-9; x += tickStep(xmax)) {
    el("line", { x1: s.px(x), y1: M.t, x2: s.px(x), y2: M.t + plotH }, grid);
    el("text", { x: s.px(x), y: M.t + plotH + 26, "text-anchor": "middle" }, ticksG)
      .textContent = fmt(x);
  }
  for (let y = tickStep(ymax); y <= ymax + 1e-9; y += tickStep(ymax)) {
    el("line", { x1: M.l, y1: s.py(y), x2: M.l + plotW, y2: s.py(y) }, grid);
    el("text", { x: M.l - 12, y: s.py(y) + 6, "text-anchor": "end" }, ticksG)
      .textContent = fmt(y);
  }
  el("line", { class: "axis-line", x1: M.l, y1: M.t + plotH, x2: M.l + plotW, y2: M.t + plotH }, axis);
  el("line", { class: "axis-line", x1: M.l, y1: M.t + plotH, x2: M.l, y2: M.t }, axis);
  el("text", { x: M.l - 12, y: M.t + plotH + 26, "text-anchor": "end", class: "ticks" }, ticksG)
    .textContent = "0";

  el("text", { class: "axis-label", x: M.l + plotW / 2, y: VB.h - 16, "text-anchor": "middle" }, svg)
    .textContent = `${CONFIG.xLabel} (${CONFIG.xUnit})`;
  el("text", {
    class: "axis-label", x: 24, y: M.t + plotH / 2, "text-anchor": "middle",
    transform: `rotate(-90 24 ${M.t + plotH / 2})`,
  }, svg).textContent = `${CONFIG.yLabel} (${CONFIG.yUnit})`;

  // 추세선이 플롯 영역 밖으로 나가지 않게 클리핑
  const clipId = "clip-" + svg.id;
  const clip = el("clipPath", { id: clipId }, el("defs", {}, svg));
  el("rect", { x: M.l, y: M.t, width: plotW, height: plotH }, clip);

  const trendLayer = el("g", { "clip-path": `url(#${clipId})` }, svg);
  const guideLayer = el("g", {}, svg);
  const ptLayer = el("g", {}, svg);
  return { s, xmax, ymax, ptLayer, trendLayer, guideLayer };
}

/* ============================================================
   §3 점 그리기
   ============================================================ */
function drawPoint(layer, s, p, { ghost = false, pop = false, r = 9 } = {}) {
  const c = el("circle", {
    class: "pt" + (ghost ? " ghost" : "") + (pop ? " pop" : ""),
    cx: s.px(p.x), cy: s.py(p.y), r: ghost ? 6 : r,
    "transform-origin": `${s.px(p.x)}px ${s.py(p.y)}px`,
  }, layer);
  if (!ghost && p.s === 1) {                  // 2번째 계열은 링(○) 마커
    c.style.fill = "var(--surface-1)";
    c.style.stroke = groupColor(p.g);
    c.style.strokeWidth = 4;
  } else {
    c.style.fill = ghost ? "var(--text-muted)" : groupColor(p.g);
  }
  c.dataset.key = `${p.g}:${p.i}:${p.s}`;
  const sName = MODE === "dual" ? ` ${CONFIG.ySeries[p.s]}` : "";
  c.dataset.tip = `${CONFIG.groupNames[p.g]}${sName} · ${CONFIG.xLabel} ${fmt(p.x)}${CONFIG.xUnit} → ${CONFIG.yLabel} ${fmt(p.y)}${CONFIG.yUnit}`;
  if (!ghost) {                               // 키보드(Tab)·스크린리더로도 점 값에 접근
    c.setAttribute("tabindex", "0");
    c.setAttribute("aria-label", c.dataset.tip);
  }
  return c;
}

/* 점이 찍힐 때 축에서 점까지 안내선 (x값 따라 →, y값 따라 ↑) */
function drawGuides(layer, s, p, color) {
  layer.innerHTML = "";
  for (const [x1, y1] of [[s.px(p.x), s.py(0)], [s.px(0), s.py(p.y)]]) {
    const ln = el("line", { class: "guide", x1, y1, x2: s.px(p.x), y2: s.py(p.y) }, layer);
    ln.style.stroke = color;
  }
}

/* ============================================================
   §4 추세선
   두 갈래: (a) 수식 적합(fitTrend) — proportional/linear/inverse,
            (b) 평균 곡선(smooth) — 각 x의 학급 평균을 단조 3차 곡선으로 연결
   computeTrend가 CONFIG.trendline에 따라 골라 통일된 형태로 반환한다.
   ============================================================ */
function fitTrend(pts) {                       // 최소제곱 (closed-form)
  if (pts.length < 2) return null;
  if (CONFIG.trendline === "proportional") {   // y = ax (원점 통과)
    let sxy = 0, sxx = 0;
    for (const p of pts) { sxy += p.x * p.y; sxx += p.x * p.x; }
    return sxx ? { type: "line", a: sxy / sxx, b: 0 } : null;
  }
  if (CONFIG.trendline === "inverse") {        // y = a / x^n (반비례)
    const n = CONFIG.trendPower === 2 ? 2 : 1;
    let syx = 0, sxx = 0;
    for (const p of pts) {
      if (p.x <= 0) continue;
      const ix = 1 / Math.pow(p.x, n);
      syx += p.y * ix; sxx += ix * ix;
    }
    return sxx ? { type: "inverse", a: syx / sxx, n } : null;
  }
  let sx = 0, sy = 0, sxy = 0, sxx = 0;        // y = ax + b
  for (const p of pts) { sx += p.x; sy += p.y; sxy += p.x * p.y; sxx += p.x * p.x; }
  const n = pts.length, d = n * sxx - sx * sx;
  if (!d) return null;
  const a = (n * sxy - sx * sy) / d;
  return { type: "line", a, b: (sy - a * sx) / n };
}

/* smooth 1단계: 같은 x(허용 오차 안)의 y를 평균 → x 오름차순 [{x,y}] */
function smoothAverages(pts) {
  const sorted = [...pts].sort((a, b) => a.x - b.x);
  const tol = xMaxNow() * 0.02;               // 이 간격 안의 x는 같은 측정점으로 취급
  const bins = [];
  for (const p of sorted) {
    const last = bins[bins.length - 1];
    if (last && p.x - last.x0 <= tol) { last.sx += p.x; last.sy += p.y; last.n++; }
    else bins.push({ x0: p.x, sx: p.x, sy: p.y, n: 1 });
  }
  return bins.map(b => ({ x: b.sx / b.n, y: b.sy / b.n }));
}

/* smooth 2단계: 단조 3차 보간(Fritsch–Carlson) 접선 — 점 사이에서
   출렁이거나(overshoot) 데이터 범위를 벗어나지 않는 부드러운 곡선을 보장 */
function monotoneTangents(P) {
  const n = P.length, m = [], t = [];
  for (let i = 0; i < n - 1; i++) m.push((P[i + 1].y - P[i].y) / (P[i + 1].x - P[i].x));
  t[0] = m[0]; t[n - 1] = m[n - 2];
  for (let i = 1; i < n - 1; i++) t[i] = (m[i - 1] * m[i] <= 0) ? 0 : (m[i - 1] + m[i]) / 2;
  for (let i = 0; i < n - 1; i++) {            // 단조성 제한
    if (m[i] === 0) { t[i] = 0; t[i + 1] = 0; continue; }
    const a = t[i] / m[i], b = t[i + 1] / m[i], h = Math.hypot(a, b);
    if (h > 3) { t[i] = m[i] * 3 * a / h; t[i + 1] = m[i] * 3 * b / h; }
  }
  return t;
}

/* smooth 3단계: 접선 → SVG 베지어 경로 문자열 (s는 좌표 변환) */
function smoothPathD(P, s) {
  const t = monotoneTangents(P);
  let d = `M ${s.px(P[0].x)} ${s.py(P[0].y)}`;
  for (let i = 0; i < P.length - 1; i++) {
    const dx = P[i + 1].x - P[i].x;
    d += ` C ${s.px(P[i].x + dx / 3)} ${s.py(P[i].y + t[i] * dx / 3)},`
      + ` ${s.px(P[i + 1].x - dx / 3)} ${s.py(P[i + 1].y - t[i + 1] * dx / 3)},`
      + ` ${s.px(P[i + 1].x)} ${s.py(P[i + 1].y)}`;
  }
  return d;
}

/* 추세 계산 결과를 한 형태로: {kind:"fit", fit} | {kind:"smooth", curves:[{s,P}]} | null */
function computeTrend(pts) {
  if (!CONFIG.trendline) return null;
  if (CONFIG.trendline === "smooth") {
    const seriesCount = MODE === "dual" ? 2 : 1;
    const curves = [];
    for (let s = 0; s < seriesCount; s++) {
      const P = smoothAverages(pts.filter(p => p.s === s));
      if (P.length >= 2) curves.push({ s, P });   // 곡선엔 서로 다른 x 2개 이상 필요
    }
    return curves.length ? { kind: "smooth", curves } : null;
  }
  const fit = fitTrend(pts);
  return fit ? { kind: "fit", fit } : null;
}

function drawTrend(layer, chart, trend, animate) {
  layer.innerHTML = "";
  if (!trend) return;
  if (REDUCED_MOTION) animate = false;
  const { s, xmax, ymax } = chart;

  const addPath = (d, dashed) => {
    const path = el("path", { class: "trendline" + (dashed ? " dashed" : "") }, layer);
    path.setAttribute("d", d);
    if (!animate) return;
    if (dashed) {                              // 점선은 dashoffset 기법과 충돌 → 페이드인
      path.style.opacity = 0;
      path.style.transition = "opacity 1.2s ease";
      requestAnimationFrame(() => requestAnimationFrame(() => { path.style.opacity = 1; }));
    } else {                                   // 실선은 그려지는 드로잉 애니메이션
      const len = path.getTotalLength();
      path.style.strokeDasharray = len;
      path.style.strokeDashoffset = len;
      path.style.transition = "stroke-dashoffset 1.4s ease";
      requestAnimationFrame(() => requestAnimationFrame(() => { path.style.strokeDashoffset = 0; }));
    }
  };

  if (trend.kind === "smooth") {
    for (const c of trend.curves) addPath(smoothPathD(c.P, s), c.s === 1);
    return;
  }
  const fit = trend.fit;
  if (fit.type === "inverse") {
    if (fit.a <= 0) return;                    // 반비례가 아닌 데이터
    // 곡선이 y축 상단(ymax)을 뚫고 올라가는 지점부터 오른쪽 끝까지 표본화
    const x0 = Math.max(Math.pow(fit.a / (ymax * 1.02), 1 / fit.n), xmax / 400);
    const seg = [];
    for (let k = 0; k <= 100; k++) {
      const x = x0 + (xmax - x0) * (k / 100);
      seg.push(`${k ? "L" : "M"} ${s.px(x)} ${s.py(fit.a / Math.pow(x, fit.n))}`);
    }
    addPath(seg.join(" "), false);
  } else {
    addPath(`M ${s.px(0)} ${s.py(fit.b)} L ${s.px(xmax)} ${s.py(fit.a * xmax + fit.b)}`, false);
  }
}

/* 종합 씬 아래에 추세선을 말로 읽어주는 문구 */
function trendReadout(trend, ptCount) {
  const tail = ` <span style="color:var(--text-muted)">(점 ${ptCount}개로 계산)</span>`;
  if (!trend) return "점이 2개 이상 있어야 추세선을 그릴 수 있습니다";
  if (trend.kind === "smooth") {
    const what = MODE === "dual"
      ? `<b>● ${esc(CONFIG.ySeries[0])}</b>: 실선 · <b>○ ${esc(CONFIG.ySeries[1])}</b>: 점선`
      : "";
    return `추세선: 각 ${esc(CONFIG.xLabel)}에서 <b>학급 평균</b>을 부드럽게 이은 곡선${what ? " — " + what : ""}${tail}`;
  }
  const fit = trend.fit;
  if (fit.type === "inverse") {
    return `추세선: <b>${esc(CONFIG.yLabel)} ≈ ${fmt(fit.a)} ÷ ${esc(CONFIG.xLabel)}${fit.n === 2 ? "²" : ""}</b>${tail}`;
  }
  const bTxt = CONFIG.trendline === "linear" && Math.abs(fit.b) > 1e-9
    ? ` ${fit.b >= 0 ? "+" : "−"} ${fmt(Math.abs(fit.b))}` : "";
  return `추세선: <b>${esc(CONFIG.yLabel)} ≈ ${fmt(fit.a)} × ${esc(CONFIG.xLabel)}${bTxt}</b>${tail}`;
}

/* ============================================================
   §5 씬 렌더링
   ============================================================ */
const $ = sel => document.querySelector(sel);
/* config 문자열(라벨·조 이름 등)을 innerHTML에 넣을 땐 반드시 이것을 거친다 */
const esc = s => String(s).replace(/[&<>"]/g,
  c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const sceneEls = {
  intro: $("#scene-intro"),
  group: $("#scene-group"),
  summary: $("#scene-summary"),
};
let groupChart = null;   // 현재 조 씬의 { s, ptLayer, ... }

function renderIntro() {
  $("#intro-title").textContent = CONFIG.title;
  $("#intro-hint").innerHTML =
    `가로축은 <b>${esc(CONFIG.xLabel)}(${esc(CONFIG.xUnit)})</b>, ` +
    `세로축은 <b>${esc(CONFIG.yLabel)}(${esc(CONFIG.yUnit)})</b> — ` +
    `측정한 두 값이 만나는 곳에 점을 찍습니다`;
  const svg = $("#svg-intro");
  svg.classList.remove("draw-in");
  drawChart(svg, xMaxNow(), yMaxNow());
  void svg.getBoundingClientRect();          // 리플로 → 애니메이션 재시작
  svg.classList.add("draw-in");
}

/* 그 행의 입력칸이 모두 채워졌는가 (행 하이라이트 기준) */
function rowComplete(g, i) {
  if (MODE === "fixed") return state.data[g][i] != null;
  return state.data[g][i].every(v => v != null);
}

function renderGroup(g) {
  state.group = g;
  const scene = sceneEls.group;
  scene.style.setProperty("--group-color", groupColor(g));
  scene.querySelector(".group-badge .swatch").style.background = groupColor(g);
  $("#group-name").textContent = CONFIG.groupNames[g];
  scene.querySelector(".table-hint").textContent = MODE === "free"
    ? "측정한 두 값을 모두 넣고 Enter — 표의 숫자가 그래프의 점이 됩니다"
    : "값을 넣고 Enter — 표의 숫자가 그래프의 점이 됩니다";

  // 표 (모드별 열 구성)
  const table = $("#group-table");
  table.className = "data-table" + (N >= 8 ? " compact" : "");
  const inputCell = (i, f, val) =>
    `<td class="y-cell"><input type="number" min="0" step="any" inputmode="decimal"
        data-i="${i}" data-f="${f}" value="${val ?? ""}"></td>`;
  const xHead = `<th>${esc(CONFIG.xLabel)}(${esc(CONFIG.xUnit)})</th>`;
  const yHead = `<th>${esc(CONFIG.yLabel)}(${esc(CONFIG.yUnit)})</th>`;
  let html;
  if (MODE === "dual") {
    html = `<tr>${xHead}<th>● ${esc(CONFIG.ySeries[0])}</th><th>○ ${esc(CONFIG.ySeries[1])}</th></tr>` +
      CONFIG.xValues.map((x, i) => `
        <tr class="${rowComplete(state.group, i) ? "landed" : ""}">
          <td class="x-cell">${fmt(x)}</td>
          ${inputCell(i, 0, state.data[g][i][0])}${inputCell(i, 1, state.data[g][i][1])}
        </tr>`).join("");
  } else if (MODE === "free") {
    html = `<tr>${xHead}${yHead}</tr>` +
      state.data[g].map((cell, i) => `
        <tr class="${rowComplete(g, i) ? "landed" : ""}">
          ${inputCell(i, 0, cell[0])}${inputCell(i, 1, cell[1])}
        </tr>`).join("");
  } else {
    html = `<tr>${xHead}${yHead}</tr>` +
      CONFIG.xValues.map((x, i) => `
        <tr class="${rowComplete(g, i) ? "landed" : ""}">
          <td class="x-cell">${fmt(x)}</td>
          ${inputCell(i, 0, state.data[g][i])}
        </tr>`).join("");
  }
  table.innerHTML = html;
  table.querySelectorAll("input").forEach(inp => {
    inp.addEventListener("keydown", e => {
      if (e.key === "Enter") { e.preventDefault(); commitInput(inp, true); }
    });
    inp.addEventListener("blur", () => commitInput(inp, false));
  });

  // 그래프: 이전 조들은 회색 잔상, 이번 조는 제 색으로
  renderGroupChartOnly();
  const firstEmpty = [...table.querySelectorAll("input")].find(x => x.value === "");
  if (firstEmpty) firstEmpty.focus();
}

function commitInput(inp, fly) {
  const g = state.group, i = +inp.dataset.i, f = +inp.dataset.f;
  const prev = getField(g, i, f);
  const v = inp.value.trim() === "" ? null : +inp.value;
  if (v !== null && (!isFinite(v) || v < 0)) {   // 음수·비정상값은 되돌림
    inp.value = prev ?? "";
    return;
  }
  if (v === prev) { if (fly) focusNextInput(inp); return; }
  setField(g, i, f, v);
  saveData();

  inp.closest("tr").classList.toggle("landed", rowComplete(g, i));

  // 이번 입력으로 (다시) 생긴 점 — 날리기 대상
  const affected = [];
  if (MODE === "dual") {
    if (v != null) affected.push({ g, i, s: f, x: CONFIG.xValues[i], y: v });
  } else if (MODE === "free") {
    const [x, y] = state.data[g][i];
    if (x != null && y != null) affected.push({ g, i, s: 0, x, y });
  } else if (v != null) {
    affected.push({ g, i, s: 0, x: CONFIG.xValues[i], y: v });
  }

  const animate = fly && !REDUCED_MOTION;      // 움직임 줄이기면 비행 없이 즉시 반영
  const keyOf = p => `${p.g}:${p.i}:${p.s}`;
  if (animate) affected.forEach(p => inFlight.add(keyOf(p)));
  renderGroupChartOnly();                      // 축 확장 포함 재렌더

  if (animate) {
    for (const p of affected) {
      const key = keyOf(p);
      const target = findOwnCircle(key);
      if (!target) { inFlight.delete(key); continue; }
      flyDot(inp.closest("td"), target, groupColor(g), () => {
        inFlight.delete(key);
        const c = findOwnCircle(key);          // 재렌더됐어도 현재 차트에서 다시 찾음
        if (c) { c.style.opacity = ""; c.classList.add("pop"); }
        drawGuides(groupChart.guideLayer, groupChart.s, p, groupColor(g));
      });
    }
  }
  if (fly) focusNextInput(inp);
}

/* 현재 조 씬 차트에서 key(g:i:s)에 해당하는 (잔상 아닌) 원을 찾는다 */
function findOwnCircle(key) {
  return groupChart.ptLayer.querySelector(`circle:not(.ghost)[data-key="${key}"]`);
}

/* 아직 날아가는 중인 점은 착지 전까지 차트에서 숨긴다 */
const inFlight = new Set();

function renderGroupChartOnly() {
  const g = state.group;
  const svg = $("#svg-group");
  groupChart = drawChart(svg, xMaxNow(), yMaxNow());
  for (const p of allPoints()) {
    if (p.g !== g) { drawPoint(groupChart.ptLayer, groupChart.s, p, { ghost: true }); continue; }
    const c = drawPoint(groupChart.ptLayer, groupChart.s, p);
    if (inFlight.has(c.dataset.key)) c.style.opacity = 0;
  }
}

function focusNextInput(inp) {
  const inputs = [...$("#group-table").querySelectorAll("input")];
  const next = inputs[inputs.indexOf(inp) + 1];
  if (next) next.focus();
}

/* 표 셀 → 그래프 점으로 날아가는 애니메이션 */
function flyDot(cellEl, targetCircle, color, onLand) {
  const a = cellEl.getBoundingClientRect();
  const b = targetCircle.getBoundingClientRect();
  const dot = document.createElement("div");
  dot.className = "fly-dot";
  dot.style.background = color;
  dot.style.left = (a.left + a.width / 2 - 9) + "px";
  dot.style.top = (a.top + a.height / 2 - 9) + "px";
  document.body.appendChild(dot);
  void dot.getBoundingClientRect();
  dot.style.transform =
    `translate(${b.left + b.width / 2 - (a.left + a.width / 2)}px,` +
    ` ${b.top + b.height / 2 - (a.top + a.height / 2)}px)`;
  setTimeout(() => {
    dot.remove();
    if (onLand) onLand();
  }, 820);
}

function renderSummary(animateTrend = false) {
  // 범례 (조별 토글 + 추세선 토글)
  const legend = $("#legend");
  legend.innerHTML = "";
  CONFIG.groupNames.forEach((name, g) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "chip" + (state.visible[g] ? "" : " off");
    btn.innerHTML = `<span class="swatch" style="background:${groupColor(g)}"></span>${esc(name)}`;
    btn.addEventListener("click", () => {
      state.visible[g] = !state.visible[g];
      renderSummary();
    });
    legend.appendChild(btn);
  });
  if (MODE === "dual") {                      // 계열 마커 안내 (토글 아님)
    CONFIG.ySeries.forEach((name, si) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "chip info";
      chip.disabled = true;
      chip.innerHTML =
        `<span class="swatch${si ? " ring" : ""}"` +
        `${si ? "" : ' style="background:var(--text-secondary)"'}></span>${esc(name)}`;
      legend.appendChild(chip);
    });
  }
  if (CONFIG.trendline) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "chip trend-chip" + (state.trendOn ? "" : " off");
    btn.innerHTML = `<span class="swatch" style="background:var(--trend)"></span>추세선`;
    btn.addEventListener("click", () => {
      state.trendOn = !state.trendOn;
      renderSummary(state.trendOn);           // 켤 때만 드로잉 애니메이션
    });
    legend.appendChild(btn);
  }

  const svg = $("#svg-summary");
  const chart = drawChart(svg, xMaxNow(), yMaxNow());
  const pts = allPoints(true);

  // 조별로 시차를 두고 등장 (모이는 느낌 — 움직임 줄이기면 즉시)
  const stagger = REDUCED_MOTION ? 0 : 130;
  CONFIG.groupNames.forEach((_, g) => {
    setTimeout(() => {
      for (const p of pts.filter(p => p.g === g))
        drawPoint(chart.ptLayer, chart.s, p, { pop: true });
    }, g * stagger);
  });

  // 추세선 + 읽어주기
  const readout = $("#trend-readout");
  if (state.trendOn && CONFIG.trendline) {
    const trend = computeTrend(pts);
    setTimeout(() => drawTrend(chart.trendLayer, chart, trend, animateTrend),
      G * stagger + 100);
    readout.innerHTML = trendReadout(trend, pts.length);
  } else {
    readout.textContent = "";
  }
}

/* ============================================================
   §6 내보내기 — CSV(측정값 표), PNG(종합 그래프)
   ============================================================ */
function downloadBlob(filename, blob) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 3000);
}

function exportCSV() {
  const esc = v => {
    const t = String(v);
    return /[",\n]/.test(t) ? '"' + t.replace(/"/g, '""') + '"' : t;
  };
  const xh = `${CONFIG.xLabel}(${CONFIG.xUnit})`;
  const yh = `${CONFIG.yLabel}(${CONFIG.yUnit})`;
  const rows = [[CONFIG.title], []];           // 첫 줄 제목, 둘째 줄 공백
  if (MODE === "free") {                       // 세로 형식: 조, x, y
    rows.push(["조", xh, yh]);
    for (const p of allPoints()) rows.push([CONFIG.groupNames[p.g], p.x, p.y]);
  } else if (MODE === "dual") {                // 가로 형식: 조 × 계열 행
    rows.push([`세로축: ${yh}`]);
    rows.push(["조", "계열", ...CONFIG.xValues.map(x => `${xh.split("(")[0]} ${fmt(x)}${CONFIG.xUnit}`)]);
    CONFIG.groupNames.forEach((name, g) =>
      CONFIG.ySeries.forEach((sn, si) =>
        rows.push([name, sn, ...state.data[g].map(cell => cell[si] ?? "")])));
  } else {                                     // 가로 형식: 조 행
    rows.push([`세로축: ${yh}`]);
    rows.push(["조", ...CONFIG.xValues.map(x => `${xh.split("(")[0]} ${fmt(x)}${CONFIG.xUnit}`)]);
    CONFIG.groupNames.forEach((name, g) =>
      rows.push([name, ...state.data[g].map(v => v ?? "")]));
  }
  // ﻿(BOM): 엑셀이 UTF-8 한글을 바로 읽게 하는 표식
  const csv = "﻿" + rows.map(r => r.map(esc).join(",")).join("\r\n");
  downloadBlob(`${CONFIG.slug || "data"}.csv`, new Blob([csv], { type: "text/csv;charset=utf-8" }));
}

/* 종합 그래프를 PNG로 저장. 화면의 SVG 대신 화면 밖에 애니메이션 없이
   새로 그려서 찍는다 — 어느 씬에서 눌러도, 점 등장 중이어도 완성본이 나온다. */
function exportPNG() {
  const tmp = el("svg");
  tmp.id = "svg-export";
  tmp.style.cssText = `position:fixed;left:-10000px;top:0;width:${VB.w}px;height:${VB.h}px`;
  document.body.appendChild(tmp);
  const chart = drawChart(tmp, xMaxNow(), yMaxNow());
  const pts = allPoints(true);
  for (const p of pts) drawPoint(chart.ptLayer, chart.s, p);
  if (state.trendOn && CONFIG.trendline) drawTrend(chart.trendLayer, chart, computeTrend(pts), false);

  // CSS 클래스는 PNG 직렬화에 반영되지 않으므로 계산된 스타일을 인라인으로 복사
  const PROPS = ["fill", "stroke", "stroke-width", "stroke-dasharray", "stroke-linecap",
                 "font-family", "font-size", "font-weight", "opacity"];
  for (const node of tmp.querySelectorAll("*")) {
    const cs = getComputedStyle(node);
    for (const prop of PROPS) node.style.setProperty(prop, cs.getPropertyValue(prop));
  }
  const bg = el("rect", { x: 0, y: 0, width: VB.w, height: VB.h });
  bg.style.fill = getComputedStyle(document.body).getPropertyValue("--surface-1").trim() || "#fff";
  tmp.insertBefore(bg, tmp.firstChild);
  tmp.setAttribute("width", VB.w);
  tmp.setAttribute("height", VB.h);
  // 화면 밖 배치용 style이 이미지로 렌더링될 때 내용을 밀어내므로 반드시 제거
  tmp.removeAttribute("style");
  const xml = new XMLSerializer().serializeToString(tmp);
  tmp.remove();

  const img = new Image();
  img.onload = () => {
    const scale = 2;                           // 2배 해상도로 선명하게
    const canvas = document.createElement("canvas");
    canvas.width = VB.w * scale;
    canvas.height = VB.h * scale;
    canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
    canvas.toBlob(b => downloadBlob(`${CONFIG.slug || "graph"}.png`, b), "image/png");
  };
  img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(xml);
}

$("#btn-csv").addEventListener("click", exportCSV);
$("#btn-png").addEventListener("click", exportPNG);

/* ============================================================
   §7 지우기·되돌리기
   지우기 전에 스냅숏을 떠 두고, 토스트의 "되돌리기"(5초)로 복구한다.
   ============================================================ */
let undoSnapshot = null;
let toastTimer = 0;

function showToast(msg, withUndo = true) {
  $("#toast-msg").textContent = msg;
  $("#btn-undo").hidden = !withUndo;             // 경고성 토스트엔 되돌리기 버튼 없음
  $("#toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { $("#toast").hidden = true; }, 5000);
}

/* groupIdx가 null이면 전체, 숫자면 그 조만 지운다 */
function doClear(groupIdx) {
  undoSnapshot = JSON.parse(JSON.stringify(state.data));
  if (groupIdx == null) {
    state.data = emptyData();
    state.visible = Array(G).fill(true);
    state.trendOn = false;
  } else {
    state.data[groupIdx] = emptyRow();
  }
  saveData();
}

$("#btn-undo").addEventListener("click", () => {
  if (!undoSnapshot) return;
  state.data = undoSnapshot;
  undoSnapshot = null;
  saveData();
  $("#toast").hidden = true;
  showScene(state.scene);                      // 현재 씬 다시 그림
});

$("#btn-reset").addEventListener("click", () => {
  if (!confirm("모든 조의 입력값을 지울까요? (다음 반 수업 시작)")) return;
  doClear(null);
  showScene(0);
  showToast("모든 조의 값을 지웠습니다");
});

$("#btn-clear-group").addEventListener("click", () => {
  const g = state.group;
  doClear(g);
  renderGroup(g);
  showToast(`${CONFIG.groupNames[g]} 값을 지웠습니다`);
});

/* ============================================================
   §8 씬 전환·내비게이션·전역 UI
   ============================================================ */
function sceneKind(i) { return i === 0 ? "intro" : i <= G ? "group" : "summary"; }

function showScene(i) {
  state.scene = Math.max(0, Math.min(SCENES - 1, i));
  const kind = sceneKind(state.scene);
  for (const [k, elm] of Object.entries(sceneEls)) elm.classList.toggle("active", k === kind);
  if (kind === "intro") renderIntro();
  else if (kind === "group") renderGroup(state.scene - 1);
  else renderSummary();
  $("#btn-prev").disabled = state.scene === 0;
  $("#btn-next").disabled = state.scene === SCENES - 1;
  renderDots();
}

function renderDots() {
  const dots = $("#dots");
  dots.innerHTML = "";
  for (let i = 0; i < SCENES; i++) {
    const d = document.createElement("button");
    d.type = "button";
    d.className = i === state.scene ? "on" : "";
    d.title = sceneKind(i) === "intro" ? "도입"
      : sceneKind(i) === "group" ? CONFIG.groupNames[i - 1] : "종합";
    d.setAttribute("aria-label", d.title + " 씬으로 이동");
    d.addEventListener("click", () => showScene(i));
    dots.appendChild(d);
  }
}

$("#btn-prev").addEventListener("click", () => showScene(state.scene - 1));
$("#btn-next").addEventListener("click", () => showScene(state.scene + 1));

/* 키보드: ←/→/Space 이전·다음, Home/0 도입, End/9 종합, 1~6 해당 조
   (프레젠터 리모컨의 이전/다음 버튼은 ←/→로 들어오므로 그대로 동작) */
document.addEventListener("keydown", e => {
  if (e.target.tagName === "INPUT") return;    // 표 입력 중에는 씬 이동 금지
  if (e.key === "ArrowRight" || e.key === " ") { e.preventDefault(); showScene(state.scene + 1); }
  else if (e.key === "ArrowLeft") { e.preventDefault(); showScene(state.scene - 1); }
  else if (e.key === "Home") { e.preventDefault(); showScene(0); }
  else if (e.key === "End") { e.preventDefault(); showScene(SCENES - 1); }
  else if (/^[0-9]$/.test(e.key)) {
    const d = +e.key;
    if (d === 0) showScene(0);
    else if (d <= G) showScene(d);
    else if (d === 9) showScene(SCENES - 1);
  }
});

$("#btn-fullscreen").addEventListener("click", () => {
  if (document.fullscreenElement) document.exitFullscreen();
  else document.documentElement.requestFullscreen();
});

/* 테마 토글 — 기본은 OS 설정을 따르고, 🌓를 누르면 반대 테마로 고정.
   (CSS의 다크 토큰 A/B 블록과 짝을 이룬다. 저장 키는 앱 공통) */
const THEME_KEY = "group_graph::theme";
function effectiveDark() {
  const t = document.documentElement.dataset.theme;
  return t ? t === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
}
{
  const saved = localStorage.getItem(THEME_KEY);
  if (saved === "dark" || saved === "light") document.documentElement.dataset.theme = saved;
}
$("#btn-theme").addEventListener("click", () => {
  const next = effectiveDark() ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  localStorage.setItem(THEME_KEY, next);
  showScene(state.scene);                      // 색이 바뀌었으니 현재 씬 다시 그림
});

/* 툴팁 — 마우스 오버 + 점 클릭(터치) + 키보드 포커스 모두 지원 */
const tooltip = $("#tooltip");
function showTipAt(c, x, y) {
  tooltip.textContent = c.dataset.tip;
  tooltip.style.display = "block";
  tooltip.style.left = (x + 14) + "px";
  tooltip.style.top = (y - 34) + "px";
}
function hideTip() { tooltip.style.display = "none"; }
document.addEventListener("mousemove", e => {
  const c = e.target.closest ? e.target.closest("circle.pt") : null;
  if (c && c.dataset.tip) showTipAt(c, e.clientX, e.clientY);
  else hideTip();
});
document.addEventListener("click", e => {      // 터치 탭
  const c = e.target.closest ? e.target.closest("circle.pt") : null;
  if (c && c.dataset.tip) {
    const r = c.getBoundingClientRect();
    showTipAt(c, r.right, r.top);
  }
});
document.addEventListener("focusin", e => {    // Tab 키로 점 순회
  const c = e.target.closest ? e.target.closest("circle.pt") : null;
  if (c && c.dataset.tip) {
    const r = c.getBoundingClientRect();
    showTipAt(c, r.right, r.top);
  }
});
document.addEventListener("focusout", hideTip);

/* ============================================================
   시작
   ============================================================ */
document.title = "조별 실험 그래프 — " + CONFIG.title;
$("#bar-title").textContent = CONFIG.title;
showScene(0);
