let dashboard = null;
let investMode = "aggregate";

const INVEST_BUTTONS = [
  ["aggregate", "Aggregate"],
  ["emailed", "Emailed"],
  ["viewed", "Viewed"],
  ["shared", "Shared"],
  ["shared_facebook", "Facebook"],
];

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function num(value) {
  if (value == null) return "—";
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 }).format(value);
}

function liftText(value) {
  const rounded = Math.round(value * 100) / 100;
  const text = rounded.toFixed(2).replace(/\.?0+$/, "");
  return `${text}×`;
}

async function fetchDashboard() {
  const live = await fetch("api/dashboard").catch(() => null);
  if (live && live.status !== 404) return live;
  return fetch("static/dashboard.json");
}

async function load() {
  const status = document.getElementById("status-line");
  status.textContent = "Loading charts…";
  try {
    const response = await fetchDashboard();
    dashboard = await response.json();
    if (!response.ok || dashboard.error) {
      status.textContent = dashboard.error || "The dashboard data could not be loaded.";
      return;
    }
    try {
      render();
    } catch (error) {
      status.textContent = `The page loaded, then failed to draw: ${error.message}`;
      throw error;
    }
  } catch (error) {
    if (status.textContent.startsWith("The page loaded")) return;
    status.textContent = "The dashboard server did not respond.";
  }
}

function render() {
  document.getElementById("status-line").textContent =
    'An analysis of data pulled from the NYT Developer "Top Stories" API and "Archive" API';
  const steps = [
    renderRecommendation,
    renderSite,
    renderDivest,
    () => renderBreakdown("regions-body", dashboard.region_board, {
      empty: "Region coverage needs the 2026 archive and the Most Popular lists.",
      axis: "Region",
      coverage: "Region coverage",
      coverageDefinition: "",
      popularityNoun: "place",
      layout: "gap",
      shortLegend: true,
    }),
    () => renderBreakdown("sections-body", dashboard.section_board, {
      empty: "Section coverage needs the 2026 archive and the Most Popular lists.",
      axis: "Section",
      coverage: "Section coverage",
      coverageDefinition: "the share of articles in the 2026 archive filed in this section.",
      popularityNoun: "section",
      layout: "heat",
      focus: ["Well", "Science", "Opinion"],
    }),
  ];
  steps.forEach((step) => {
    try {
      step();
    } catch (error) {
      document.getElementById("status-line").textContent = `The page loaded, then failed to draw: ${error.message}`;
    }
  });
}

function renderSite() {
  const body = document.getElementById("site-body");
  body.replaceChildren();
  const section = dashboard.section1;
  if (!section.ready) {
    body.append(el("p", "empty", section.message));
    return;
  }
  body.append(investmentBlock(dashboard.topic_board));
  const stats = el("ul", "stats");
  [
    [num(section.archive_articles), "Archive articles, January–October 2026"],
    [num(section.popular_articles), "Articles on a Most Popular list"],
  ].forEach(([value, label]) => {
    const item = el("li");
    item.append(el("strong", null, value), el("span", null, label));
    stats.append(item);
  });
  body.append(stats);
  if (section.partial) {
    body.append(el("p", "note", `Archive coverage is ${section.months_loaded} of ${section.months_expected} months. Base rates will move as the remaining months load.`));
  }
}

function chart(title, rows, kind) {
  const block = el("div", "chart");
  block.append(el("h3", null, title));
  if (!rows || !rows.length) {
    block.append(el("p", "note", "No tag clears the minimum of 2 popular articles and 20 archive articles."));
    return block;
  }
  const ranked = [...rows].sort((a, b) => b.lift - a.lift || a.tag.localeCompare(b.tag));
  const max = Math.max(...ranked.map((row) => row.lift), 0.01);
  ranked.forEach((row) => {
    const line = el("div", "bar-row");
    const name = el("span");
    name.append(el("span", "bar-name", row.tag), el("span", "bar-meta", `${row.popular_pct}% of popular · ${row.archive_pct}% of archive`));
    const track = el("span", "track");
    const fill = el("span", row.lift >= 1.2 ? "fill" : "fill quiet");
    fill.style.width = `${Math.max(2, (row.lift / max) * 100)}%`;
    track.append(fill);
    line.append(name, track, el("span", "lift", liftText(row.lift)));
    block.append(line);
  });
  return block;
}

function pctText(value) {
  return `${Number(value).toFixed(1)}%`;
}

