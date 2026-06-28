"use strict";

const SVGNS = "http://www.w3.org/2000/svg";
const RES = ["WOOD", "BRICK", "SHEEP", "WHEAT", "ORE", "DESERT"];
const RES_COLOR = {
  WOOD: "#3f7d34", BRICK: "#c1612f", SHEEP: "#a9d06b",
  WHEAT: "#e6b422", ORE: "#7e8a98", DESERT: "#e3d3a8",
};
const NUMS = [2, 3, 4, 5, 6, 8, 9, 10, 11, 12];
// Port types: "3:1" is the generic any-resource port; the rest are 2:1 resource ports.
const PORT_TYPES = ["3:1", "WOOD", "BRICK", "SHEEP", "WHEAT", "ORE"];
const REQ_RES = { WOOD: 4, BRICK: 3, SHEEP: 4, WHEAT: 4, ORE: 3, DESERT: 1 };
const REQ_NUM = { 2: 1, 3: 2, 4: 2, 5: 2, 6: 2, 8: 2, 9: 2, 10: 2, 11: 2, 12: 1 };
const REQ_PORT = { "3:1": 4, WOOD: 1, BRICK: 1, SHEEP: 1, WHEAT: 1, ORE: 1 };
const RED_NUMS = new Set([6, 8]);
// dots under each token = number of ways to roll it (as on the real tokens)
const PIPS = { 2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 8: 5, 9: 4, 10: 3, 11: 2, 12: 1 };
// The four real Catan player colours; 1v1 defaults P1 = blue, P2 = white.
const CATAN_COLORS = { red: "#cf3a36", orange: "#e2711d", blue: "#2f6fc4", white: "#f1efe6" };
const PCOLOR = { P1: CATAN_COLORS.blue, P2: CATAN_COLORS.white };
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
// port editor (advisor): node-pair key of the open port + its pending type selection
let editingPort = null;
let portEditType = null;
let draftPieces = []; // advisor: ordered existing draft pieces [{p, k:"S"|"R", node|edge}]
let recs = [];
let selected = null;

// practice state
let puzzle = null;                          // OpeningPlacementRequest from the server
let practiceScenario = null;                // seat chosen in the scenario modal (null = none yet)
let practiceBoardMode = "random";           // "random" | "fixed" | "configure"
let practiceFixedBoard = null;              // board reused for "fixed"/"configure" modes
let buildingForPractice = false;            // user is building a board (on the advisor editor)
let savedAdvisorBoard = null;               // advisor board stashed during a build, restored after
let userPieces = [];                        // ordered [{k:"S",node} | {k:"R",edge}], S,R,S,R…
let practiceResult = null;
let practiceSel = null;                     // a ranking row the user clicked to inspect
let practiceReveal = null;                  // a ranking row whose full optimal line is revealed
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
  buildPortEditor();
  $("randomize").onclick = randomize;
  $("clear").onclick = clearBoard;
  $("seat").onchange = (e) => { seat = e.target.value; resetDraft(); render(); };
  $("analyze").onclick = analyze;
  $("undoAnalyze").onclick = clearAnalysis;
  // tabs
  $("tabAdvisor").onclick = () => setMode("advisor");
  $("tabPractice").onclick = () => setMode("practice");
  // hex editor modal
  $("hexApply").onclick = applyHexEdit;
  $("hexClearOne").onclick = clearHexEdit;
  $("hexCancel").onclick = closeHexModal;
  $("hexModal").onclick = (e) => { if (e.target.id === "hexModal") closeHexModal(); };
  // port editor modal
  $("portApply").onclick = applyPortEdit;
  $("portClearOne").onclick = clearPortEdit;
  $("portCancel").onclick = closePortModal;
  $("portModal").onclick = (e) => { if (e.target.id === "portModal") closePortModal(); };
  // analyze info modal
  $("analyzeInfo").onclick = () => $("infoModal").classList.remove("hidden");
  $("infoClose").onclick = () => $("infoModal").classList.add("hidden");
  $("infoModal").onclick = (e) => { if (e.target.id === "infoModal") $("infoModal").classList.add("hidden"); };
  // practice controls
  $("newPuzzle").onclick = newPuzzle;
  $("submitPlacement").onclick = submitPlacement;
  $("clearPlacement").onclick = () => { startUserAttempt(); render(); renderFeedback(); };
  $("changeScenario").onclick = showScenarioModal;
  $("resetScore").onclick = resetScore;
  document.querySelectorAll("#scenarioModal [data-seat]").forEach((b) => {
    b.onclick = () => selectSeat(b.dataset.seat);
  });
  document.querySelectorAll("#scenarioModal [data-boardmode]").forEach((b) => {
    b.onclick = () => selectBoardMode(b.dataset.boardmode);
  });
  $("startPractice").onclick = startPractice;
  updateBoardModeButtons();
  $("useInPractice").onclick = finishBoardBuild;
  $("cancelBuild").onclick = cancelBoardBuild;
  $("scenarioModal").onclick = (e) => { if (e.target.id === "scenarioModal" && puzzle) hideScenarioModal(); };
  updateScoreboard();
  await loadClearBoard();
}

