"use strict";

const SVGNS = "http://www.w3.org/2000/svg";
const RES = ["WOOD", "BRICK", "SHEEP", "WHEAT", "ORE", "DESERT"];
const RES_COLOR = {
  WOOD: "#3f7d34", BRICK: "#c1612f", SHEEP: "#a9d06b",
  WHEAT: "#e6b422", ORE: "#7e8a98", DESERT: "#e3d3a8",
};
const NUMS = [2, 3, 4, 5, 6, 8, 9, 10, 11, 12];
const REQ_RES = { WOOD: 4, BRICK: 3, SHEEP: 4, WHEAT: 4, ORE: 3, DESERT: 1 };
const REQ_NUM = { 2: 1, 3: 2, 4: 2, 5: 2, 6: 2, 8: 2, 9: 2, 10: 2, 11: 2, 12: 1 };
const RED_NUMS = new Set([6, 8]);
// dots under each token = number of ways to roll it (as on the real tokens)
const PIPS = { 2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 8: 5, 9: 4, 10: 3, 11: 2, 12: 1 };
const PCOLOR = { P1: "#e0663f", P2: "#4da3ff" };
// Required existing placements (ordered S=settlement, R=road) before analysis, per seat.
const SEAT_PLAN = {
  FIRST: [],
  SECOND: [{ p: "P1", k: "S" }, { p: "P1", k: "R" }],
  FIRST_FINAL: [
    { p: "P1", k: "S" }, { p: "P1", k: "R" },
    { p: "P2", k: "S" }, { p: "P2", k: "R" },
    { p: "P2", k: "S" }, { p: "P2", k: "R" },
  ],
};
// How many settlement+road placements the user must make in practice, per seat.
const USER_PIECES = { FIRST: 1, SECOND: 2, FIRST_FINAL: 1 };

let mode = "advisor"; // "advisor" | "practice"
let geom = null;
let board = null;
let paint = null;     // active palette paint ({type:"res"|"num", value}) or null
let seat = "FIRST";
// hex editor (advisor): which hex is open + its pending resource/number selection
let editingHex = null;
let hexEditRes = null;
let hexEditNum = null;
let draftPieces = []; // advisor: ordered existing draft pieces [{p, k:"S"|"R", node|edge}]
let recs = [];
let selected = null;

// practice state
let puzzle = null;                          // OpeningPlacementRequest from the server
let practiceScenario = "FIRST";             // chosen in the scenario modal
let userPieces = [];                        // ordered [{k:"S",node} | {k:"R",edge}], S,R,S,R…
let practiceResult = null;
let practiceSel = null;                     // a ranking row the user clicked to inspect
const SCORE_KEY = "catanPracticeScoreV2";   // bumped: scoring model changed to 0–10
const BASE_SCORE = { points: 0, maxPoints: 0, streak: 0, attempts: 0, last: null };
let score = loadScore();