const POPULARITY_LIST_NAMES = {
  aggregate: "Most Popular list",
  emailed: "emailed list",
  viewed: "viewed list",
  shared: "shared list",
  shared_facebook: "Facebook list",
};
const SVG_NS = "http://www.w3.org/2000/svg";
const SCATTER_SIZE = 460;
const SCATTER_MARGIN = { left: 60, top: 16, right: 16, bottom: 60 };
const SCATTER_WIDTH = SCATTER_MARGIN.left + SCATTER_SIZE + SCATTER_MARGIN.right;
const SCATTER_HEIGHT = SCATTER_MARGIN.top + SCATTER_SIZE + SCATTER_MARGIN.bottom;
const SCATTER_LABELS = {
  "United States Politics and Government": { text: "U.S. politics", side: "left" },
  "Midterm Elections (2026)": { text: "Midterms", side: "right" },
  "Elections, Senate": { text: "Senate", side: "right" },
  "Corruption (Institutional)": { text: "Corruption", side: "right" },
  "Research": { text: "Research", side: "left" },
  "US and Israeli Attack on Iran (2026)": { text: "Iran war", side: "right" },
};

function svgNode(tag, attrs, text) {
  const node = document.createElementNS(SVG_NS, tag);
  Object.entries(attrs || {}).forEach(([key, value]) => node.setAttribute(key, String(value)));
  if (text != null) node.textContent = text;
  return node;
}

const SCATTER_LOG_LO = Math.log10(0.5);
const SCATTER_LOG_HI = Math.log10(50);
const SCATTER_FULL_SPAN = SCATTER_LOG_HI - SCATTER_LOG_LO;
const SCATTER_MIN_SPAN = 0.25;
const SCATTER_TICK_CANDIDATES = [0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100];
const SCATTER_DEFAULT_VIEW = {
  centerX: (SCATTER_LOG_LO + SCATTER_LOG_HI) / 2,
  centerY: (SCATTER_LOG_LO + SCATTER_LOG_HI) / 2,
  span: SCATTER_FULL_SPAN,
};
const scatterView = { ...SCATTER_DEFAULT_VIEW };

function viewBounds() {
  const half = scatterView.span / 2;
  return {
    x0: scatterView.centerX - half,
    y0: scatterView.centerY - half,
    span: scatterView.span,
  };
}

function clampScatterView() {
  scatterView.span = Math.min(Math.max(scatterView.span, SCATTER_MIN_SPAN), SCATTER_FULL_SPAN);
  const half = scatterView.span / 2;
  scatterView.centerX = Math.min(Math.max(scatterView.centerX, SCATTER_LOG_LO + half), SCATTER_LOG_HI - half);
  scatterView.centerY = Math.min(Math.max(scatterView.centerY, SCATTER_LOG_LO + half), SCATTER_LOG_HI - half);
}

function setScatterView(centerX, centerY, span) {
  scatterView.centerX = centerX;
  scatterView.centerY = centerY;
  scatterView.span = span;
  clampScatterView();
}

function zoomScatterAt(factor, fx, fy) {
  const bounds = viewBounds();
  const anchorX = bounds.x0 + fx * bounds.span;
  const anchorY = bounds.y0 + (1 - fy) * bounds.span;
  const span = Math.min(Math.max(bounds.span * factor, SCATTER_MIN_SPAN), SCATTER_FULL_SPAN);
  setScatterView(anchorX + (0.5 - fx) * span, anchorY + (fy - 0.5) * span, span);
}

function visibleTicks(low, span) {
  return SCATTER_TICK_CANDIDATES.filter((tick) => {
    const value = Math.log10(tick);
    return value >= low - 1e-9 && value <= low + span + 1e-9;
  });
}

function topicRows(investment, mode) {
  const listTotal = investment.modes[mode].articles;
  return investment.topics.map((row) => {
    const coverage = Number(row.archive_pct) || 0;
    const popularity = Number(row.scores[mode].pct) || 0;
    return {
      topic: row.topic,
      coverage,
      popularity,
      ratio: coverage > 0 ? popularity / coverage : 0,
      archiveArticles: row.archive_articles,
      listArticles: row.scores[mode].articles,
      listTotal,
    };
  });
}

function topicSummary(point, investment, mode) {
  return `${point.topic}: ${pctText(point.coverage)} of archive, ${pctText(point.popularity)} of ${investment.modes[mode].label.toLowerCase()} list, ratio ${liftText(point.ratio)}`;
}

function topicTipContent(point, investment, mode) {
  const label = investment.modes[mode].label;
  let ratioLine;
  if (point.popularity === 0) {
    ratioLine = "Not on this list, so the dot sits on the bottom edge.";
  } else if (point.ratio >= 1) {
    ratioLine = `Ratio ${liftText(point.ratio)}: draws more readers than its share of the archive.`;
  } else {
    ratioLine = `Ratio ${liftText(point.ratio)}: draws fewer readers than its share of the archive.`;
  }
  return [
    el("strong", null, point.topic),
    el("span", null, `Archive: ${pctText(point.coverage)} of Jan–Oct 2026 articles (${num(point.archiveArticles)} articles)`),
    el("span", null, `${label} list: ${pctText(point.popularity)} (${num(point.listArticles)} of ${num(point.listTotal)} articles)`),
    el("span", null, ratioLine),
  ];
}

