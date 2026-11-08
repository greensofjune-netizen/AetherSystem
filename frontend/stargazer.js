"use strict";

const canvas = document.getElementById("cosmos");
const ctx = canvas.getContext("2d");
const motionPreference = window.matchMedia("(prefers-reduced-motion: reduce)");
let width = 1, height = 1, panX = 0, panY = 0;
let pointer = null, showLines = true, drift = !motionPreference.matches;
let previousTime = null, frame = null;
let shellVisible = true;
const meteors = [];
const SPECTRAL_COLORS = ["#ffffff", "#cfe4ff", "#ffe9c4", "#ffd2a1", "#9bb0ff"];
const stars = Array.from({ length: 550 }, () => ({
  x: Math.random() * 2400 - 1200, y: Math.random() * 1600 - 800,
  r: Math.random() * 1.8 + 0.3, alpha: Math.random() * 0.8 + 0.2,
  speed: Math.random() * 1.8 + 0.3, phase: Math.random() * Math.PI * 2,
  color: SPECTRAL_COLORS[Math.floor(Math.random() * SPECTRAL_COLORS.length)],
}));
const CONSTELLATIONS = [
  {
    name: "Orion (The Hunter)",
    info: "Betelgeuse is a red supergiant and Rigel is a blue supergiant. The three belt stars sit between Orion's shoulders and feet.",
    points: [
      {x:-120,y:-90,label:"Betelgeuse"}, {x:-40,y:-80,label:"Bellatrix"},
      {x:-75,y:-10,label:"Alnitak"}, {x:-90,y:-5,label:"Alnilam"},
      {x:-105,y:0,label:"Mintaka"}, {x:-130,y:85,label:"Saiph"},
      {x:-35,y:80,label:"Rigel"},
    ],
    links: [[0,1],[0,4],[1,2],[2,3],[3,4],[4,5],[2,6],[5,6]],
  },
  {
    name: "Ursa Major (Big Dipper asterism)",
    info: "The Big Dipper is part of Ursa Major. Extending a line from Merak through Dubhe leads toward Polaris. Visibility depends on latitude and season.",
    points: [
      {x:140,y:-110,label:"Dubhe"}, {x:145,y:-55,label:"Merak"},
      {x:205,y:-45,label:"Phecda"}, {x:210,y:-95,label:"Megrez"},
      {x:265,y:-115,label:"Alioth"}, {x:315,y:-125,label:"Mizar"},
      {x:365,y:-100,label:"Alkaid"},
    ],
    links: [[0,1],[1,2],[2,3],[3,0],[3,4],[4,5],[5,6]],
  },
  {
    name: "Cassiopeia (The Queen)",
    info: "Cassiopeia's five notable stars form a W-shaped asterism in the northern sky. This diagram is illustrative, not an observing chart.",
    points: [
      {x:-320,y:-160,label:"Caph"}, {x:-285,y:-115,label:"Schedar"},
      {x:-245,y:-145,label:"Navi"}, {x:-205,y:-105,label:"Ruchbah"},
      {x:-170,y:-140,label:"Segin"},
    ],
    links: [[0,1],[1,2],[2,3],[3,4]],
  },
];

function updateToggle(id, enabled, label) {
  const button = document.getElementById(id);
  button.textContent = `${label}: ${enabled ? "ON" : "OFF"}`;
  button.classList.toggle("active", enabled);
  button.setAttribute("aria-pressed", String(enabled));
}

function selectStar(c, p) {
  document.getElementById("constellation-info").textContent = `${p.label} - ${c.name}. ${c.info}`;
}

const guide = document.getElementById("star-guide");
CONSTELLATIONS.forEach((c, ci) => c.points.forEach((p, pi) => {
  const option = document.createElement("option");
  option.value = `${ci}:${pi}`;
  option.textContent = `${p.label} - ${c.name}`;
  guide.append(option);
}));
guide.addEventListener("change", () => {
  if (!guide.value) return;
  const [ci, pi] = guide.value.split(":").map(Number);
  const c = CONSTELLATIONS[ci], p = c.points[pi];
  selectStar(c, p);
  panX = -p.x;
  panY = -p.y;
  requestRender();
});

function resize() {
  width = Math.max(1, window.innerWidth);
  height = Math.max(1, window.innerHeight);
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.round(width * ratio);
  canvas.height = Math.round(height * ratio);
  if (ctx) ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  requestRender();
}

