// Spool Maker UI: schema-driven controls, URL state, live three.js preview.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { STLLoader } from "three/addons/loaders/STLLoader.js";

const DEBOUNCE_MS = 250;
const EXPLODE_MM = 60;
const DEFAULT_COLOR = "#f28c28";
const SWATCHES = ["#f28c28", "#e8e4dc", "#2b2b2b", "#3b7dd8", "#4caf50", "#d64550", "#9b6dd6"];

const GROUPS = ["Refill", "Size", "Pattern", "Personalize", "Extras", "Print"];

// name -> {label, unit, group, help, step}
const FIELD_META = {
  refill: { label: "Refill coil", group: "Refill" },
  coil_inner_diameter: { label: "Coil inner diameter", unit: "mm", group: "Refill", step: 0.5 },
  coil_width: { label: "Coil width", unit: "mm", group: "Refill", step: 0.5 },
  coil_clearance: { label: "Coil clearance", unit: "mm", group: "Refill", step: 0.05,
    help: "Extra room between the coil and the flanges." },
  outer_diameter: { label: "Outer diameter", unit: "mm", group: "Size", step: 0.5 },
  bore_diameter: { label: "Bore diameter", unit: "mm", group: "Size", step: 0.5,
    help: "Centre hole that rides on the AMS / holder spindle." },
  flange_thickness: { label: "Flange thickness", unit: "mm", group: "Size", step: 0.1 },
  pattern: { label: "Flange pattern", group: "Pattern" },
  pattern_density: { label: "Pattern density", group: "Pattern", step: 0.01,
    help: "Higher means more open area and a lighter spool." },
  pattern_seed: { label: "Pattern seed", group: "Pattern", step: 1,
    help: "Reshuffles randomised patterns (voronoi, holes)." },
  lightweight: { label: "Lightweight mode", group: "Pattern",
    help: "Thinner, more open structure. Prints faster, uses less filament." },
  label: { label: "Label panel", group: "Personalize" },
  label_width: { label: "Label width", unit: "mm", group: "Personalize", step: 0.5 },
  label_height: { label: "Label height", unit: "mm", group: "Personalize", step: 0.5 },
  text: { label: "Engraved text", group: "Personalize", help: "Up to 24 characters." },
  color: { label: "Preview colour", group: "Personalize",
    help: "Only changes the preview — print in whatever you like." },
  gauge: { label: "Remaining-filament gauge", group: "Extras" },
  gauge_material: { label: "Gauge material", group: "Extras",
    help: "Filament the gauge ticks are calibrated for." },
  clip_holes: { label: "Filament clip holes", group: "Extras", step: 1 },
  tag_pocket: { label: "NFC tag pocket", group: "Extras" },
  tag_diameter: { label: "Tag diameter", unit: "mm", group: "Extras" },
  lock_clearance: { label: "Twist-lock clearance", unit: "mm", group: "Print", step: 0.01,
    help: "Loosen if the halves are hard to twist together." },
  print_material: { label: "Print material", group: "Print",
    help: "Used for the weight estimate." },
};

// ---------- state ----------

let schema = null;
let model = {};          // current values, keyed by field name (+ color)
let reqSeq = 0;          // monotonically increasing request id
let debounceTimer = null;
let lastValid = false;
let framed = false;
const controls = {};     // name -> {set(value), setDisabled(bool)}

const $ = (id) => document.getElementById(id);

function humanize(name) {
  const s = name.replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function metaFor(name) {
  return FIELD_META[name] || { label: humanize(name), group: "Extras" };
}

function decimals(step) {
  const s = String(step);
  return s.includes(".") ? s.split(".")[1].length : 0;
}

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else node.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children) if (c) node.append(c);
  return node;
}

// ---------- query <-> model ----------

function parseValue(def, raw) {
  if (def.type === "bool") {
    const v = String(raw).trim().toLowerCase();
    if (["1", "true", "on"].includes(v)) return true;
    if (["0", "false", "off", ""].includes(v)) return false;
    return def.default;
  }
  if (def.type === "string") return String(raw).slice(0, def.max_length ?? 24);
  if (def.type === "choice") {
    const match = def.choices.find((c) => String(c) === String(raw));
    return match === undefined ? def.default : match;
  }
  const n = Number(raw);
  if (!Number.isFinite(n)) return def.default;
  const v = def.type === "int" ? Math.trunc(n) : n;
  return clamp(v, def.min, def.max);
}