function showTopicTip(stage, node, point, investment, mode) {
  const tip = stage.querySelector(".topic-tip");
  tip.replaceChildren(...topicTipContent(point, investment, mode));
  tip.hidden = false;
  const stageRect = stage.getBoundingClientRect();
  const dotRect = node.getBoundingClientRect();
  const dotX = dotRect.left - stageRect.left + dotRect.width / 2;
  const dotY = dotRect.top - stageRect.top + dotRect.height / 2;
  let x = dotX + 14;
  if (x + tip.offsetWidth > stage.clientWidth) x = dotX - tip.offsetWidth - 14;
  const y = Math.min(Math.max(dotY - tip.offsetHeight / 2, 0), Math.max(stage.clientHeight - tip.offsetHeight, 0));
  tip.style.left = `${Math.max(x, 0)}px`;
  tip.style.top = `${y}px`;
}

function hideTopicTip(stage) {
  const tip = stage.querySelector(".topic-tip");
  if (tip) tip.hidden = true;
}

function pointerPlotFraction(stage, event) {
  const rect = stage.querySelector("svg").getBoundingClientRect();
  const vx = ((event.clientX - rect.left) / rect.width) * SCATTER_WIDTH;
  const vy = ((event.clientY - rect.top) / rect.height) * SCATTER_HEIGHT;
  return {
    fx: Math.min(Math.max((vx - SCATTER_MARGIN.left) / SCATTER_SIZE, 0), 1),
    fy: Math.min(Math.max((vy - SCATTER_MARGIN.top) / SCATTER_SIZE, 0), 1),
  };
}

function drawTopicScatter(stage, points, mode, investment) {
  const { left, top } = SCATTER_MARGIN;
  const size = SCATTER_SIZE;
  const plotRight = left + size;
  const plotBottom = top + size;
  const bounds = viewBounds();
  const fraction = (value, low) => (value > 0 ? (Math.log10(value) - low) / bounds.span : 0);
  const px = (value) => left + fraction(value, bounds.x0) * size;
  const py = (value) => plotBottom - fraction(value, bounds.y0) * size;
  const listName = POPULARITY_LIST_NAMES[mode];
  const xTicks = visibleTicks(bounds.x0, bounds.span);
  const yTicks = visibleTicks(bounds.y0, bounds.span);
  const inside = (cx, cy) => cx >= left && cx <= plotRight && cy >= top && cy <= plotBottom;

  const svg = svgNode("svg", {
    class: "topic-scatter-svg",
    viewBox: `0 0 ${SCATTER_WIDTH} ${SCATTER_HEIGHT}`,
    role: "img",
    "aria-label": `Scatter of ${points.length} topics. Across is share of the 2026 archive, up is share of the ${listName}. Dots above the dashed line draw more readers than their coverage. Zoom with the buttons or Ctrl plus scroll.`,
  });
  const defs = svgNode("defs");
  const clip = svgNode("clipPath", { id: "topic-plot-clip" });
  clip.append(svgNode("rect", { x: left - 8, y: top - 8, width: size + 16, height: size + 16 }));
  defs.append(clip);
  svg.append(defs);
  svg.append(svgNode("rect", { class: "plot-bg", x: left, y: top, width: size, height: size }));

  const data = svgNode("g", { "clip-path": "url(#topic-plot-clip)" });
  xTicks.forEach((tick) => data.append(svgNode("line", { class: "topic-grid", x1: px(tick), y1: top, x2: px(tick), y2: plotBottom })));
  yTicks.forEach((tick) => data.append(svgNode("line", { class: "topic-grid", x1: left, y1: py(tick), x2: plotRight, y2: py(tick) })));

  const diagonalLow = Math.max(bounds.x0, bounds.y0);
  const diagonalHigh = Math.min(bounds.x0, bounds.y0) + bounds.span;
  if (diagonalHigh > diagonalLow) {
    data.append(svgNode("line", {
      class: "topic-equal",
      x1: px(10 ** diagonalLow), y1: py(10 ** diagonalLow),
      x2: px(10 ** diagonalHigh), y2: py(10 ** diagonalHigh),
    }));
    const labelAt = diagonalLow + (diagonalHigh - diagonalLow) * 0.6;
    data.append(svgNode("text", { class: "topic-note-label", x: px(10 ** labelAt) + 8, y: py(10 ** labelAt) + 16 }, "Equal share"));
  }

  points.forEach((point) => {
    const cx = px(point.coverage);
    const cy = py(point.popularity);
    const ahead = point.ratio >= 1 && point.popularity > 0;
    const dot = svgNode("circle", {
      class: ahead ? "topic-dot ahead" : "topic-dot behind",
      cx,
      cy,
      r: 6,
    });
    if (inside(cx, cy)) {
      dot.setAttribute("tabindex", "0");
      dot.setAttribute("aria-label", topicSummary(point, investment, mode));
      const show = () => showTopicTip(stage, dot, point, investment, mode);
      dot.addEventListener("pointerenter", show);
      dot.addEventListener("focus", show);
      dot.addEventListener("pointerleave", () => hideTopicTip(stage));
      dot.addEventListener("blur", () => hideTopicTip(stage));
    }
    data.append(dot);
  });

  points.forEach((point) => {
    const label = SCATTER_LABELS[point.topic];
    const cx = px(point.coverage);
    const cy = py(point.popularity);
    if (!label || !inside(cx, cy)) return;
    const placement = {
      right: { x: cx + 9, y: cy + 4, anchor: "start" },
      left: { x: cx - 9, y: cy + 4, anchor: "end" },
    }[label.side];
    data.append(svgNode("text", {
      class: "topic-label",
      x: placement.x,
      y: placement.y,
      "text-anchor": placement.anchor,
    }, label.text));
  });
  svg.append(data);

  svg.append(svgNode("line", { class: "topic-axis", x1: left, y1: top, x2: left, y2: plotBottom }));
  svg.append(svgNode("line", { class: "topic-axis", x1: left, y1: plotBottom, x2: plotRight, y2: plotBottom }));
  xTicks.forEach((tick) => svg.append(svgNode("text", { class: "tick", x: px(tick), y: plotBottom + 18, "text-anchor": "middle" }, `${tick}%`)));
  yTicks.forEach((tick) => svg.append(svgNode("text", { class: "tick", x: left - 8, y: py(tick) + 4, "text-anchor": "end" }, `${tick}%`)));
  svg.append(svgNode("text", { class: "axis-title", x: left + size / 2, y: SCATTER_HEIGHT - 10, "text-anchor": "middle" }, "Share of Jan–Oct 2026 archive"));
  svg.append(svgNode("text", {
    class: "axis-title",
    x: 16,
    y: top + size / 2,
    "text-anchor": "middle",
    transform: `rotate(-90 16 ${top + size / 2})`,
  }, `Share of ${listName}`));

  const previous = stage.querySelector("svg");
  if (previous) previous.remove();
  hideTopicTip(stage);
  stage.prepend(svg);
}