const $ = (id) => document.getElementById(id);
const el = (tag, attrs) => {
  const e = document.createElementNS(SVGNS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  return e;
};

async function init() {
  geom = await (await fetch("/api/layout")).json();
  const svg = $("board");
  const SCALE = 1.4; // display larger than the viewBox so the whole board scales up crisply
  svg.setAttribute("width", geom.width * SCALE);
  svg.setAttribute("height", geom.height * SCALE);
  svg.setAttribute("viewBox", `0 0 ${geom.width} ${geom.height}`);
  buildPalette();
  buildHexEditor();
  $("randomize").onclick = randomize;
  $("clear").onclick = clearBoard;
  $("seat").onchange = (e) => { seat = e.target.value; resetDraft(); render(); };
  $("analyze").onclick = analyze;
  // tabs
  $("tabAdvisor").onclick = () => setMode("advisor");
  $("tabPractice").onclick = () => setMode("practice");
  // hex editor modal
  $("hexApply").onclick = applyHexEdit;
  $("hexClearOne").onclick = clearHexEdit;
  $("hexCancel").onclick = closeHexModal;
  $("hexModal").onclick = (e) => { if (e.target.id === "hexModal") closeHexModal(); };
  // analyze info modal
  $("analyzeInfo").onclick = () => $("infoModal").classList.remove("hidden");
  $("infoClose").onclick = () => $("infoModal").classList.add("hidden");
  $("infoModal").onclick = (e) => { if (e.target.id === "infoModal") $("infoModal").classList.add("hidden"); };
  // practice controls
  $("newPuzzle").onclick = newPuzzle;
  $("submitPlacement").onclick = submitPlacement;
  $("clearPlacement").onclick = () => { startUserAttempt(); render(); renderFeedback(); };
  $("changeScenario").onclick = showScenarioModal;
  $("resetScore").onclick = () => { score = { ...BASE_SCORE }; saveScore(); updateScoreboard(); };
  document.querySelectorAll("#scenarioModal [data-seat]").forEach((b) => {
    b.onclick = () => chooseScenario(b.dataset.seat);
  });
  $("scenarioModal").onclick = (e) => { if (e.target.id === "scenarioModal" && puzzle) hideScenarioModal(); };
  updateScoreboard();
  await loadClearBoard();
}

// Load a real board (for valid ports/structure) but start it visually empty.
async function loadClearBoard() {
  board = await (await fetch("/api/board/random")).json();
  board.hexes.forEach((h) => { h.resource = null; h.number = null; });
  resetDraft();
  render();
}

// ---- scenario modal --------------------------------------------------------
function showScenarioModal() { $("scenarioModal").classList.remove("hidden"); }
function hideScenarioModal() { $("scenarioModal").classList.add("hidden"); }

async function chooseScenario(seatChoice) {
  practiceScenario = seatChoice;
  hideScenarioModal();
  await newPuzzle();
}

// --------------------------------------------------------------------------- //
// Mode switching
// --------------------------------------------------------------------------- //
async function setMode(m) {
  mode = m;
  $("tabAdvisor").classList.toggle("active", m === "advisor");
  $("tabPractice").classList.toggle("active", m === "practice");
  $("advisorControls").classList.toggle("hidden", m !== "advisor");
  $("advisorResults").classList.toggle("hidden", m !== "advisor");
  $("practiceControls").classList.toggle("hidden", m !== "practice");
  $("practiceResults").classList.toggle("hidden", m !== "practice");
  if (m === "practice") { showScenarioModal(); return; }
  render();
}

function activeBoard() {
  return mode === "practice" && puzzle ? puzzle.board : board;
}

// ---- paint palette (the quick "select a paint, click hexes" method) --------
function buildPalette() {
  RES.forEach((r) => {
    const b = document.createElement("button");
    b.textContent = r[0] + r.slice(1).toLowerCase();
    b.style.background = RES_COLOR[r];
    b.style.color = "#0b1118";
    b.dataset.paint = "res:" + r;
    b.onclick = () => { paint = isPaint("res", r) ? null : { type: "res", value: r }; markActive(); };
    $("resourceSwatches").appendChild(b);
  });
  NUMS.forEach((n) => {
    const b = document.createElement("button");
    b.textContent = n;
    b.dataset.paint = "num:" + n;
    b.onclick = () => { paint = isPaint("num", n) ? null : { type: "num", value: n }; markActive(); };
    $("numberButtons").appendChild(b);
  });
}

function isPaint(type, value) { return paint && paint.type === type && paint.value === value; }

function markActive() {
  const key = paint ? paint.type + ":" + paint.value : "";
  document.querySelectorAll("[data-paint]").forEach((b) =>
    b.classList.toggle("active", b.dataset.paint === key)
  );
}

// Clicking a hex: paint it if a paint is selected, otherwise open the editor menu.
function clickHex(id) {
  if (mode !== "advisor") return;
  if (paint) paintHex(id);
  else openHexEditor(id);
}

function paintHex(id) {
  const h = board.hexes.find((x) => x.id === id);
  if (paint.type === "res") {
    h.resource = paint.value;
    if (paint.value === "DESERT") { h.number = null; board.robber_hex = id; }
  } else if (h.resource !== "DESERT") {
    h.number = paint.value;
  }
  render();
}

// ---- hex editor (click a hex to set its resource + number) -----------------
function buildHexEditor() {
  RES.forEach((r) => {
    const b = document.createElement("button");
    b.textContent = r[0] + r.slice(1).toLowerCase();
    b.style.background = RES_COLOR[r];
    b.style.color = "#0b1118";
    b.dataset.res = r;
    b.onclick = () => { hexEditRes = r; if (r === "DESERT") hexEditNum = null; updateHexHighlights(); };
    $("hexResChoices").appendChild(b);
  });
  NUMS.forEach((n) => {
    const b = document.createElement("button");
    b.textContent = n;
    b.dataset.num = n;
    if (RED_NUMS.has(n)) b.style.color = "#f0883e";
    b.onclick = () => { if (hexEditRes === "DESERT") return; hexEditNum = n; updateHexHighlights(); };
    $("hexNumChoices").appendChild(b);
  });
}

function updateHexHighlights() {
  document.querySelectorAll("#hexResChoices [data-res]").forEach((b) =>
    b.classList.toggle("active", b.dataset.res === hexEditRes)
  );
  const desert = hexEditRes === "DESERT";
  document.querySelectorAll("#hexNumChoices [data-num]").forEach((b) => {
    b.classList.toggle("active", !desert && Number(b.dataset.num) === hexEditNum);
    b.disabled = desert;
  });
}

function openHexEditor(id) {
  if (mode !== "advisor") return;
  const h = board.hexes.find((x) => x.id === id);
  editingHex = id;
  hexEditRes = h.resource || null;
  hexEditNum = h.number || null;
  updateHexHighlights();
  $("hexModal").classList.remove("hidden");
}

function closeHexModal() { editingHex = null; $("hexModal").classList.add("hidden"); }

function applyHexEdit() {
  const h = board.hexes.find((x) => x.id === editingHex);
  h.resource = hexEditRes;
  if (hexEditRes === "DESERT") { h.number = null; board.robber_hex = editingHex; }
  else h.number = hexEditNum;
  closeHexModal();
  render();
}

function clearHexEdit() {
  const h = board.hexes.find((x) => x.id === editingHex);
  h.resource = null;
  h.number = null;
  closeHexModal();
  render();
}

async function randomize() {
  board = await (await fetch("/api/board/random")).json();
  resetDraft();
  render();
}

function clearBoard() {
  board.hexes.forEach((h) => { h.resource = null; h.number = null; });
  resetDraft();
  render();
}

function resetDraft() {
  draftPieces = [];
  recs = [];
  selected = null;
  renderResults();
}

// advisor existing-placements, grouped by player for rendering / the request
function draftSettlements() {
  const o = {};
  draftPieces.filter((x) => x.k === "S").forEach((x) => { (o[x.p] = o[x.p] || []).push(x.node); });
  return o;
}
function draftRoads() {
  const o = {};
  draftPieces.filter((x) => x.k === "R").forEach((x) => { (o[x.p] = o[x.p] || []).push(x.edge); });
  return o;
}

// ---- editing ---------------------------------------------------------------
function clickNode(n) {
  if (mode === "practice") return clickNodePractice(n);
  // click a settlement already placed to remove it (and anything placed after)
  const idx = draftPieces.findIndex((x) => x.k === "S" && x.node === n.id);
  if (idx !== -1) { draftPieces.length = idx; render(); return; }
  const next = SEAT_PLAN[seat][draftPieces.length];
  if (next && next.k === "S") { draftPieces.push({ p: next.p, k: "S", node: n.id }); render(); }
}

function clickEdge(e) {
  if (mode === "practice") return clickEdgePractice(e);
  const idx = draftPieces.findIndex((x) => x.k === "R" && sameEdge(x.edge, [e.a, e.b]));
  if (idx !== -1) { draftPieces.length = idx; render(); return; }
  const next = SEAT_PLAN[seat][draftPieces.length];
  if (next && next.k === "R") { draftPieces.push({ p: next.p, k: "R", edge: [e.a, e.b] }); render(); }
}

// ---- rendering -------------------------------------------------------------
function render() {
  const svg = $("board");
  svg.replaceChildren();
  const b = activeBoard();
  if (!b) return;
  const s = geom.size;
  const corners = [
    [0, -1], [Math.sqrt(3) / 2, -0.5], [Math.sqrt(3) / 2, 0.5],
    [0, 1], [-Math.sqrt(3) / 2, 0.5], [-Math.sqrt(3) / 2, -0.5],
  ];
  const bHex = {};
  b.hexes.forEach((h) => (bHex[h.id] = h));

  geom.hexes.forEach((gh) => {
    const h = bHex[gh.id];
    const pts = corners
      .map(([cx, cy]) => `${(gh.x + cx * s).toFixed(1)},${(gh.y + cy * s).toFixed(1)}`)
      .join(" ");
    const poly = el("polygon", {
      points: pts,
      fill: h && h.resource ? RES_COLOR[h.resource] : "#243240",
      stroke: "#0b1118", "stroke-width": 2,
    });
    poly.style.cursor = mode === "advisor" ? "pointer" : "default";
    poly.onclick = () => clickHex(gh.id);
    svg.appendChild(poly);

    if (h && h.number != null) {
      const red = RED_NUMS.has(h.number);
      svg.appendChild(el("circle", { cx: gh.x, cy: gh.y, r: 16, fill: "#f3e9d2", stroke: "#0b1118" }));
      const t = el("text", {
        x: gh.x, y: gh.y, "text-anchor": "middle", "dominant-baseline": "central",
        "font-size": 14, "font-weight": "bold", fill: red ? "#c0392b" : "#222",
      });
      t.textContent = h.number;
      svg.appendChild(t);
      const pips = PIPS[h.number] || 0;
      const gap = 3.6;
      const x0 = gh.x - ((pips - 1) * gap) / 2;
      for (let k = 0; k < pips; k++) {
        svg.appendChild(el("circle", { cx: x0 + k * gap, cy: gh.y + 10, r: 1.5, fill: red ? "#c0392b" : "#444" }));
      }
    }
    // robber sits on the desert during setup — only show it once a desert exists
    if (b.robber_hex === gh.id && h && h.resource === "DESERT") {
      svg.appendChild(el("circle", { cx: gh.x, cy: gh.y, r: 9, fill: "#111", opacity: 0.55 }));
    }
  });

  geom.edges.forEach((e) => {
    // visible road slot (thin, non-interactive)
    svg.appendChild(el("line", {
      x1: e.x1, y1: e.y1, x2: e.x2, y2: e.y2,
      stroke: "#3a4b5c", "stroke-width": 4, "stroke-linecap": "round", "pointer-events": "none",
    }));
    // wider transparent hitbox on top, for easier clicking (no visual change)
    const hit = el("line", {
      x1: e.x1, y1: e.y1, x2: e.x2, y2: e.y2,
      stroke: "transparent", "stroke-width": 13, "stroke-linecap": "round",
    });
    hit.style.cursor = "pointer";
    hit.onclick = () => clickEdge(e);
    svg.appendChild(hit);
  });

  drawPorts(svg, b);

  if (mode === "advisor") {
    drawPieces(svg, draftSettlements(), draftRoads());
    if (selected) drawHighlight(svg, selected.placements, "#ffd23f");
  } else if (puzzle) {
    drawPieces(svg, puzzle.settlements || {}, puzzle.roads || {});       // the given priors
    drawPieces(svg, { P1: userSettlements() }, { P1: userRoads() });      // the user's answer
    if (practiceResult) {
      drawHighlight(svg, practiceResult.optimal_placements, "#ffd23f");
      if (practiceSel) drawHighlight(svg, practiceSel.placements, "#35d0e0");
      drawGradeMarks(svg);
    }
  }

  geom.nodes.forEach((n) => {
    const c = el("circle", { cx: n.x, cy: n.y, r: 5, fill: "#cdd9e5", stroke: "#0b1118", "stroke-width": 1 });
    c.style.cursor = "pointer";
    c.onclick = () => clickNode(n);
    svg.appendChild(c);
  });

  if (mode === "advisor") { updateStatus(); updateHint(); markActive(); }
  else { updatePracticeHint(); }
}

function drawPorts(svg, b) {
  const typeByPair = {};
  b.ports.forEach((p) => (typeByPair[[...p.nodes].sort((a, x) => a - x).join("-")] = p.type));
  const nodeById = {};
  geom.nodes.forEach((n) => (nodeById[n.id] = n));
  geom.ports.forEach((gp) => {
    const type = typeByPair[[gp.a, gp.b].sort((a, x) => a - x).join("-")] || "?";
    const generic = type === "3:1";
    // 3:1 ports are near-white so they're distinct from the (grey) ore ports.
    const color = generic ? "#eef1f5" : RES_COLOR[type] || "#7c8a98";
    // "docks": lines from the port marker to the two settlement spots it serves
    [gp.a, gp.b].forEach((nid) => {
      const n = nodeById[nid];
      if (n) svg.appendChild(el("line", {
        x1: gp.x, y1: gp.y, x2: n.x, y2: n.y,
        stroke: color, "stroke-width": 3, "stroke-linecap": "round", opacity: 0.85,
      }));
    });
    svg.appendChild(el("circle", { cx: gp.x, cy: gp.y, r: 12, fill: color, stroke: "#0b1118", "stroke-width": 1.5 }));
    const t = el("text", { x: gp.x, y: gp.y + 4, "text-anchor": "middle", "font-size": 10, "font-weight": "bold", fill: "#0b1118" });
    t.textContent = generic ? "3:1" : type[0];
    svg.appendChild(t);
  });
}

// Draw settlements + roads grouped by player colour. settObj/roadObj: {player: [...]}.
function drawPieces(svg, settObj, roadObj) {
  for (const p in roadObj) {
    (roadObj[p] || []).forEach(([a, b]) => {
      const e = findEdge(a, b);
      if (e) svg.appendChild(el("line", { x1: e.x1, y1: e.y1, x2: e.x2, y2: e.y2, stroke: PCOLOR[p] || "#888", "stroke-width": 7, "stroke-linecap": "round", "pointer-events": "none" }));
    });
  }
  for (const p in settObj) {
    (settObj[p] || []).forEach((nid) => {
      const n = geom.nodes.find((x) => x.id === nid);
      if (n) svg.appendChild(el("rect", { x: n.x - 8, y: n.y - 8, width: 16, height: 16, fill: PCOLOR[p] || "#888", stroke: "#0b1118", "stroke-width": 2 }));
    });
  }
}

// Highlight a list of {settlement, road} placements in `color` (recommendation / model line).
function drawHighlight(svg, pls, color) {
  pls.forEach((pl, i) => {
    const e = findEdge(pl.road[0], pl.road[1]);
    if (e) svg.appendChild(el("line", { x1: e.x1, y1: e.y1, x2: e.x2, y2: e.y2, stroke: color, "stroke-width": 8, "stroke-linecap": "round", opacity: 0.85, "pointer-events": "none" }));
    const n = geom.nodes.find((x) => x.id === pl.settlement);
    if (n) {
      svg.appendChild(el("circle", { cx: n.x, cy: n.y, r: 13, fill: color, stroke: "#0b1118", "stroke-width": 2 }));
      const t = el("text", { x: n.x, y: n.y + 5, "text-anchor": "middle", "font-size": 13, "font-weight": "bold", fill: "#222" });
      t.textContent = pls.length > 1 ? i + 1 : "★";
      svg.appendChild(t);
    }
  });
}

// Ring the user's chosen spots green/red according to the grade.
function drawGradeMarks(svg) {
  practiceResult.grades.forEach((g) => {
    const col = g.correct ? "#56d364" : "#f0883e";
    if (g.kind === "settlement" && g.chosen_node != null) {
      const n = geom.nodes.find((x) => x.id === g.chosen_node);
      if (n) svg.appendChild(el("circle", { cx: n.x, cy: n.y, r: 11, fill: "none", stroke: col, "stroke-width": 3 }));
    } else if (g.kind === "road" && g.chosen_edge) {
      const e = findEdge(g.chosen_edge[0], g.chosen_edge[1]);
      if (e) svg.appendChild(el("line", { x1: e.x1, y1: e.y1, x2: e.x2, y2: e.y2, stroke: col, "stroke-width": 3, "stroke-dasharray": "4 3", "pointer-events": "none" }));
    }
  });
}

function findEdge(a, b) {
  return geom.edges.find((x) => (x.a === a && x.b === b) || (x.a === b && x.b === a));
}

// ---- validation / status (advisor) -----------------------------------------
function validateBoard() {
  const issues = [];
  const rc = {};
  RES.forEach((r) => (rc[r] = 0));
  board.hexes.forEach((h) => { if (h.resource) rc[h.resource]++; });
  for (const r in REQ_RES) if (rc[r] !== REQ_RES[r]) issues.push(`${r} ${rc[r]}/${REQ_RES[r]}`);
  const nc = {};
  let missing = 0;
  board.hexes.forEach((h) => {
    if (h.resource && h.resource !== "DESERT") {
      if (h.number == null) missing++;
      else nc[h.number] = (nc[h.number] || 0) + 1;
    }
  });
  if (missing) issues.push(`${missing} hex(es) missing a number`);
  else for (const n in REQ_NUM) if ((nc[n] || 0) !== REQ_NUM[n]) issues.push(`token ${n} ${(nc[n] || 0)}/${REQ_NUM[n]}`);

  // No two edge-adjacent hexes may both be a red number (6/8) — official setup rule.
  const num = {};
  board.hexes.forEach((h) => (num[h.id] = h.number));
  let redPairs = 0;
  (geom.hex_adjacency || []).forEach(([a, b]) => {
    if (RED_NUMS.has(num[a]) && RED_NUMS.has(num[b])) redPairs++;
  });
  if (redPairs) issues.push(`${redPairs} adjacent red 6/8 pair(s)`);
  return issues;
}

function updateStatus() {
  const issues = validateBoard();
  const s = $("status");
  if (issues.length === 0) { s.textContent = "Board valid ✓"; s.className = "status ok"; }
  else { s.textContent = `Board: ${issues.length} issue(s)`; s.className = "status bad"; }
}

function updateHint() {
  const h = $("placeHint");
  const next = SEAT_PLAN[seat][draftPieces.length];
  if (next) {
    h.textContent = `Click a ${next.k === "S" ? "node to place" : "edge for"} ${next.p}'s ${next.k === "S" ? "settlement" : "road"}. (Click a placed piece to remove it.)`;
  } else {
    h.textContent = seat === "FIRST" ? "" : "All draft pieces placed ✓";
  }
}

// ---- analyze (advisor) -----------------------------------------------------
function buildRequest() {
  const hexes = board.hexes.map((h) => ({
    id: h.id, resource: h.resource, number: h.resource === "DESERT" ? null : h.number,
  }));
  const desert = hexes.find((h) => h.resource === "DESERT");
  return {
    board: { hexes, ports: board.ports, robber_hex: desert ? desert.id : board.robber_hex },
    seat,
    user_color: seat === "SECOND" ? "P2" : "P1",
    settlements: draftSettlements(),
    roads: draftRoads(),
  };
}

async function analyze() {
  const issues = validateBoard();
  if (issues.length) { alert("Board not valid:\n  " + issues.join("\n  ")); return; }
  if (draftPieces.length < SEAT_PLAN[seat].length) { alert("Place all existing draft pieces first."); return; }

  const btn = $("analyze");
  const label = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Analyzing…";
  try {
    const body = {
      request: buildRequest(),
      top_k: 6,
      n_rollouts: 0, // win-% display shelved; rank by heuristic only (see docs/heuristic-accuracy.md)
    };
    const resp = await fetch("/api/recommend", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!resp.ok) { alert("Solver error:\n" + (await resp.text()).slice(0, 500)); return; }
    recs = await resp.json();
    selected = recs[0] || null;
    render();
    renderResults();
  } finally {
    btn.disabled = false;
    btn.textContent = label;
  }
}

function renderResults() {
  const div = $("results");
  if (!recs.length) {
    div.innerHTML = '<p class="hint">Build a board and click Analyze.</p>';
    return;
  }
  div.replaceChildren();
  recs.forEach((r, i) => {
    const row = document.createElement("div");
    row.className = "rec" + (r === selected ? " sel" : "");
    const spots = r.placements
      .map((p) => `${spotName(p.settlement)} (${roadDir(p.settlement, p.road)})`)
      .join("  +  ");
    row.innerHTML = `<b>#${i + 1}</b> ${spots}<br><span style="color:#8aa0b3" title="${SCORE_HINT}">${scoreLabel(r)}</span>`;
    row.onclick = () => { selected = r; render(); renderResults(); };
    div.appendChild(row);
  });
}

// Recommendations are ranked by the heuristic score (higher = better). A win-%
// display was trialled but shelved — vs the only available (weak) bot it read ~96%
// where strong humans win ~44%, which would mislead. See docs/heuristic-accuracy.md.
const SCORE_HINT = "Relative strength score (higher = better) — production-weighted, with diversity and ports. A comparative ranking, not a win probability.";
function scoreLabel(r) {
  return `score ${r.heuristic_score.toFixed(2)}`;
}

// --------------------------------------------------------------------------- //
// Practice mode
// --------------------------------------------------------------------------- //
async function newPuzzle() {
  const btn = $("newPuzzle");
  btn.disabled = true;
  try {
    const resp = await fetch("/api/practice/new", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ seat: practiceScenario }),
    });
    if (!resp.ok) { alert("Could not generate puzzle:\n" + (await resp.text()).slice(0, 500)); return; }
    puzzle = await resp.json();
    startUserAttempt();
    const label = practiceScenario === "RANDOM" ? `${SEAT_NAME[puzzle.seat]} 🎲` : SEAT_NAME[puzzle.seat];
    $("scenarioLabel").textContent = label;
    render();
    renderFeedback();
  } finally {
    btn.disabled = false;
  }
}