function clamp(v, lo, hi) {
  if (lo !== undefined && v < lo) return lo;
  if (hi !== undefined && v > hi) return hi;
  return v;
}

function isCustom() { return model.refill === "custom"; }

function applyPreset() {
  if (isCustom()) return;
  const p = schema.presets[model.refill];
  if (!p) return;
  model.coil_inner_diameter = p.inner_diameter;
  model.coil_width = p.width;
}

function buildQuery() {
  const q = new URLSearchParams();
  for (const [name, def] of Object.entries(schema.fields)) {
    if (!isCustom() && (name === "coil_inner_diameter" || name === "coil_width")) continue;
    const v = model[name];
    if (v === def.default) continue;
    q.set(name, def.type === "bool" ? (v ? "1" : "0") : String(v));
  }
  if (model.color !== DEFAULT_COLOR) q.set("color", model.color);
  return q;
}

function readUrl() {
  const params = new URLSearchParams(location.search);
  for (const [name, def] of Object.entries(schema.fields)) {
    model[name] = params.has(name) ? parseValue(def, params.get(name)) : def.default;
  }
  const c = params.get("color");
  model.color = c && /^#?[0-9a-f]{6}$/i.test(c) ? (c.startsWith("#") ? c : "#" + c).toLowerCase()
    : DEFAULT_COLOR;
  applyPreset();
}

function writeUrl() {
  const qs = buildQuery().toString();
  history.replaceState(null, "", qs ? `?${qs}` : location.pathname);
}

// ---------- controls ----------

function fieldWrap(name, labelNode, unit, help, ...body) {
  const head = el("div", { class: "field-head" }, labelNode,
    unit ? el("span", { class: "unit", text: unit }) : null);
  return el("div", { class: "field", "data-field": name }, head, ...body,
    help ? el("p", { class: "help", id: `help-${name}`, text: help }) : null);
}

function makeRange(name, def, meta) {
  const id = `f-${name}`;
  const step = meta.step ?? (def.type === "int" ? 1 : 0.1);
  const dp = decimals(step);
  const slider = el("input", { type: "range", id: `${id}-range`, min: def.min, max: def.max,
    step, "aria-label": `${meta.label} slider`, "aria-describedby": meta.help ? `help-${name}` : null });
  const number = el("input", { type: "number", id, min: def.min, max: def.max, step,
    inputmode: "decimal", "aria-describedby": meta.help ? `help-${name}` : null });
  const fmt = (v) => Number(v).toFixed(dp);
  const set = (v) => { slider.value = v; number.value = fmt(v); };

  slider.addEventListener("input", () => {
    const v = parseValue(def, Number(Number(slider.value).toFixed(dp)));
    number.value = fmt(v);
    commit(name, v);
  });
  number.addEventListener("change", () => {
    const v = parseValue(def, number.value === "" ? model[name] : number.value);
    set(v);
    commit(name, v);
  });

  const label = el("label", { for: id, text: meta.label });
  const node = fieldWrap(name, label, meta.unit, meta.help,
    el("div", { class: "range-row" }, slider, number));
  controls[name] = {
    set,
    setDisabled(d) { slider.disabled = d; number.disabled = d; node.classList.toggle("is-disabled", d); },
  };
  return node;
}

function makeSelect(name, def, meta) {
  const id = `f-${name}`;
  const select = el("select", { id, "aria-describedby": meta.help ? `help-${name}` : null });
  for (const c of def.choices) {
    let text = String(c);
    if (name === "refill" && schema.presets[c]) text = schema.presets[c].name;
    if (meta.unit) text += ` ${meta.unit}`;
    select.append(el("option", { value: String(c), text }));
  }
  select.addEventListener("change", () => commit(name, parseValue(def, select.value)));
  const label = el("label", { for: id, text: meta.label });
  const extra = name === "refill" ? el("span", { class: "badge", id: "preset-note", hidden: true,
    text: "dimensions unverified — measure your coil" }) : null;
  const node = fieldWrap(name, label, null, meta.help, select, extra);
  controls[name] = {
    set(v) { select.value = String(v); },
    setDisabled(d) { select.disabled = d; node.classList.toggle("is-disabled", d); },
  };
  return node;
}