function topicTable(points) {
  const ranked = [...points].sort((a, b) => b.ratio - a.ratio || a.topic.localeCompare(b.topic));
  const table = el("table", "topic-table");
  table.setAttribute("aria-label", "Topics ranked by popularity share divided by archive share");
  const head = el("tr");
  ["Rank", "Topic", "Archive", "Popular", "Ratio"].forEach((label, index) => {
    head.append(el("th", index >= 2 ? "num" : null, label));
  });
  const thead = el("thead");
  thead.append(head);
  const body = el("tbody");
  ranked.forEach((row, index) => {
    const ahead = row.ratio >= 1 && row.popularity > 0;
    const line = el("tr");
    line.append(
      el("td", "num topic-rank", String(index + 1)),
      el("td", "topic-name", row.topic),
      el("td", "num", pctText(row.coverage)),
      el("td", "num", pctText(row.popularity)),
      el("td", `num topic-ratio ${ahead ? "ahead" : "behind"}`, liftText(row.ratio)),
    );
    body.append(line);
  });
  table.append(thead, body);
  return table;
}

function topicCompare(investment, mode) {
  const points = topicRows(investment, mode);
  const wrap = el("div", "topic-compare");

  const plot = el("div", "topic-plot");
  const stage = el("div", "topic-stage");
  stage.tabIndex = 0;
  stage.setAttribute("role", "group");
  stage.setAttribute("aria-label", "Zoomable scatter plot. Plus and minus zoom, arrow keys pan, and zero resets the view.");
  const tip = el("div", "topic-tip");
  tip.hidden = true;
  tip.setAttribute("aria-hidden", "true");
  stage.append(tip);

  const refresh = () => drawTopicScatter(stage, points, mode, investment);
  const resetView = () => setScatterView(SCATTER_DEFAULT_VIEW.centerX, SCATTER_DEFAULT_VIEW.centerY, SCATTER_DEFAULT_VIEW.span);
  const zoomIn = () => zoomScatterAt(1 / 1.5, 0.5, 0.5);
  const zoomOut = () => zoomScatterAt(1.5, 0.5, 0.5);
  stage.addEventListener("keydown", (event) => {
    const step = viewBounds().span * 0.1;
    const keyActions = {
      "+": zoomIn,
      "=": zoomIn,
      "-": zoomOut,
      "_": zoomOut,
      "0": resetView,
      ArrowLeft: () => { scatterView.centerX -= step; },
      ArrowRight: () => { scatterView.centerX += step; },
      ArrowUp: () => { scatterView.centerY += step; },
      ArrowDown: () => { scatterView.centerY -= step; },
    };
    const action = keyActions[event.key];
    if (!action) return;
    event.preventDefault();
    action();
    clampScatterView();
    refresh();
  });
  stage.addEventListener("dblclick", () => {
    resetView();
    refresh();
  });

  stage.addEventListener("wheel", (event) => {
    if (!event.ctrlKey && !event.metaKey) return;
    event.preventDefault();
    const { fx, fy } = pointerPlotFraction(stage, event);
    zoomScatterAt(event.deltaY > 0 ? 1.12 : 1 / 1.12, fx, fy);
    refresh();
  }, { passive: false });

  let drag = null;
  stage.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    drag = { x: event.clientX, y: event.clientY };
    stage.setPointerCapture(event.pointerId);
    stage.classList.add("is-panning");
    hideTopicTip(stage);
  });
  stage.addEventListener("pointermove", (event) => {
    if (!drag) return;
    const scale = stage.querySelector("svg").getBoundingClientRect().width / SCATTER_WIDTH;
    const unit = viewBounds().span / SCATTER_SIZE;
    scatterView.centerX -= ((event.clientX - drag.x) / scale) * unit;
    scatterView.centerY += ((event.clientY - drag.y) / scale) * unit;
    drag = { x: event.clientX, y: event.clientY };
    clampScatterView();
    refresh();
  });
  const endDrag = (event) => {
    if (!drag) return;
    drag = null;
    stage.classList.remove("is-panning");
    if (stage.hasPointerCapture(event.pointerId)) stage.releasePointerCapture(event.pointerId);
  };
  stage.addEventListener("pointerup", endDrag);
  stage.addEventListener("pointercancel", endDrag);

  refresh();
  plot.append(stage);
  const zeros = points.filter((point) => point.popularity === 0).length;
  if (zeros) {
    plot.append(el("p", "note", `${zeros === 1 ? "One topic had" : `${zeros} topics had`} 0% of this list, so ${zeros === 1 ? "its dot sits" : "those dots sit"} on the bottom edge.`));
  }

  const list = el("div", "topic-list");
  list.append(topicTable(points));
  list.append(el("p", "note", "Ratio is the Popular share divided by the Archive share. Above 1× means the topic draws more readers than its coverage."));

  wrap.append(plot, list);
  return wrap;
}