// Reset the user's in-progress answer for the current puzzle.
function startUserAttempt() {
  userPieces = [];
  practiceResult = null;
  practiceSel = null;
}

const SEAT_NAME = { FIRST: "Going first", SECOND: "Going second", FIRST_FINAL: "First player's final pick" };
function piecesNeeded() { return 2 * USER_PIECES[puzzle.seat]; }   // S,R per placement
function nextKind() { return userPieces.length % 2 === 0 ? "S" : "R"; }
function userSettlements() { return userPieces.filter((p) => p.k === "S").map((p) => p.node); }
function userRoads() { return userPieces.filter((p) => p.k === "R").map((p) => p.edge); }
function sameEdge(a, b) { return (a[0] === b[0] && a[1] === b[1]) || (a[0] === b[1] && a[1] === b[0]); }

function clickNodePractice(n) {
  if (practiceResult) return;
  // click a settlement you already placed to remove it (and anything placed after)
  const idx = userPieces.findIndex((p) => p.k === "S" && p.node === n.id);
  if (idx !== -1) { userPieces.length = idx; render(); return; }
  if (userPieces.length < piecesNeeded() && nextKind() === "S") {
    userPieces.push({ k: "S", node: n.id });
    render();
  }
}

function clickEdgePractice(e) {
  if (practiceResult) return;
  const idx = userPieces.findIndex((p) => p.k === "R" && sameEdge(p.edge, [e.a, e.b]));
  if (idx !== -1) { userPieces.length = idx; render(); return; }
  if (userPieces.length < piecesNeeded() && nextKind() === "R") {
    userPieces.push({ k: "R", edge: [e.a, e.b] });
    render();
  }
}