// Load a real board (for valid ports/structure) but start it visually empty.
async function loadClearBoard() {
  board = await (await fetch("/api/board/random")).json();
  board.hexes.forEach((h) => { h.resource = null; h.number = null; });
  board.ports.forEach((p) => { p.type = null; });
  resetDraft();
  render();
}

// ---- scenario modal --------------------------------------------------------
function showScenarioModal() {
  updateBoardModeButtons();
  updateSeatButtons();
  updateBoardOptions();
  updateStartButton();
  $("scenarioModal").classList.remove("hidden");
}
function hideScenarioModal() { $("scenarioModal").classList.add("hidden"); }

function selectSeat(s) {
  practiceScenario = s;
  updateSeatButtons();
  updateBoardOptions();
  updateStartButton();
}

// "Fixed board" is pointless for "Going first" — with no opponent priors it's the same
// puzzle every time — so disable it for that seat, falling back to random if it was chosen.
function updateBoardOptions() {
  const fixedBtn = document.querySelector('#scenarioModal [data-boardmode="fixed"]');
  const disableFixed = practiceScenario === "FIRST";
  if (fixedBtn) fixedBtn.disabled = disableFixed;
  if (disableFixed && practiceBoardMode === "fixed") {
    practiceBoardMode = "random";
    updateBoardModeButtons();
  }
}

function updateSeatButtons() {
  document.querySelectorAll("#scenarioModal [data-seat]").forEach((b) =>
    b.classList.toggle("active", b.dataset.seat === practiceScenario)
  );
}

// Start is enabled once a board mode and a scenario are both chosen.
function updateStartButton() {
  $("startPractice").disabled = !(practiceBoardMode && practiceScenario);
}

// Begin practice with the chosen board mode + seat. "configure" (with no board built yet)
// launches the board builder first; the puzzle then starts when the user finishes building.
function startPractice() {
  if (!practiceScenario) return;
  // reconfiguring an existing session (via Change) starts a fresh scoreboard
  if (puzzle) resetScore();
  if (practiceBoardMode === "configure" && !practiceFixedBoard) { startBoardBuild(); return; }
  hideScenarioModal();
  newPuzzle();
}

function updateBoardModeButtons() {
  document.querySelectorAll("#scenarioModal [data-boardmode]").forEach((b) =>
    b.classList.toggle("active", b.dataset.boardmode === practiceBoardMode)
  );
}

// Board choice in the practice menu: random (fresh each puzzle), fixed (one random board
// reused), or configure (build your own). "configure" launches the board builder.
function selectBoardMode(m) {
  practiceBoardMode = m;
  // any explicit board choice starts fresh: "random" never reuses a board; "fixed"/"configure"
  // (re)acquire one on Start / when the build finishes.
  practiceFixedBoard = null;
  updateBoardModeButtons();
  updateStartButton();
}

// Build-your-own-board: reuse the advisor tab's full editor. Stash the advisor board, drop
// in a random board to tweak, and show a banner with "Use in practice".
async function startBoardBuild() {
  practiceBoardMode = "configure";
  buildingForPractice = true;
  hideScenarioModal();
  savedAdvisorBoard = board;
  board = await (await fetch("/api/board/random")).json();  // a valid base to edit
  resetDraft();
  setMode("advisor");
}

async function finishBoardBuild() {
  const issues = validateBoard();
  if (issues.length) { alert("Board not valid:\n  " + issues.join("\n  ")); return; }
  practiceFixedBoard = JSON.parse(JSON.stringify(board));  // lock the built board
  buildingForPractice = false;
  if (savedAdvisorBoard) { board = savedAdvisorBoard; savedAdvisorBoard = null; resetDraft(); }
  await setMode("practice", true);  // back to practice without re-opening the menu
  await newPuzzle();                // first puzzle on the built board
}

function cancelBoardBuild() {
  buildingForPractice = false;
  if (savedAdvisorBoard) { board = savedAdvisorBoard; savedAdvisorBoard = null; resetDraft(); }
  setMode("practice", true);
  showScenarioModal();
}