function makeCheckbox(name, meta) {
  const id = `f-${name}`;
  const box = el("input", { type: "checkbox", id,
    "aria-describedby": meta.help ? `help-${name}` : null });
  box.addEventListener("change", () => commit(name, box.checked));
  const row = el("div", { class: "check-row" }, box, el("label", { for: id, text: meta.label }));
  const node = el("div", { class: "field", "data-field": name }, row,
    meta.help ? el("p", { class: "help", id: `help-${name}`, text: meta.help }) : null);
  controls[name] = {
    set(v) { box.checked = !!v; },
    setDisabled(d) { box.disabled = d; node.classList.toggle("is-disabled", d); },
  };
  return node;
}

function makeText(name, def, meta) {
  const id = `f-${name}`;
  const input = el("input", { type: "text", id, maxlength: def.max_length ?? 24,
    spellcheck: "false", "aria-describedby": meta.help ? `help-${name}` : null });
  input.addEventListener("input", () => commit(name, parseValue(def, input.value)));
  const node = fieldWrap(name, el("label", { for: id, text: meta.label }), null, meta.help, input);
  controls[name] = {
    set(v) { if (input.value !== v) input.value = v; },
    setDisabled(d) { input.disabled = d; },
  };
  return node;
}

function makeColor() {
  const meta = FIELD_META.color;
  const input = el("input", { type: "color", id: "f-color", "aria-describedby": "help-color" });
  const swatches = el("div", { class: "swatches", role: "group", "aria-label": "Colour presets" });
  const buttons = SWATCHES.map((hex) => {
    const b = el("button", { type: "button", class: "swatch", "aria-label": `Colour ${hex}`,
      "aria-pressed": "false" });
    b.style.background = hex;
    b.addEventListener("click", () => { setColor(hex); });
    swatches.append(b);
    return b;
  });
  input.addEventListener("input", () => setColor(input.value.toLowerCase()));
  const node = fieldWrap("color", el("label", { for: "f-color", text: meta.label }), null, meta.help,
    el("div", { class: "color-row" }, input, swatches));
  controls.color = {
    set(v) {
      input.value = v;
      buttons.forEach((b, i) => b.setAttribute("aria-pressed", String(SWATCHES[i] === v)));
    },
    setDisabled() {},
  };
  return node;
}

function buildControls() {
  const form = $("controls");
  form.replaceChildren();
  form.addEventListener("submit", (e) => e.preventDefault());
  const sets = Object.fromEntries(GROUPS.map((g, i) => [g, el("fieldset", { class: "group" },
    (() => {
      const lg = el("legend", { class: "group-title" });
      lg.append(el("span", { class: "num", text: String(i + 1).padStart(2, "0") }), g);
      return lg;
    })())]));

  // Deliberate order: FIELD_META order first (incl. the preview-only colour), then any
  // fields the backend added that the UI doesn't know about yet.
  const known = Object.keys(FIELD_META).filter((n) => n === "color" || n in schema.fields);
  const order = [...known, ...Object.keys(schema.fields).filter((n) => !(n in FIELD_META))];
  for (const name of order) {
    const meta = metaFor(name);
    if (name === "color") { sets[meta.group].append(makeColor()); continue; }
    const def = schema.fields[name];
    let node;
    if (def.type === "bool") node = makeCheckbox(name, meta);
    else if (def.type === "choice") node = makeSelect(name, def, meta);
    else if (def.type === "string") node = makeText(name, def, meta);
    else if (def.min !== undefined && def.max !== undefined) node = makeRange(name, def, meta);
    else {
      // numeric without a range: plain number input
      const id = `f-${name}`;
      const input = el("input", { type: "number", id, step: def.type === "int" ? 1 : "any" });
      input.addEventListener("change", () => commit(name, parseValue(def, input.value)));
      node = fieldWrap(name, el("label", { for: id, text: meta.label }), meta.unit, meta.help, input);
      controls[name] = { set(v) { input.value = v; }, setDisabled(d) { input.disabled = d; } };
    }
    (sets[meta.group] || sets.Extras).append(node);
  }
  for (const g of GROUPS) if (sets[g].children.length > 1) form.append(sets[g]);
}

function syncControls() {
  for (const [name, c] of Object.entries(controls)) c.set(model[name]);
  const presetLocked = !isCustom();
  controls.coil_inner_diameter?.setDisabled(presetLocked);
  controls.coil_width?.setDisabled(presetLocked);
  const p = schema.presets[model.refill];
  const note = $("preset-note");
  if (note) note.hidden = !(p && !p.verified && presetLocked);
  // dependent controls
  controls.label_width?.setDisabled(!model.label);
  controls.label_height?.setDisabled(!model.label);
  controls.gauge_material?.setDisabled(!model.gauge);
  controls.tag_diameter?.setDisabled(!model.tag_pocket);
}