function updatePracticeHint() {
  if (!puzzle) return;
  const h = $("practiceHint");
  const name = SEAT_NAME[puzzle.seat];
  if (practiceResult) { h.textContent = `${name} — review the answer, then start a new puzzle.`; return; }
  if (userPieces.length < piecesNeeded()) {
    h.textContent = `${name}: click a ${nextKind() === "S" ? "node for your settlement" : "edge for your road"}. (Click a placed piece to remove it.)`;
  } else {
    h.textContent = `${name}: ready — click Submit answer.`;
  }
}

async function submitPlacement() {
  if (!puzzle) return;
  if (userPieces.length < piecesNeeded()) { alert("Place all your settlement(s) and road(s) first."); return; }
  const settlements = userSettlements();
  const roads = userRoads();
  const pls = settlements.map((s, i) => ({ settlement: s, road: roads[i] }));
  const btn = $("submitPlacement");
  btn.disabled = true;
  try {
    const resp = await fetch("/api/practice/grade", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ request: puzzle, placements: pls }),
    });
    if (!resp.ok) { alert("Grading error:\n" + (await resp.text()).slice(0, 500)); return; }
    practiceResult = await resp.json();
    // update + persist score
    score.points += practiceResult.total_awarded;
    score.maxPoints += practiceResult.total_max;
    score.attempts += 1;
    score.streak = practiceResult.all_correct ? score.streak + 1 : 0;
    score.last = practiceResult.total_awarded;
    saveScore();
    updateScoreboard();
    render();
    renderFeedback();
  } finally {
    btn.disabled = false;
  }
}