// --------------------------------------------------------------------------- //
// Mode switching
// --------------------------------------------------------------------------- //
async function setMode(m, skipMenu) {
  // leaving a board-build (e.g. via the tab) abandons it and restores the advisor board
  if (buildingForPractice && m !== "advisor") {
    buildingForPractice = false;
    if (savedAdvisorBoard) { board = savedAdvisorBoard; savedAdvisorBoard = null; resetDraft(); }
  }
  mode = m;
  $("tabAdvisor").classList.toggle("active", m === "advisor");
  $("tabPractice").classList.toggle("active", m === "practice");
  $("advisorControls").classList.toggle("hidden", m !== "advisor");
  $("advisorResults").classList.toggle("hidden", m !== "advisor");
  $("practiceControls").classList.toggle("hidden", m !== "practice");
  $("practiceResults").classList.toggle("hidden", m !== "practice");
  $("practiceBuildBar").classList.toggle("hidden", !(m === "advisor" && buildingForPractice));
  if (m === "practice" && !skipMenu) { showScenarioModal(); return; }
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

// ---- port editor (click a port to set its type) ----------------------------
// Ports sit at fixed board edges (their node pair never changes); only the trade
// type is editable. Keyed by the sorted node pair so geometry and board agree.
function portKey(nodes) { return [...nodes].sort((a, b) => a - b).join("-"); }

function buildPortEditor() {
  PORT_TYPES.forEach((t) => {
    const generic = t === "3:1";
    const b = document.createElement("button");
    b.textContent = generic ? "3:1" : t[0] + t.slice(1).toLowerCase();
    b.style.background = generic ? "#eef1f5" : RES_COLOR[t];
    b.style.color = "#0b1118";
    b.dataset.port = t;
    b.onclick = () => { portEditType = t; updatePortHighlights(); };
    $("portTypeChoices").appendChild(b);
  });
}

function updatePortHighlights() {
  document.querySelectorAll("#portTypeChoices [data-port]").forEach((b) =>
    b.classList.toggle("active", b.dataset.port === portEditType)
  );
}

function openPortEditor(gp) {
  if (mode !== "advisor") return;
  const key = portKey([gp.a, gp.b]);
  const port = board.ports.find((p) => portKey(p.nodes) === key);
  if (!port) return;
  editingPort = key;
  portEditType = port.type || null;
  updatePortHighlights();
  $("portModal").classList.remove("hidden");
}

function closePortModal() { editingPort = null; $("portModal").classList.add("hidden"); }

function applyPortEdit() {
  const port = board.ports.find((p) => portKey(p.nodes) === editingPort);
  if (port && portEditType) port.type = portEditType;
  closePortModal();
  render();
}

function clearPortEdit() {
  const port = board.ports.find((p) => portKey(p.nodes) === editingPort);
  if (port) port.type = null;
  closePortModal();
  render();
}

async function randomize() {
  board = await (await fetch("/api/board/random")).json();
  resetDraft();
  render();
}

function clearBoard() {
  board.hexes.forEach((h) => { h.resource = null; h.number = null; });
  board.ports.forEach((p) => { p.type = null; });
  resetDraft();
  render();
}

function resetDraft() {
  draftPieces = [];
  recs = [];
  selected = null;
  renderResults();
}

// Remove just the Analyze result (the recommendations + on-board highlight), keeping the
// board and draft pieces so the user can tweak and re-analyze without starting over.
function clearAnalysis() {
  recs = [];
  selected = null;
  render();
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
// A small, auto-dismissing hint that pops up next to the mouse cursor.
function cursorHint(text, ev) {
  let h = $("cursorHint");
  if (!h) {
    h = document.createElement("div");
    h.id = "cursorHint";
    h.style.cssText =
      "position:fixed; z-index:1000; max-width:230px; padding:7px 10px; pointer-events:none;"
      + "background:#1b2430; color:#e6edf3; border:1px solid #38465a; border-radius:6px;"
      + "font-size:12px; line-height:1.4; box-shadow:0 2px 10px rgba(0,0,0,.45); opacity:0;"
      + "transition:opacity .2s;";
    document.body.appendChild(h);
  }
  h.textContent = text;
  h.style.left = (ev.clientX + 14) + "px";
  h.style.top = (ev.clientY + 16) + "px";
  requestAnimationFrame(() => { h.style.opacity = "1"; });
  clearTimeout(cursorHint._t);
  cursorHint._t = setTimeout(() => { h.style.opacity = "0"; }, 2600);
}

function clickNode(n, ev) {
  if (mode === "practice") return clickNodePractice(n);
  // click a settlement already placed to remove it (and anything placed after)
  const idx = draftPieces.findIndex((x) => x.k === "S" && x.node === n.id);
  if (idx !== -1) { draftPieces.length = idx; render(); return; }
  const next = SEAT_PLAN[seat][draftPieces.length];
  if (next && next.k === "S") { draftPieces.push({ p: next.p, k: "S", node: n.id }); render(); return; }
  // "Going first" has no preexisting placements, so a click to place a piece is a mistake —
  // nudge the user to switch seats if they meant to set up a board with pieces already down.
  if (seat === "FIRST" && ev) {
    cursorHint(
      "Going first starts from an empty board — just click Analyze. To set up existing "
      + "placements, change \"Your seat\" to Going second or First (final pick).",
      ev,
    );
  }
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

  // Interactive node dots — drawn *before* the pieces so a placed house covers its dot
  // yet stays clickable to remove (pieces are pointer-events:none, so clicks fall through).
  geom.nodes.forEach((n) => {
    const c = el("circle", { cx: n.x, cy: n.y, r: 5, fill: "#cdd9e5", stroke: "#0b1118", "stroke-width": 1 });
    c.style.cursor = "pointer";
    c.onclick = (ev) => clickNode(n, ev);
    svg.appendChild(c);
  });

  drawPorts(svg, b);

  if (mode === "advisor") {
    drawPieces(svg, draftSettlements(), draftRoads());
    if (selected) drawHighlight(svg, selected.placements, PCOLOR[userColor()]);
  } else if (puzzle) {
    drawPieces(svg, puzzle.settlements || {}, puzzle.roads || {});       // the given priors
    drawPieces(svg, { P1: userSettlements() }, { P1: userRoads() });      // the user's answer
    if (practiceResult) {
      if (practiceReveal && practiceReveal.continuation) {
        drawContinuation(svg, practiceReveal.continuation, puzzle.seat);
      } else {
        drawHighlight(svg, practiceResult.optimal_placements, PCOLOR[userColor()]);
        if (practiceSel) drawHighlight(svg, practiceSel.placements, "#35d0e0");
      }
      drawGradeMarks(svg);
    }
  }

  if (mode === "advisor") { updateStatus(); updateHint(); markActive(); }
  else { updatePracticeHint(); }
}

function drawPorts(svg, b) {
  const typeByPair = {};
  b.ports.forEach((p) => (typeByPair[portKey(p.nodes)] = p.type));
  const nodeById = {};
  geom.nodes.forEach((n) => (nodeById[n.id] = n));
  geom.ports.forEach((gp) => {
    const type = typeByPair[portKey([gp.a, gp.b])] || null;
    const empty = !type;
    const generic = type === "3:1";
    // empty ports show as a dim slot (consistent with the empty hexes); 3:1 ports are
    // near-white so they're distinct from the (grey) ore ports.
    const color = empty ? "#2c3c4d" : generic ? "#eef1f5" : RES_COLOR[type] || "#7c8a98";
    // "docks": lines from the port marker to the two settlement spots it serves
    [gp.a, gp.b].forEach((nid) => {
      const n = nodeById[nid];
      if (n) svg.appendChild(el("line", {
        x1: gp.x, y1: gp.y, x2: n.x, y2: n.y,
        stroke: empty ? "#3a4b5c" : color, "stroke-width": 3, "stroke-linecap": "round",
        opacity: empty ? 0.5 : 0.85, "pointer-events": "none",
      }));
    });
    const marker = el("circle", { cx: gp.x, cy: gp.y, r: 12, fill: color, stroke: "#0b1118", "stroke-width": 1.5 });
    if (mode === "advisor") {
      marker.style.cursor = "pointer";
      marker.onclick = () => openPortEditor(gp);
    }
    svg.appendChild(marker);
    if (!empty) {
      const t = el("text", {
        x: gp.x, y: gp.y + 4, "text-anchor": "middle", "font-size": 10, "font-weight": "bold",
        fill: "#0b1118", "pointer-events": "none",
      });
      t.textContent = generic ? "3:1" : type[0];
      svg.appendChild(t);
    }
  });
}

// A classic Catan settlement: a little house (square body + triangular roof), centred
// on (cx, cy), with a dark outline + eave line so it reads as a building (and white
// pieces stay visible).
function drawSettlement(svg, cx, cy, color) {
  const w = 9, body = 8, eaveDy = -3, peakDy = -12;
  const pts = [
    [cx, cy + peakDy], [cx + w, cy + eaveDy], [cx + w, cy + body],
    [cx - w, cy + body], [cx - w, cy + eaveDy],
  ].map((q) => q.join(",")).join(" ");
  svg.appendChild(el("polygon", {
    points: pts, fill: color, stroke: "#0b1118", "stroke-width": 1.6,
    "stroke-linejoin": "round", "pointer-events": "none",
  }));
  svg.appendChild(el("line", {
    x1: cx - w, y1: cy + eaveDy, x2: cx + w, y2: cy + eaveDy,
    stroke: "#0b1118", "stroke-width": 1, opacity: 0.45, "pointer-events": "none",
  }));
}

// A Catan road: a dark casing under the player colour, so it stands out (esp. white).
function drawRoad(svg, e, color) {
  svg.appendChild(el("line", { x1: e.x1, y1: e.y1, x2: e.x2, y2: e.y2, stroke: "#0b1118", "stroke-width": 10, "stroke-linecap": "round", "pointer-events": "none" }));
  svg.appendChild(el("line", { x1: e.x1, y1: e.y1, x2: e.x2, y2: e.y2, stroke: color, "stroke-width": 6, "stroke-linecap": "round", "pointer-events": "none" }));
}

// Draw settlements + roads grouped by player colour. settObj/roadObj: {player: [...]}.
function drawPieces(svg, settObj, roadObj) {
  for (const p in roadObj) {
    (roadObj[p] || []).forEach(([a, b]) => {
      const e = findEdge(a, b);
      if (e) drawRoad(svg, e, PCOLOR[p] || "#888");
    });
  }
  for (const p in settObj) {
    (settObj[p] || []).forEach((nid) => {
      const n = geom.nodes.find((x) => x.id === nid);
      if (n) drawSettlement(svg, n.x, n.y, PCOLOR[p] || "#888");
    });
  }
}

// Which player the on-board solution belongs to (so it shows in that player's colour):
// the user goes second (P2) only for the SECOND seat, otherwise first (P1).
function userColor() {
  if (mode === "practice") return (puzzle && puzzle.user_color) || "P1";
  return seat === "SECOND" ? "P2" : "P1";
}

// Pick a legible ink (dark on light fills, light on dark fills) for text on a marker.
function contrastInk(hex) {
  const c = hex.replace("#", "");
  const r = parseInt(c.slice(0, 2), 16), g = parseInt(c.slice(2, 4), 16), b = parseInt(c.slice(4, 6), 16);
  return (0.299 * r + 0.587 * g + 0.114 * b) / 255 > 0.55 ? "#0b1118" : "#f5f5f0";
}

// One highlight marker: the road, a filled node circle, and a `label` glyph (★ or a number).
function drawMarker(svg, pl, color, label) {
  const e = findEdge(pl.road[0], pl.road[1]);
  if (e) svg.appendChild(el("line", { x1: e.x1, y1: e.y1, x2: e.x2, y2: e.y2, stroke: color, "stroke-width": 8, "stroke-linecap": "round", opacity: 0.85, "pointer-events": "none" }));
  const n = geom.nodes.find((x) => x.id === pl.settlement);
  if (!n) return;
  svg.appendChild(el("circle", { cx: n.x, cy: n.y, r: 13, fill: color, stroke: "#0b1118", "stroke-width": 2, "pointer-events": "none" }));
  if (!label) return;
  const t = el("text", { x: n.x, y: n.y + 5, "text-anchor": "middle", "font-size": 13, "font-weight": "bold", fill: contrastInk(color), "pointer-events": "none" });
  t.textContent = label;
  svg.appendChild(t);
}

// Highlight a list of {settlement, road} placements in `color` (recommendation / model line).
// Always the model-answer star, never a per-spot label: for the second player both settlements
// go down together, so any A/B or 1-2 marker reads as a misleading ranking.
function drawHighlight(svg, pls, color) {
  pls.forEach((pl) => drawMarker(svg, pl, color, "★"));
}

// Reveal the full optimal draft behind a pick: the opponent's optimal replies (in their
// colour, unlabelled) and the user's own optimal settlements (in the user's colour). For the
// FIRST seat the user has two settlements whose ORDER matters (turn 1 vs the final pick — the
// second one placed sets the starting hand), so number them 1/2; otherwise star them.
function drawContinuation(svg, line, seat) {
  const uCol = PCOLOR[userColor()];
  const oCol = PCOLOR[userColor() === "P1" ? "P2" : "P1"];
  line.opponent.forEach((pl) => drawMarker(svg, pl, oCol, ""));
  const numbered = seat === "FIRST" && line.user.length > 1;
  line.user.forEach((pl, i) => drawMarker(svg, pl, uCol, numbered ? String(i + 1) : "★"));
}

// Ring the user's chosen spots green/red according to the grade.
function drawGradeMarks(svg) {
  practiceResult.grades.forEach((g) => {
    const col = g.correct ? "#56d364" : "#f0883e";
    if (g.kind === "settlement" && g.chosen_node != null) {
      const n = geom.nodes.find((x) => x.id === g.chosen_node);
      if (n) {
        svg.appendChild(el("circle", { cx: n.x, cy: n.y, r: 11, fill: "none", stroke: col, "stroke-width": 3, "pointer-events": "none" }));
        // tick (correct) / cross (off) in the ring's colour, with a thin dark outline so it
        // reads against light hexes. Normally directly below the ring, but if a road slot
        // runs straight down from the spot, shift it 120° from north (down-right) to clear it
        // (the open gap between the down road and the up-right road).
        const r = 19, ang = (2 * Math.PI) / 3;  // 120° from vertical north, clockwise
        const downRoad = geom.edges.some((e) => {
          if (e.a !== n.id && e.b !== n.id) return false;
          const swap = Math.hypot(e.x1 - n.x, e.y1 - n.y) > Math.hypot(e.x2 - n.x, e.y2 - n.y);
          const dx = (swap ? e.x1 : e.x2) - n.x, dy = (swap ? e.y1 : e.y2) - n.y;
          return dy > 0 && Math.abs(dx) < Math.abs(dy) * 0.3;  // ~vertical, pointing down
        });
        const mx = downRoad ? n.x + r * Math.sin(ang) : n.x;
        const my = downRoad ? n.y - r * Math.cos(ang) : n.y + r;
        const mark = el("text", {
          x: mx, y: my, "text-anchor": "middle", "dominant-baseline": "central",
          "font-size": 12, "font-weight": "bold", fill: col,
          stroke: "#0b1118", "stroke-width": 2, "paint-order": "stroke",
          "stroke-linejoin": "round", "pointer-events": "none",
        });
        mark.textContent = g.correct ? "✓" : "✗";
        svg.appendChild(mark);
      }
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

  // Ports: each must be set, then composition (4 generic 3:1 + one 2:1 per resource).
  const emptyPorts = (board.ports || []).filter((p) => !p.type).length;
  if (emptyPorts) {
    issues.push(`${emptyPorts} port(s) not set`);
  } else {
    const pc = {};
    board.ports.forEach((p) => (pc[p.type] = (pc[p.type] || 0) + 1));
    for (const t in REQ_PORT) if ((pc[t] || 0) !== REQ_PORT[t]) {
      issues.push(`port ${t} ${(pc[t] || 0)}/${REQ_PORT[t]}`);
    }
  }
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
      n_rollouts: 0, // heuristic pre-ranking; win-% comes from the value model (win_prob: true by default)
    };
    const resp = await fetch("/api/recommend", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!resp.ok) { alert("Solver error:\n" + (await resp.text()).slice(0, 500)); return; }
    recs = rankedForDisplay(await resp.json()); // headline by calibrated win-%
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
  const undo = $("undoAnalyze");
  if (undo) undo.disabled = !recs.length;  // only undoable once there's a result
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
    row.innerHTML = `<b>#${i + 1}</b> ${spots}<br><span style="color:#8aa0b3">${scoreLabel(r)}</span>`;
    row.onclick = () => { selected = r; render(); renderResults(); };
    div.appendChild(row);
  });
  if (recs.some((r) => r.placements.length > 1)) {
    const note = document.createElement("p");
    note.className = "hint";
    note.innerHTML = SECOND_ORDER_NOTE;
    div.appendChild(note);
  }
}

// Each recommendation carries two numbers: the calibrated **opening win-%** from the
// learned value model — P(you win) vs an equal-strength bot, the honest figure Phase 5.2
// unlocked — and the heuristic **strength score** that pre-ranks the candidates. The win-%
// is the headline and we sort by it when present (the value model is the better evaluator,
// so it can order picks differently from the score); we fall back to score order when the
// model is unavailable. The earlier shelved win-% was a rollout-vs-weak-bot figure (~96%
// where strong humans win ~44%); this one is calibrated against equal-strength self-play.
const SCORE_HINT = "Strength score (higher = better) — production-weighted, with diversity and ports. Pre-ranks the candidates; the win-% maps this to a calibrated probability.";
const WINPCT_HINT = "Opening win probability — P(you win) vs an equal-strength bot, where both players complete the rest of the draft with their best opening. It maps how much your opening out-produces your opponent's onto a win-%. A balanced opening is ~50/50; the strongest openings reach ~60%, and going first edges going second (best play ≈51% vs ≈45%), in line with the ~56/44 first-mover advantage in elite 1v1 play.";
const WINPCT_LABEL = "vs an equal-strength bot";

// Going second, the two settlements (A & B) are placed back-to-back with no dice between
// them, so the order shown is not a ranking. The one real effect of order — which spot gives
// your opening hand (a card per adjacent hex of the settlement placed second) — the solver
// doesn't weigh yet (planned for Phase 6, when the full-game bot can evaluate the hand).
const SECOND_ORDER_NOTE =
  "Going second, both settlements are placed together, so the order shown isn't a ranking. Order "
  + "only sets your opening hand (one card per adjacent hex of whichever is placed second), which "
  + "the solver doesn't optimise yet.";

function winPct(r) {
  return r && r.opening_win_prob != null ? Math.round(r.opening_win_prob * 100) : null;
}

// Sort a recommendation list for display: by calibrated win-% when any is present,
// else by the heuristic score. Returns a new array (references preserved for `sel`).
function rankedForDisplay(list) {
  const haveWin = list.some((r) => r.opening_win_prob != null);
  return [...list].sort((a, b) =>
    haveWin ? (winPct(b) ?? -1) - (winPct(a) ?? -1) : b.heuristic_score - a.heuristic_score
  );
}

function scoreLabel(r) {
  const wp = winPct(r);
  if (wp == null) return `<span title="${SCORE_HINT}">score ${r.heuristic_score.toFixed(2)}</span>`;
  return `<span title="${WINPCT_HINT}"><b style="color:#cfe3d2">≈${wp}%</b> <span style="color:#6f8597">${WINPCT_LABEL}</span></span>`
    + ` <span style="color:#6f8597" title="${SCORE_HINT}">· score ${r.heuristic_score.toFixed(2)}</span>`;
}

// --------------------------------------------------------------------------- //
// Practice mode
// --------------------------------------------------------------------------- //
async function newPuzzle() {
  const btn = $("newPuzzle");
  btn.disabled = true;
  try {
    const body = { seat: practiceScenario };
    // "fixed"/"configure" reuse one board; "random" gets a fresh board each puzzle
    if (practiceBoardMode !== "random" && practiceFixedBoard) body.board = practiceFixedBoard;
    const resp = await fetch("/api/practice/new", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      cache: "no-store",
      body: JSON.stringify(body),
    });
    if (!resp.ok) { alert("Could not generate puzzle:\n" + (await resp.text()).slice(0, 500)); return; }
    puzzle = await resp.json();
    if (practiceBoardMode === "fixed") practiceFixedBoard = puzzle.board;  // lock the first random board
    startUserAttempt();
    const seatLabel = practiceScenario === "RANDOM" ? `${SEAT_NAME[puzzle.seat]} 🎲` : SEAT_NAME[puzzle.seat];
    const tag = practiceBoardMode === "configure" ? " · ✏️ your board"
      : practiceBoardMode === "fixed" ? " · 📌 fixed board" : "";
    $("scenarioLabel").textContent = seatLabel + tag;
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
  practiceReveal = null;
  const sb = $("submitPlacement");
  if (sb) sb.disabled = false;  // a fresh attempt can be submitted again
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
    // an initial road must connect to the settlement just placed for this pair
    const lastSettlement = [...userPieces].reverse().find((p) => p.k === "S");
    if (!lastSettlement || (e.a !== lastSettlement.node && e.b !== lastSettlement.node)) return;
    userPieces.push({ k: "R", edge: [e.a, e.b] });
    render();
  }
}

function updatePracticeHint() {
  if (!puzzle) return;
  const h = $("practiceHint");
  const name = SEAT_NAME[puzzle.seat];
  const clr = $("clearPlacement");
  if (clr) clr.disabled = !!practiceResult;  // nothing to clear once the answer is graded
  if (practiceResult) { h.textContent = `${name} — review the answer, then start a new puzzle.`; return; }
  if (userPieces.length < piecesNeeded()) {
    h.textContent = `${name}: click a ${nextKind() === "S" ? "node for your settlement" : "edge for your road"}. (Click a placed piece to remove it.)`;
  } else {
    h.textContent = `${name}: ready — click Submit answer.`;
  }
}

async function submitPlacement() {
  if (!puzzle || practiceResult) return;  // nothing to do, or already graded this puzzle
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
    if (!resp.ok) { alert("Grading error:\n" + (await resp.text()).slice(0, 500)); btn.disabled = false; return; }
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
    // leave Submit disabled until "New puzzle" (re-enabled by startUserAttempt) so the
    // same answer can't be graded twice
  } catch (err) {
    btn.disabled = false;
    throw err;
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

// The user's submitted placement(s), reconstructed from the grades.
function userChoicePlacements(r) {
  const out = [];
  for (let i = 0; i < USER_PIECES[r.seat]; i++) {
    const s = r.grades.find((g) => g.kind === "settlement" && g.placement_index === i);
    const rd = r.grades.find((g) => g.kind === "road" && g.placement_index === i);
    if (s && rd && s.chosen_node != null && rd.chosen_edge) {
      out.push({ settlement: s.chosen_node, road: rd.chosen_edge });
    }
  }
  return out;
}

// Does a ranking pick match the user's choice? Matched on the *settlement* spot(s) only
// (order-independent for the pair), so it still flags as "your choice" if only the road
// differed. The road quality is shown separately by the per-placement grade.
function recMatchesChoice(rec, chosen) {
  if (chosen.length === 0 || rec.placements.length !== chosen.length) return false;
  const used = chosen.map(() => false);
  return rec.placements.every((rp) => {
    const i = chosen.findIndex((cp, k) => !used[k] && cp.settlement === rp.settlement);
    if (i === -1) return false;
    used[i] = true;
    return true;
  });
}

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

  // Calibrated learned-value win-% for the user's opening vs the model's line (Phase 5.2c).
  if (r.user_win_prob != null) {
    const u = Math.round(r.user_win_prob * 100);
    const o = r.optimal_win_prob != null ? Math.round(r.optimal_win_prob * 100) : null;
    const wl = document.createElement("div");
    wl.className = "winline";
    wl.title = WINPCT_HINT;
    wl.innerHTML =
      `<b>≈${u}% win</b> with your opening`
      + (o != null ? ` <span style="color:#6f8597">· best pick = ${o}% win</span>` : "")
      + `<br><span class="hint" style="margin:2px 0 0">${WINPCT_LABEL} — your win-% reflects how much your opening out-produces your opponent's.</span>`;
    div.appendChild(wl);
  }

  const sg = (i) => r.grades.find((g) => g.kind === "settlement" && g.placement_index === i);
  const rg = (i) => r.grades.find((g) => g.kind === "road" && g.placement_index === i);
  const n = USER_PIECES[r.seat];
  for (let i = 0; i < n; i++) {
    const s = sg(i), road = rg(i);
    const head = "Your placement";
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
  const chosen = userChoicePlacements(r);
  rankedForDisplay(r.ranking).forEach((rec, i) => {
    const row = document.createElement("div");
    row.className = "rec" + (rec === practiceSel ? " sel" : "");
    const spots = rec.placements
      .map((p) => `${spotName(p.settlement)} (${roadDir(p.settlement, p.road)})`)
      .join("  +  ");
    const mine = recMatchesChoice(rec, chosen)
      ? `<span style="float:right; color:#9ed9ad; font-weight:600">(your choice)</span>` : "";
    row.innerHTML = `${mine}<b>#${i + 1}</b> ${spots}<br><span style="color:#8aa0b3">${scoreLabel(rec)}</span>`;
    row.onclick = () => { practiceSel = rec; render(); renderFeedback(); };
    // Per-pick toggle to reveal the rest of the optimal draft behind this pick.
    if (rec.continuation) {
      const revealed = rec === practiceReveal;
      const btn = document.createElement("button");
      btn.className = "revealBtn";
      btn.textContent = revealed ? "Hide rest of draft" : "Reveal rest of draft";
      btn.style.cssText = "margin-top:6px; font-size:11px; padding:2px 8px; cursor:pointer;"
        + "border-radius:5px; border:1px solid #38465a; background:" + (revealed ? "#2f6fc4" : "#1b2430")
        + "; color:#e6edf3;";
      btn.onclick = (ev) => {
        ev.stopPropagation();
        practiceReveal = revealed ? null : rec;
        if (!revealed) practiceSel = rec;  // keep the selection consistent with the reveal
        render(); renderFeedback();
      };
      row.appendChild(btn);
    }
    div.appendChild(row);
  });
  const legend = document.createElement("p");
  legend.className = "hint";
  legend.innerHTML = "★ (in your colour) = model answer · cyan = a pick you clicked · ring = your spot (green ok / orange off)."
    + "<br>Spots read as <b>numbers-of-adjacent-hexes (road direction)</b>, e.g. 5-6-9 (L)."
    + "<br><b>Reveal rest of draft</b> plays the opening out optimally: the opponent's best replies (in their colour) and your remaining optimal spot"
    + (puzzle.seat === "FIRST" ? " — numbered 1/2 to show which settlement you'd place first vs last." : ".")
    + (n > 1 ? "<br>" + SECOND_ORDER_NOTE : "");
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

function resetScore() {
  score = { ...BASE_SCORE };
  saveScore();
  updateScoreboard();
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