function setDownloads(enabled) {
  for (const b of ["dl-a", "dl-b", "dl-3mf"]) $(b).disabled = !enabled;
}

function commit(name, value) {
  model[name] = value;
  lastValid = false;   // downloads stay off until the stats for this exact model arrive
  setDownloads(false);
  if (name === "refill") applyPreset();
  syncControls();
  writeUrl();
  scheduleUpdate();
}

function setColor(hex) {
  model.color = hex;
  controls.color.set(hex);
  applyColor();
  writeUrl();
}

// ---------- fetching ----------

function scheduleUpdate() {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(update, DEBOUNCE_MS);
}

async function update() {
  const id = ++reqSeq;
  const qs = buildQuery();
  qs.delete("color");
  const query = qs.toString();
  setBusy(true);
  try {
    const stats = await fetch(`/api/stats?${query}`).then((r) => r.json());
    if (id !== reqSeq) return;
    renderStats(stats);
    if (!stats.valid) return;
    const [a, b] = await Promise.all(["a", "b"].map((h) =>
      fetch(`/api/half/${h}.stl?${query}`).then((r) => {
        if (!r.ok) throw new Error(`half ${h}: HTTP ${r.status}`);
        return r.arrayBuffer();
      })));
    if (id !== reqSeq) return;
    showMeshes(a, b, stats.overall_width);
    $("viewer-msg").hidden = true;
  } catch (err) {
    if (id !== reqSeq) return;
    console.error(err);
    const msg = $("viewer-msg");
    msg.textContent = "Couldn’t reach the server — check that spoolmaker is still running.";
    msg.hidden = false;
  } finally {
    if (id === reqSeq) setBusy(false);
  }
}

function setBusy(on) { $("busy").hidden = !on; }

function fmtG(v) { return `${v.toFixed(1)} g`; }

function renderStats(s) {
  lastValid = s.valid;
  const errBox = $("errors");
  if (s.valid) {
    errBox.hidden = true;
    errBox.replaceChildren();
    $("st-a").textContent = fmtG(s.weight_g.a);
    $("st-b").textContent = fmtG(s.weight_g.b);
    $("st-total").textContent = fmtG(s.weight_g.total);
    $("st-width").textContent = `${s.overall_width.toFixed(1)} mm`;
    const notes = [s.weight_note, s.bed_note].filter(Boolean);
    $("notes").textContent = notes.join(" · ");
  } else {
    const list = el("ul");
    for (const e of s.errors) list.append(el("li", { text: e }));
    errBox.replaceChildren(el("strong", { text: "This spool can’t be built yet" }), list);
    errBox.hidden = false;
    $("notes").textContent = "Preview shows the last valid design.";
  }
  $("stats").classList.toggle("is-stale", !s.valid);
  setDownloads(s.valid);
  setDimmed(!s.valid);
}

function download(path) {
  if (!lastValid) return;
  const qs = buildQuery();
  qs.delete("color");
  qs.set("download", "1");
  const a = el("a", { href: `${path}?${qs}`, download: "" });
  document.body.append(a);
  a.click();
  a.remove();
}

async function copyShare() {
  const status = $("share-status");
  try {
    await navigator.clipboard.writeText(location.href);
    status.textContent = "Link copied.";
  } catch {
    window.prompt("Copy this link:", location.href);
    status.textContent = "";
  }
  setTimeout(() => { status.textContent = ""; }, 2500);
}

// ---------- viewer ----------

const canvas = $("canvas");
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
const scene = new THREE.Scene();
THREE.Object3D.DEFAULT_UP.set(0, 0, 1);
const camera = new THREE.PerspectiveCamera(35, 1, 1, 5000);
camera.up.set(0, 0, 1);
camera.position.set(260, -320, 220);
const orbit = new OrbitControls(camera, canvas);
orbit.enableDamping = true;
orbit.dampingFactor = 0.1;

const darkMq = window.matchMedia("(prefers-color-scheme: dark)");
const hemi = new THREE.HemisphereLight(0xfff4e6, 0x3a2e24, 1.1);
hemi.position.set(0, 0, 1);
scene.add(hemi);
const sun = new THREE.DirectionalLight(0xffffff, 1.6);
sun.position.set(180, -240, 400);
scene.add(sun);
const fill = new THREE.DirectionalLight(0xffe2c4, 0.4);
fill.position.set(-200, 200, 120);
scene.add(fill);