function draw(time) {
  frame = null;
  if (!ctx || document.hidden || !shellVisible) return;
  const elapsed = previousTime === null ? 0 : Math.min((time - previousTime) / 1000, 0.05);
  previousTime = time;
  ctx.fillStyle = "#05070e";
  ctx.fillRect(0, 0, width, height);
  const glow = ctx.createLinearGradient(0, 0, width, height);
  glow.addColorStop(0, "rgba(25,45,95,0.14)");
  glow.addColorStop(0.5, "rgba(110,60,140,0.08)");
  glow.addColorStop(1, "rgba(10,20,45,0.15)");
  ctx.fillStyle = glow;
  ctx.fillRect(0, 0, width, height);
  if (drift && !pointer) panX -= 3 * elapsed;
  const cx = width / 2 + panX, cy = height / 2 + panY;
  for (const s of stars) {
    if (!motionPreference.matches) s.phase += s.speed * elapsed;
    ctx.globalAlpha = s.alpha * (0.65 + 0.35 * Math.sin(s.phase));
    ctx.fillStyle = s.color;
    ctx.beginPath();
    ctx.arc(((s.x+cx)%width+width)%width, ((s.y+cy)%height+height)%height, s.r, 0, Math.PI*2);
    ctx.fill();
  }
  ctx.globalAlpha = 1;
  for (const c of CONSTELLATIONS) {
    if (showLines) {
      ctx.strokeStyle = "rgba(125,211,252,0.4)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      for (const [a,b] of c.links) {
        ctx.moveTo(cx+c.points[a].x, cy+c.points[a].y);
        ctx.lineTo(cx+c.points[b].x, cy+c.points[b].y);
      }
      ctx.stroke();
    }
    for (const p of c.points) {
      ctx.fillStyle = p.label === "Betelgeuse" ? "#ffd2a1" : "#7dd3fc";
      ctx.beginPath();
      ctx.arc(cx+p.x, cy+p.y, 3.5, 0, Math.PI*2);
      ctx.fill();
    }
  }
  for (let i = meteors.length-1; i>=0; i--) {
    const m = meteors[i];
    m.x += m.vx * elapsed;
    m.y += m.vy * elapsed;
    m.life -= elapsed;
    if (m.life <= 0) { meteors.splice(i,1); continue; }
    ctx.strokeStyle = `rgba(220,240,255,${m.life})`;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(m.x-m.vx*0.12, m.y-m.vy*0.12);
    ctx.lineTo(m.x,m.y);
    ctx.stroke();
  }
  if (!motionPreference.matches || drift || meteors.length) requestRender();
}

function requestRender() {
  if (ctx && frame === null && !document.hidden && shellVisible) frame = requestAnimationFrame(draw);
}

canvas.addEventListener("pointerdown", (event) => {
  if (pointer || !event.isPrimary || event.button !== 0) return;
  canvas.focus({preventScroll:true});
  canvas.setPointerCapture(event.pointerId);
  pointer = {id:event.pointerId, x:event.clientX, y:event.clientY, moved:0};
});
canvas.addEventListener("pointermove", (event) => {
  if (!pointer || pointer.id !== event.pointerId) return;
  const dx = event.clientX-pointer.x, dy = event.clientY-pointer.y;
  panX += dx; panY += dy;
  pointer.moved += Math.hypot(dx,dy);
  pointer.x = event.clientX; pointer.y = event.clientY;
  requestRender();
});
canvas.addEventListener("pointerup", (event) => {
  if (!pointer || pointer.id !== event.pointerId) return;
  if (pointer.moved < 6) {
    let closest = null, distance = 18;
    CONSTELLATIONS.forEach((c,ci) => c.points.forEach((p,pi) => {
      const d = Math.hypot(event.clientX-(width/2+panX+p.x), event.clientY-(height/2+panY+p.y));
      if (d < distance) { distance = d; closest = {c,p,ci,pi}; }
    }));
    if (closest) {
      selectStar(closest.c, closest.p);
      guide.value = `${closest.ci}:${closest.pi}`;
    }
  }
  pointer = null;
});
canvas.addEventListener("lostpointercapture", () => { pointer = null; });
canvas.addEventListener("keydown", (event) => {
  const offsets = {ArrowLeft:[30,0], ArrowRight:[-30,0], ArrowUp:[0,30], ArrowDown:[0,-30]};
  if (!offsets[event.key]) return;
  event.preventDefault();
  const [dx,dy] = offsets[event.key];
  panX += dx; panY += dy;
  requestRender();
});
document.getElementById("toggle-lines").addEventListener("click", () => {
  showLines = !showLines;
  updateToggle("toggle-lines", showLines, "Constellation Lines");
  requestRender();
});
document.getElementById("toggle-drift").addEventListener("click", () => {
  drift = !drift;
  updateToggle("toggle-drift", drift, "Visual Drift");
  requestRender();
});
document.getElementById("trigger-meteor").addEventListener("click", () => {
  if (meteors.length >= 20) return;
  meteors.push({x:Math.random()*width,y:Math.random()*height*0.4,vx:-600,vy:420,life:1});
  requestRender();
});
document.getElementById("reset-view").addEventListener("click", () => {
  panX = 0; panY = 0;
  requestRender();
});
motionPreference.addEventListener("change", () => {
  drift = !motionPreference.matches;
  updateToggle("toggle-drift", drift, "Visual Drift");
  requestRender();
});
document.addEventListener("visibilitychange", () => {
  if (frame !== null) cancelAnimationFrame(frame);
  frame = null; previousTime = null;
  requestRender();
});
window.addEventListener("message", (event) => {
  if (event.origin !== window.location.origin || event.source !== window.parent ||
      event.data?.type !== "cosmic-shell-visibility" ||
      typeof event.data.visible !== "boolean") return;
  shellVisible = event.data.visible;
  if (frame !== null) cancelAnimationFrame(frame);
  frame = null; previousTime = null; pointer = null;
  requestRender();
});
window.addEventListener("resize", resize);
function updateClock() {
  document.getElementById("utc-clock").textContent = `UTC: ${new Date().toISOString().slice(11,19)}`;
}
if (!ctx) {
  document.getElementById("sky-status").textContent = "CANVAS UNAVAILABLE";
  document.getElementById("constellation-info").textContent = "Canvas rendering is unavailable. Use the star guide to explore descriptions.";
  console.error("Stargazer: browser could not create a 2D canvas context.");
}
updateToggle("toggle-drift", drift, "Visual Drift");
updateClock();
setInterval(updateClock, 1000);
resize();