function divestChart(rows, scaleMax) {
  const chart = el("div", "divest-chart");
  const head = el("div", "divest-head");
  head.append(
    el("span", null, "Topic"),
    el("span", null, "Archive share"),
    el("span", "num", "Coverage"),
    el("span", "num", "Most Popular"),
  );
  chart.append(head);
  rows.forEach((row) => {
    const line = el("div", "divest-row");
    const name = el("div", "divest-name");
    name.append(
      el("strong", null, row.topic),
      el("span", "bar-meta", `${num(row.archive_articles)} archive articles`),
    );
    const track = el("span", "divest-track");
    const fill = el("span", "hbar-fill coverage");
    const share = Number(row.archive_pct) || 0;
    fill.style.width = `${scaleMax ? (share / scaleMax) * 100 : 0}%`;
    track.append(fill);
    line.append(
      name,
      track,
      el("span", "hbar-value coverage", pctText(share)),
      el("span", "divest-zero", "0 stories"),
    );
    chart.append(line);
  });
  return chart;
}

function mixColor(amount, max, target) {
  const scale = max <= 0 ? 0 : Math.max(0, Math.min(1, amount / max));
  const paper = [247, 244, 238];
  const rgb = paper.map((channel, index) => Math.round(channel + (target[index] - channel) * scale));
  return {
    background: `rgb(${rgb.join(",")})`,
    color: scale > 0.62 ? "#f6f1e7" : "#1c1916",
  };
}

function paintCell(node, amount, max, target) {
  const tone = mixColor(amount, max, target);
  node.style.background = tone.background;
  node.style.color = tone.color;
}