// Describe a settlement spot by the numbers on its adjacent hexes, e.g. "5-8-11".
function spotName(nodeId) {
  const hids = (geom.node_hexes && geom.node_hexes[nodeId]) || [];
  const byId = {};
  activeBoard().hexes.forEach((h) => (byId[h.id] = h));
  const nums = hids
    .map((id) => byId[id] && byId[id].number)
    .filter((n) => n != null)
    .sort((a, b) => a - b);
  return nums.length ? nums.join("-") : "coast";
}

function nodePos(id) { return geom.nodes.find((n) => n.id === id); }

// Describe a road by its rough direction (L/R/U/D) out of `fromNode`.
function roadDir(fromNode, edge) {
  const far = edge[0] === fromNode ? edge[1] : edge[0];
  const a = nodePos(fromNode), b = nodePos(far);
  if (!a || !b) return "?";
  const dx = b.x - a.x, dy = b.y - a.y;
  if (Math.abs(dx) >= Math.abs(dy)) return dx >= 0 ? "R" : "L";
  return dy >= 0 ? "D" : "U"; // SVG y grows downward
}
const DIR_WORD = { L: "left", R: "right", U: "up", D: "down", "?": "?" };

function renderFeedback() {
  const div = $("feedback");
  if (!practiceResult) {
    div.innerHTML = '<p class="hint">Place your pieces and click <b>Submit answer</b>.</p>';
    return;
  }
  const r = practiceResult;
  div.replaceChildren();

  const verdict = document.createElement("div");
  let word, cls;
  if (r.is_optimal) { word = "Perfect — optimal!"; cls = "ok"; }
  else if (r.all_correct) { word = "Good — not optimal"; cls = "ok"; }
  else { word = "Off the mark"; cls = "bad"; }
  verdict.className = "verdict " + cls;
  verdict.textContent = `${word} · ${r.total_awarded.toFixed(1)} / ${r.total_max.toFixed(0)} pts`;
  div.appendChild(verdict);

  const sg = (i) => r.grades.find((g) => g.kind === "settlement" && g.placement_index === i);
  const rg = (i) => r.grades.find((g) => g.kind === "road" && g.placement_index === i);
  const n = USER_PIECES[r.seat];
  for (let i = 0; i < n; i++) {
    const s = sg(i), road = rg(i);
    const head = n > 1 ? `Placement ${i + 1}` : "Your placement";
    const block = document.createElement("div");
    block.className = "grade";
    block.innerHTML =
      `<b>${head}</b>` +
      gradeLine("Settlement", spotName(s.chosen_node), s.is_optimal ? null : spotName(s.optimal_node), s) +
      // the best road is judged relative to the settlement the user actually built
      gradeLine("Road", dirLabel(s.chosen_node, road.chosen_edge),
        road.is_optimal ? null : dirLabel(s.chosen_node, road.optimal_edge), road);
    div.appendChild(block);
  }

  const h = document.createElement("h3");
  h.style.cssText = "color:#8aa0b3; font-size:12px; text-transform:uppercase; letter-spacing:.05em; margin:12px 0 4px";
  h.textContent = "Solver's top picks";
  div.appendChild(h);
  r.ranking.forEach((rec, i) => {
    const row = document.createElement("div");
    row.className = "rec" + (rec === practiceSel ? " sel" : "");
    const spots = rec.placements
      .map((p) => `${spotName(p.settlement)} (${roadDir(p.settlement, p.road)})`)
      .join("  +  ");
    row.innerHTML = `<b>#${i + 1}</b> ${spots}<br><span style="color:#8aa0b3" title="${SCORE_HINT}">${scoreLabel(rec)}</span>`;
    row.onclick = () => { practiceSel = rec; render(); renderFeedback(); };
    div.appendChild(row);
  });
  const legend = document.createElement("p");
  legend.className = "hint";
  legend.innerHTML = "Gold ★ = model answer · cyan = a pick you clicked · ring = your spot (green ok / orange off)."
    + "<br>Spots read as <b>numbers-of-adjacent-hexes (road direction)</b>, e.g. 5-6-9 (L).";
  div.appendChild(legend);
}