let grid = null;
function buildGrid() {
  if (grid) { scene.remove(grid); grid.geometry.dispose(); grid.material.dispose(); }
  const dark = darkMq.matches;
  grid = new THREE.GridHelper(400, 40, dark ? 0x4a3d31 : 0xb9a88f, dark ? 0x2c241d : 0xd8ccb8);
  grid.rotation.x = Math.PI / 2;  // XY plane, Z up
  grid.material.transparent = true;
  grid.material.opacity = 0.7;
  scene.add(grid);
}
buildGrid();
darkMq.addEventListener("change", buildGrid);

const material = new THREE.MeshStandardMaterial({ color: DEFAULT_COLOR, roughness: 0.55,
  metalness: 0.05 });
const loader = new STLLoader();
const spool = new THREE.Group();
scene.add(spool);
let meshA = null;
let meshB = null;
let overallWidth = 0;

function replaceMesh(old, geometry) {
  if (old) { spool.remove(old); old.geometry.dispose(); }
  const mesh = new THREE.Mesh(geometry, material);
  spool.add(mesh);
  return mesh;
}

function placeB() {
  if (!meshB) return;
  meshB.rotation.set(Math.PI, 0, 0);
  meshB.position.set(0, 0, overallWidth + ($("exploded").checked ? EXPLODE_MM : 0));
}

function showMeshes(bufA, bufB, width) {
  overallWidth = width;
  // Parse both first so a failure can't leave a new A next to an old B.
  const geoA = loader.parse(bufA);
  const geoB = loader.parse(bufB);
  geoA.computeVertexNormals();
  geoB.computeVertexNormals();
  meshA = replaceMesh(meshA, geoA);
  meshB = replaceMesh(meshB, geoB);
  placeB();
  if (!framed) { frame(); framed = true; }
}

function frame() {
  const box = new THREE.Box3().setFromObject(spool);
  const sphere = box.getBoundingSphere(new THREE.Sphere());
  const dist = sphere.radius / Math.sin(THREE.MathUtils.degToRad(camera.fov / 2)) * 1.05;
  const dir = new THREE.Vector3(0.55, -0.75, 0.6).normalize();
  orbit.target.copy(sphere.center);
  camera.position.copy(sphere.center).addScaledVector(dir, dist);
  camera.near = dist / 50;
  camera.far = dist * 20;
  camera.updateProjectionMatrix();
  orbit.update();
}

function setDimmed(dim) {
  material.transparent = dim;
  material.opacity = dim ? 0.3 : 1;
  material.depthWrite = !dim;
  material.needsUpdate = true;
}

function luminance(hex) {
  const n = parseInt(hex.slice(1), 16);
  const ch = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((c) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2];
}

function applyColor() {
  material.color.set(model.color);
  const root = document.documentElement.style;
  root.setProperty("--accent", model.color);
  root.setProperty("--accent-ink", luminance(model.color) > 0.3 ? "#1f1408" : "#ffffff");
}

function resize() {
  const { clientWidth: w, clientHeight: h } = canvas;
  if (canvas.width !== Math.floor(w * renderer.getPixelRatio()) ||
      canvas.height !== Math.floor(h * renderer.getPixelRatio())) {
    renderer.setSize(w, h, false);
    camera.aspect = w / Math.max(h, 1);
    camera.updateProjectionMatrix();
  }
}

function loop() {
  resize();
  orbit.update();
  renderer.render(scene, camera);
  requestAnimationFrame(loop);
}

// ---------- boot ----------

async function boot() {
  $("dl-a").addEventListener("click", () => download("/api/half/a.stl"));
  $("dl-b").addEventListener("click", () => download("/api/half/b.stl"));
  $("dl-3mf").addEventListener("click", () => download("/api/spool.3mf"));
  $("share").addEventListener("click", copyShare);
  $("exploded").addEventListener("change", placeB);
  requestAnimationFrame(loop);

  try {
    schema = await fetch("/api/schema").then((r) => r.json());
  } catch (err) {
    $("controls").replaceChildren(el("p", { class: "loading-note",
      text: "Couldn’t load settings from the server." }));
    return;
  }
  readUrl();
  buildControls();
  syncControls();
  applyColor();
  writeUrl();
  update();
}

boot();