function heatMap(rows, mode, focus) {
  const ranked = rows.map((row) => {
    const coverage = Number(row.archive_pct);
    const popularity = Number(row.scores[mode].pct);
    return {
      topic: row.topic,
      coverage,
      popularity,
      lift: coverage > 0 ? popularity / coverage : 0,
    };
  }).sort((a, b) => b.lift - a.lift || a.topic.localeCompare(b.topic));
  const maxCoverage = Math.max(...ranked.map((row) => row.coverage), 0.01);
  const maxPopularity = Math.max(...ranked.map((row) => row.popularity), 0.01);
  const maxLift = Math.max(...ranked.map((row) => row.lift), 1);
  const names = focus || [];
  const wrap = el("div", "heat-map");
  const callouts = el("div", "heat-callouts");
  names.forEach((name) => {
    const row = ranked.find((item) => item.topic === name);
    if (!row) return;
    const card = el("article", "heat-callout");
    card.append(
      el("p", "heat-kicker", name),
      el("p", "heat-multiple", liftText(row.lift)),
      el("p", null, `${pctText(row.coverage)} of the 2026 archive, ${pctText(row.popularity)} of this list.`),
    );
    callouts.append(card);
  });
  if (callouts.childElementCount) wrap.append(callouts);

  const table = el("table", "heat-table");
  const head = el("tr");
  ["Section", "Coverage", "Popularity", "Opportunity"].forEach((label, index) => {
    head.append(el("th", index === 0 ? null : "num", label));
  });
  table.append(el("thead").appendChild(head).parentElement);
  const body = el("tbody");
  ranked.forEach((row) => {
    const line = el("tr", names.includes(row.topic) ? "heat-focus" : null);
    const coverage = el("td", "num heat-cell", pctText(row.coverage));
    const popularity = el("td", "num heat-cell", pctText(row.popularity));
    const opportunity = el("td", "num heat-cell", liftText(row.lift));
    paintCell(coverage, row.coverage, maxCoverage, [45, 74, 62]);
    paintCell(popularity, row.popularity, maxPopularity, [140, 29, 24]);
    paintCell(opportunity, Math.max(0, row.lift - 1), Math.max(0.01, maxLift - 1), [140, 29, 24]);
    line.append(el("td", "heat-name", row.topic), coverage, popularity, opportunity);
    body.append(line);
  });
  table.append(body);
  wrap.append(table);
  return wrap;
}

function pointsText(value) {
  const rounded = Math.round(Number(value) * 10) / 10;
  const body = Math.abs(rounded).toFixed(1);
  if (rounded > 0) return `+${body} pts`;
  if (rounded < 0) return `−${body} pts`;
  return "0.0 pts";
}

function scaleCeiling(value) {
  const padded = Number(value) * 1.08;
  const steps = [2, 4, 5, 8, 10, 15, 20, 25, 30, 40, 50, 60, 80, 100];
  return steps.find((step) => step >= padded) || 100;
}

function gapChart(rows, mode) {
  const ranked = [...rows].sort((a, b) => {
    const gapA = a.scores[mode].pct - a.archive_pct;
    const gapB = b.scores[mode].pct - b.archive_pct;
    return gapB - gapA || a.topic.localeCompare(b.topic);
  });
  const ceiling = scaleCeiling(Math.max(
    ...ranked.flatMap((row) => [row.archive_pct, row.scores[mode].pct]),
    0.01,
  ));
  const chart = el("div", "gap-chart");
  const scale = el("div", "gap-scale");
  const axis = el("div", "gap-axis");
  [0, ceiling / 2, ceiling].forEach((tick, index) => {
    const label = Number.isInteger(tick) ? String(tick) : tick.toFixed(1);
    const mark = el("span", ["start", "mid", "end"][index], `${label}%`);
    mark.style.left = `${(tick / ceiling) * 100}%`;
    axis.append(mark);
  });
  scale.append(el("div"), el("div"), axis, el("div", "gap-delta", "Gap"));
  chart.append(scale);

  ranked.forEach((row) => {
    const coverage = Number(row.archive_pct);
    const popularity = Number(row.scores[mode].pct);
    const gap = popularity - coverage;
    const line = el("div", "gap-row");
    const numbers = el("div", "gap-nums");
    numbers.append(
      el("span", "coverage", pctText(coverage)),
      el("span", "popularity", pctText(popularity)),
    );
    const track = el("div", "gap-track");
    const link = el("span", "gap-link");
    const start = Math.min(coverage, popularity);
    link.style.left = `${(start / ceiling) * 100}%`;
    link.style.width = `${Math.max(Math.abs(gap) / ceiling * 100, 0.6)}%`;
    const coverageDot = el("span", "gap-dot coverage");
    coverageDot.style.left = `${(coverage / ceiling) * 100}%`;
    coverageDot.title = `Coverage ${pctText(coverage)}`;
    const popularityDot = el("span", "gap-dot popularity");
    popularityDot.style.left = `${(popularity / ceiling) * 100}%`;
    popularityDot.title = `Popularity ${pctText(popularity)}`;
    track.append(link, coverageDot, popularityDot);
    line.append(
      el("div", "gap-name", row.topic),
      numbers,
      track,
      el("div", gap >= 0 ? "gap-delta ahead" : "gap-delta behind", pointsText(gap)),
    );
    chart.append(line);
  });
  return chart;
}

function axisMax(value) {
  const step = value <= 20 ? 5 : 10;
  return Math.max(step, Math.ceil((value * 1.12) / step) * step);
}