function dirLabel(fromNode, edge) {
  const d = roadDir(fromNode, edge);
  return `${d} (${DIR_WORD[d]})`;
}

// One settlement/road line: marker, description, points, and the best if you missed it.
function gradeLine(label, desc, best, g) {
  const mark = g.is_optimal
    ? '<span class="mark ok">★</span>'
    : g.correct ? '<span class="mark ok">✓</span>' : '<span class="mark bad">✗</span>';
  const bestTxt = best ? ` · best <b>${best}</b> (ranked ${g.rank}/${g.n_options})` : "";
  return `<br>${mark} ${label}: <b>${desc}</b> &nbsp;+${g.points.toFixed(1)}` +
    `<br><span class="sub">${Math.round(g.quality * 100)}% of optimal${bestTxt}</span>`;
}

// ---- score persistence -----------------------------------------------------
function loadScore() {
  try {
    const s = JSON.parse(localStorage.getItem(SCORE_KEY));
    return s && typeof s.points === "number" ? { ...BASE_SCORE, ...s } : { ...BASE_SCORE };
  } catch (_) {
    return { ...BASE_SCORE };
  }
}

function saveScore() {
  try { localStorage.setItem(SCORE_KEY, JSON.stringify(score)); } catch (_) { /* ignore */ }
}

function updateScoreboard() {
  $("statPoints").textContent = Math.round(score.points);
  $("statStreak").textContent = score.streak;
  // average points per puzzle, out of 10
  $("statAcc").textContent = score.attempts ? (score.points / score.attempts).toFixed(1) : "—";
  const last = $("lastPoints");
  if (last) {
    last.textContent = score.last == null
      ? "No answers yet."
      : `Last answer: ${score.last.toFixed(1)} / 10  ·  ${score.attempts} attempt${score.attempts === 1 ? "" : "s"}`;
  }
}

window.addEventListener("DOMContentLoaded", init);