const commsElement = (id) => document.getElementById(id);
let clockReference = null;
let clockSample = 0;
let commsBusy = false;

async function commsJson(path, options = {}) {
  const response = await fetch(path, {
    ...options, signal: AbortSignal.timeout(options.method === "POST" ? 135000 : 10000),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : `Backend HTTP ${response.status}`);
  return data;
}

function appendComms(sender, text, stamp) {
  const entry = document.createElement("div");
  const heading = document.createElement("div");
  heading.className = "metric-label";
  heading.textContent = `[${stamp}] ${sender}`;
  const message = document.createElement("div");
  message.textContent = text;
  entry.append(heading, message);
  const log = commsElement("comms-log");
  log.append(entry);
  while (log.children.length > 100) log.firstElementChild.remove();
  log.scrollTop = log.scrollHeight;
}

async function refreshComms() {
  try {
    const clock = await commsJson("/api/clock");
    const reference = Date.parse(clock.utc);
    if (!Number.isFinite(reference)) throw new Error("Invalid backend clock response.");
    clockReference = reference;
    clockSample = performance.now();
    const config = await commsJson("/api/chat/status");
    if (!config.enabled) throw new Error("Local AI is disabled. Start historian_matrix.py with an approved --ollama-model.");
    commsElement("comms-status").textContent = `Configured local model: ${config.model}. Availability is checked when you send.`;
    commsElement("comms-send").disabled = commsBusy;
    if (!commsBusy) commsElement("comms-error").hidden = true;
  } catch (error) {
    clockReference = null;
    commsElement("comms-utc").textContent = "Backend UTC unavailable";
    commsElement("comms-status").textContent = "Comms unavailable; use the independent Copernicus Matrix shell.";
    commsElement("comms-send").disabled = true;
    commsElement("comms-error").textContent = error.message;
    commsElement("comms-error").hidden = false;
    console.error("Stargazer comms configuration failed:", error);
  }
}

setInterval(() => {
  if (clockReference !== null) {
    commsElement("comms-utc").textContent =
      `Backend UTC ~${new Date(clockReference + performance.now() - clockSample).toISOString().slice(11,19)}`;
  }
}, 1000);

commsElement("comms-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (commsBusy) return;
  const input = commsElement("comms-input");
  const message = input.value.trim();
  if (!message) {
    commsElement("comms-error").textContent = "Enter a message.";
    commsElement("comms-error").hidden = false;
    return;
  }
  commsBusy = true;
  input.disabled = true;
  commsElement("comms-send").disabled = true;
  commsElement("comms-error").hidden = true;
  commsElement("comms-status").textContent = "Awaiting Copernicus...";
  try {
    const data = await commsJson("/api/chat", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({message}),
    });
    if (typeof data.response !== "string" || !data.response.trim() ||
        !Number.isFinite(Date.parse(data.request_utc)) ||
        !Number.isFinite(Date.parse(data.response_utc))) {
      throw new Error("Invalid backend communication response.");
    }
    appendComms("SHELL", message, data.request_utc);
    appendComms("COPERNICUS", data.response, data.response_utc);
    input.value = "";
    commsElement("comms-status").textContent = "Reply received. Chat is not saved; UTC stamps are assigned by the backend.";
  } catch (error) {
    commsElement("comms-status").textContent = "Message failed; retained for retry.";
    commsElement("comms-error").textContent = error.message;
    commsElement("comms-error").hidden = false;
    console.error("Stargazer comms request failed:", error);
  } finally {
    commsBusy = false;
    input.disabled = false;
    commsElement("comms-send").disabled = false;
  }
});
refreshComms();
setInterval(refreshComms, 60000);