function legendItem(kind, title, definition) {
  const item = el("p", "legend-item");
  const text = el("span");
  text.append(el("strong", null, title));
  if (definition) text.append(document.createTextNode(` — ${definition}`));
  item.append(el("span", `swatch ${kind}`), text);
  return item;
}

function columnChart(rows, mode, axisLabel = "Topic", coverageName = "Topic coverage") {
  const values = rows.flatMap((row) => [row.archive_pct, row.scores[mode].pct]);
  const yMax = axisMax(Math.max(...values, 0));
  const step = yMax <= 20 ? 5 : 10;
  const ticks = [];
  for (let tick = yMax; tick >= 0; tick -= step) ticks.push(tick);

  const chart = el("div", "column-chart");
  chart.setAttribute("role", "img");
  chart.setAttribute("aria-label", `Double bar chart of ${coverageName.toLowerCase()} and popularity by ${axisLabel.toLowerCase()}. The vertical axis is percentage.`);

  const yTitle = el("div", "y-title", "Percentage");
  const yAxis = el("div", "y-axis");
  ticks.forEach((tick) => yAxis.append(el("span", null, pctText(tick))));

  const plot = el("div", "plot");
  const stage = el("div", "stage");
  ticks.forEach((tick) => {
    if (!tick) return;
    const line = el("span", "gridline");
    line.style.bottom = `${(tick / yMax) * 100}%`;
    stage.append(line);
  });
  rows.forEach((row) => {
    const popularity = row.scores[mode].pct;
    const group = el("div", "bar-group");
    [
      ["coverage", row.archive_pct, coverageName],
      ["popularity", popularity, "Popularity"],
    ].forEach(([kind, value, name]) => {
      const column = el("div", `column ${kind}`);
      column.style.height = `${(value / yMax) * 100}%`;
      column.title = `${row.topic}: ${name} ${pctText(value)}`;
      group.append(column);
    });
    stage.append(group);
  });
  plot.append(stage);

  const labels = el("div", "x-labels");
  rows.forEach((row) => {
    const label = el("div", "x-label");
    const values = el("div", "x-values");
    values.append(
      el("span", "coverage", pctText(row.archive_pct)),
      el("span", "popularity", pctText(row.scores[mode].pct)),
    );
    label.append(values, el("div", null, row.topic));
    labels.append(label);
  });
  const xCaption = el("div", "x-caption", axisLabel);

  chart.append(yTitle, yAxis, plot, labels, xCaption);
  return chart;
}

function investmentBlock(board) {
  const wrap = el("div");
  const investment = board && board.investment;
  if (!board || !board.ready || !investment || !investment.topics.length) {
    wrap.append(el("p", "empty", "This ranking needs the 2026 archive and the Most Popular lists."));
    return wrap;
  }
  wrap.append(el("h3", null, "Investment performance"));
  const switcher = el("div", "switcher");
  INVEST_BUTTONS.forEach(([id, label]) => {
    const button = el("button", null, label);
    button.type = "button";
    button.setAttribute("aria-pressed", investMode === id ? "true" : "false");
    button.addEventListener("click", () => {
      investMode = id;
      render();
    });
    switcher.append(button);
  });
  wrap.append(switcher);
  wrap.append(topicCompare(investment, investMode));
  const popularityDefinition = {
    aggregate: "the share of Most Popular articles with this topic. A story on more than one list counts once.",
    emailed: "the share of emailed articles with this topic. A story on the 1-day and 30-day lists counts once.",
    viewed: "the share of viewed articles with this topic. A story on the 1-day and 30-day lists counts once.",
    shared: "the share of shared articles with this topic. A story on the 1-day and 30-day lists counts once.",
    shared_facebook: "the share of Facebook-shared articles with this topic. A story on the 1-day and 30-day lists counts once.",
  }[investMode];
  const legend = el("div", "legend");
  legend.append(
    legendItem("ahead", "Filled dot", "popularity is ahead of coverage, above the dashed line."),
    legendItem("behind", "Hollow dot", "popularity trails coverage, below the line."),
  );
  wrap.append(legend);
  wrap.append(el("p", "note", `Across: the share of 2026 archive articles with this topic. Up: ${popularityDefinition}`));
  if (board.facebook_matches_shared && (investMode === "shared" || investMode === "shared_facebook")) {
    wrap.append(el("p", "note", "On this pull, the Facebook list is the same articles as the shared list, so those two charts match."));
  }
  return wrap;
}

function renderDivest() {
  const body = document.getElementById("divest-body");
  body.replaceChildren();
  const investment = dashboard.topic_board && dashboard.topic_board.investment;
  const unpaid = investment && investment.unpaid;
  if (!unpaid || !unpaid.length) {
    body.append(el("p", "empty", "Topics with no Most Popular stories will show here once the archive and lists are loaded."));
    return;
  }
  const scale = axisMax(Math.max(...unpaid.map((row) => row.archive_pct), 0.01));
  body.append(divestChart(unpaid, scale));
  const legend = el("div", "legend");
  legend.append(
    legendItem("coverage", "Archive share", "the share of 2026 archive articles with this topic, even though none of those stories reached a Most Popular list."),
  );
  body.append(legend);
}

function renderBreakdown(elementId, board, copy) {
  const body = document.getElementById(elementId);
  body.replaceChildren();
  const investment = board && board.investment;
  if (!board || !board.ready || !investment || !investment.topics.length) {
    body.append(el("p", "empty", copy.empty));
    return;
  }
  const locked = copy.layout === "gap" || copy.layout === "heat";
  const mode = locked ? "aggregate" : investMode;
  if (!locked) {
    const switcher = el("div", "switcher");
    INVEST_BUTTONS.forEach(([id, label]) => {
      const button = el("button", null, label);
      button.type = "button";
      button.setAttribute("aria-pressed", investMode === id ? "true" : "false");
      button.addEventListener("click", () => {
        investMode = id;
        render();
      });
      switcher.append(button);
    });
    body.append(switcher);
  }
  body.append(copy.layout === "gap"
    ? gapChart(investment.topics, mode)
    : copy.layout === "heat"
      ? heatMap(investment.topics, mode, copy.focus)
      : columnChart(investment.topics, mode, copy.axis, copy.coverage));
  const popularityDefinition = {
    aggregate: `the share of Most Popular articles with this ${copy.popularityNoun}. A story on more than one list counts once.`,
    emailed: `the share of emailed articles with this ${copy.popularityNoun}. A story on the 1-day and 30-day lists counts once.`,
    viewed: `the share of viewed articles with this ${copy.popularityNoun}. A story on the 1-day and 30-day lists counts once.`,
    shared: `the share of shared articles with this ${copy.popularityNoun}. A story on the 1-day and 30-day lists counts once.`,
    shared_facebook: `the share of Facebook-shared articles with this ${copy.popularityNoun}. A story on the 1-day and 30-day lists counts once.`,
  }[mode];
  const legend = el("div", "legend");
  legend.append(
    legendItem("coverage", copy.coverage, copy.shortLegend ? "" : copy.coverageDefinition),
    legendItem("popularity", "Popularity (October 2026)", copy.shortLegend ? "" : popularityDefinition),
  );
  body.append(legend);
  if (copy.layout === "heat") {
    body.append(el("p", "note", "Darker red in Opportunity means the section is more common on the combined Most Popular list than in the 2026 archive. A section at 1× shows up in the same proportion as it is written."));
  }
  if (board.facebook_matches_shared && (mode === "shared" || mode === "shared_facebook")) {
    body.append(el("p", "note", "On this pull, the Facebook list is the same articles as the shared list, so those two charts match."));
  }
}

function recommendationCard(area, title, copy) {
  const item = el("article", "card");
  item.append(el("p", "area", area), el("h3", null, title), copy);
  return item;
}

function renderRecommendation() {
  const body = document.getElementById("recommendation-body");
  body.replaceChildren();
  const elections = el("p");
  elections.append(
    "Put more reporting weight on U.S. elections. It appears that Midterm elections in 2026 constitute 18.9% of the Most Popular articles in Oct 2026 against 9.0% of the January–October 2026 archive, which implies that the midterm elections were ~2.1× more popular relative to coverage. Given in 2027, we will be past the Midterms, the Times should take this opportunity to invest heavily in coverage of the mounting 2028 primaries and general election. Another area of opportunity is topic coverage on ",
    el("em", null, "corruption"),
    ", which generates much more engagement relative to how often it's covered, and in particular, gets shared.",
  );
  const cards = el("div", "cards");
  cards.append(
    recommendationCard("Topical", "Elections", elections),
    recommendationCard("Regional", "Ukraine", el("p", null, "Readers care about what's happening in the Ukraine war, with the country earning a 4.7% share of most popular articles by region. As a result, the Times should think about expanding coverage of Ukraine and presenting reporting about the topic in visual and video formats")),
    recommendationCard("Section", "Well", el("p", null, "7.1% of the most popular articles in Oct 2026 came from the Well section of the paper. This is in line with broader trends in society, where there is an increased emphasis on physical health, eating properly, and mental wellbeing. To expand the Well section, we could bring on more science reporters and increase coverage of research on wellbeing.")),
    recommendationCard("Section", "Opinion", el("p", null, "Opinion pieces resonate with Times readers, but to expand opinion writing, we need a strategy to increase freelancer and op-ed contributor recruitment. Times editors could host workshops or webinars in partnership with community organizations, in an attempt to increase the diversity and throughput of opinion pieces on the site.")),
  );
  body.append(cards);
}

load();
