const NEUTRAL_CARDS = new Set([
  "I'm learning",
  "Inspect",
  "Digital Forensics",
  "Tell me more",
  "I'm out",
  "Show me what you got",
  "All in",
]);

async function postJSON(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify(body ?? {}),
  });
  const data = await res.json();
  if (!res.ok) {
    data.ok = false;
  }
  return data;
}

async function getJSON(url) {
  const res = await fetch(url, { credentials: "same-origin" });
  const data = await res.json();
  if (!res.ok) {
    data.ok = false;
  }
  return data;
}

function el(tag, attrs = {}, children = []) {
  const n = document.createElement(tag);
  Object.entries(attrs).forEach(([k, v]) => {
    if (k === "class") n.className = v;
    else if (k.startsWith("on") && typeof v === "function") n.addEventListener(k.slice(2), v);
    else if (v === false) return;
    else n.setAttribute(k, v);
  });
  for (const c of children) {
    if (typeof c === "string") n.appendChild(document.createTextNode(c));
    else if (c) n.appendChild(c);
  }
  return n;
}

function showLobbyError(msg) {
  const box = document.getElementById("lobby-error");
  box.textContent = msg;
  box.hidden = !msg;
}

function phaseLabel(phase) {
  const map = {
    day_draw: "Day — draw",
    day_inspect: "Day — Inspect resolution",
    day_neutral: "Day — neutral cards",
    day_discussion: "Day — discussion",
    day_vote: "Day — vote",
    night_black: "Night — Black hat",
    night_white: "Night — White hat defense",
    night_gray: "Night — Gray hat",
    game_over: "Game over",
  };
  return map[phase] || phase;
}

function renderHand(hand) {
  const ul = document.getElementById("g-hand");
  ul.innerHTML = "";
  (hand || []).forEach((c) => ul.appendChild(el("li", { class: "mono" }, [c])));
}

function renderVulns(rows) {
  const tb = document.querySelector("#g-vulns tbody");
  tb.innerHTML = "";
  rows.forEach((v) => {
    tb.appendChild(
      el("tr", {}, [
        el("td", {}, [String(v.id)]),
        el("td", { class: "mono" }, [v.kind]),
        el("td", {}, [v.status]),
      ])
    );
  });
}

function renderPlayers(players, you) {
  const ul = document.getElementById("g-players");
  ul.innerHTML = "";
  players.forEach((p) => {
    const roleText = p.pid === you ? p.role : "hidden";
    const cardsText = p.pid === you ? `${(p.hand || []).length} cards` : `${p.hand_count ?? "?"} cards`;
    const label =
      p.pid === you ? `${p.name} (you) — ${roleText} · ${cardsText}` : `${p.name} — ${roleText} · ${cardsText}`;
    ul.appendChild(el("li", {}, [p.eliminated ? `${label} · eliminated` : label]));
  });
}

function renderLog(lines) {
  const ol = document.getElementById("g-log");
  ol.innerHTML = "";
  (lines || []).forEach((ln) => ol.appendChild(el("li", {}, [ln])));
}

function renderActions(s) {
  const root = document.getElementById("actions-root");
  root.innerHTML = "";
  const you = s.you;

  const push = (nodes) => nodes.forEach((n) => root.appendChild(n));

  if (s.winner) {
    push([
      el("div", { class: "block" }, [
        el("p", {}, ["The match ended. Start a new game when you are ready."]),
      ]),
    ]);
    return;
  }

  const nd = (s.needs_discard || []).find((x) => x.pid === you);
  if (nd) {
    const picked = new Set();
    const box = el("div", { class: "block" });
    box.appendChild(el("p", {}, [`Discard ${nd.amount} card(s) from your hand (select by index).`]));
    const hand = s.players[you].hand || [];
    const list = el("div", { class: "mono" });
    hand.forEach((c, i) => {
      const row = el("label", {}, [
        el("input", { type: "checkbox", name: "di", value: String(i) }),
        document.createTextNode(` [${i}] ${c}`),
      ]);
      row.querySelector("input").addEventListener("change", (e) => {
        const idx = Number(e.target.value);
        if (e.target.checked) picked.add(idx);
        else picked.delete(idx);
      });
      list.appendChild(row);
      list.appendChild(el("br"));
    });
    box.appendChild(list);
    box.appendChild(
      el(
        "button",
        {},
        [
          "Confirm discard",
        ]
      )
    );
    box.querySelector("button").addEventListener("click", async () => {
      if (picked.size !== nd.amount) {
        alert(`Pick exactly ${nd.amount} cards.`);
        return;
      }
      const indices = Array.from(picked).sort((a, b) => b - a);
      await send({ type: "discard_down", indices });
    });
    push([box]);
    return;
  }

  if (s.company_must_choose_inspector && s.players[you].role === "company") {
    const box = el("div", { class: "block" });
    box.appendChild(el("p", {}, ["Choose which player with Inspect may inspect a vulnerability."]));
    const sel = el("select", { id: "pick-inspector" });
    (s.inspect_candidates || []).forEach((pid) => {
      const name = s.players[pid].name;
      sel.appendChild(el("option", { value: String(pid) }, [`${name} (#${pid})`]));
    });
    box.appendChild(sel);
    const btn = el("button", {}, ["Confirm"]);
    btn.addEventListener("click", async () => {
      await send({
        type: "company_pick_inspector",
        target_pid: Number(sel.value),
      });
    });
    box.appendChild(btn);
    push([box]);
    return;
  }

  if (s.phase === "day_neutral" && s.neutral_turn === you) {
    const hand = s.players[you].hand || [];
    const neutrals = hand.filter((c) => NEUTRAL_CARDS.has(c));
    const box = el("div", { class: "block" });
    box.appendChild(el("p", {}, ["Your neutral phase — play one neutral card or pass."]));
    if (neutrals.length) {
      const sel = el("select", { id: "neutral-card" });
      neutrals.forEach((c) => sel.appendChild(el("option", {}, [c])));
      box.appendChild(sel);
      let target = null;
      if (neutrals.includes("Show me what you got")) {
        const tsel = el("select", { id: "neutral-target" });
        s.players.forEach((p) => {
          if (p.pid !== you && !p.eliminated) {
            tsel.appendChild(el("option", { value: String(p.pid) }, [`${p.name} (#${p.pid})`]));
          }
        });
        box.appendChild(el("p", {}, ["Target (for Show me what you got):"]));
        box.appendChild(tsel);
        target = tsel;
      }
      const playBtn = el("button", { type: "button" }, ["Play neutral"]);
      playBtn.addEventListener("click", async () => {
        const card = sel.value;
        const payload = { type: "neutral_play", card };
        if (card === "Show me what you got" && target) {
          payload.target_pid = Number(target.value);
        }
        await send(payload);
      });
      box.appendChild(playBtn);
    }
    const passBtn = el("button", { type: "button", class: "secondary" }, ["Pass"]);
    passBtn.addEventListener("click", async () => {
      await send({ type: "neutral_pass" });
    });
    box.appendChild(passBtn);
    push([box]);
    return;
  }

  if (s.phase === "day_discussion") {
    const box = el("div", { class: "block" });
    box.appendChild(el("p", {}, ["Discussion — end the day when you are ready."]));
    if (s.company_may_forensics && s.players[you].role === "company") {
      box.appendChild(
        el("button", {}, [
          "Use Digital Forensics (wrong attack tracked)",
        ])
      );
      box.querySelector("button").addEventListener("click", async () => {
        await send({ type: "forensics" });
      });
    }
    box.appendChild(
      el("button", { class: "secondary" }, [
        "End day (go to night)",
      ])
    );
    box.querySelector("button.secondary").addEventListener("click", async () => {
      await send({ type: "end_discussion" });
    });

    const vbox = el("div", { class: "block" });
    vbox.appendChild(el("p", {}, ["Start elimination vote against a player:"]));
    const vsel = el("select", { id: "vote-start" });
    s.players.forEach((p) => {
      if (!p.eliminated && p.pid !== you) {
        vsel.appendChild(el("option", { value: String(p.pid) }, [`${p.name} (#${p.pid})`]));
      }
    });
    vbox.appendChild(vsel);
    vbox.appendChild(
      el("button", {}, [
        "Start vote",
      ])
    );
    vbox.querySelector("button").addEventListener("click", async () => {
      await send({ type: "start_vote", target_pid: Number(vsel.value) });
    });
    push([box, vbox]);
    return;
  }

  if (s.phase === "day_vote" && s.vote_active) {
    const box = el("div", { class: "block" });
    box.appendChild(el("p", {}, ["Cast your vote (majority eliminates)."]));
    const vsel = el("select", { id: "vote-for" });
    s.players.forEach((p) => {
      if (!p.eliminated) vsel.appendChild(el("option", { value: String(p.pid) }, [`${p.name} (#${p.pid})`]));
    });
    box.appendChild(vsel);
    box.appendChild(
      el("button", {}, [
        "Submit vote",
      ])
    );
    box.querySelector("button").addEventListener("click", async () => {
      await send({ type: "vote", target_pid: Number(vsel.value) });
    });
    push([box]);
    return;
  }

  if (s.phase === "night_black" && s.night_black_actor === you) {
    const box = el("div", { class: "block" });
    box.appendChild(el("p", {}, ["Black hat night — inspect a vulnerability, attack, or pass."]));
    const hand = s.players[you].hand || [];
    const inspectBtn = el("button", { type: "button" }, ["Inspect (uses Inspect card)"]);
    inspectBtn.addEventListener("click", async () => {
      await send({ type: "night_black", mode: "inspect" });
    });
    box.appendChild(inspectBtn);
    const vulnSel = el("select", { id: "atk-vuln" });
    s.vulnerabilities.forEach((v) => {
      vulnSel.appendChild(el("option", { value: String(v.id) }, [`#${v.id} (${v.kind})`]));
    });
    const cardSel = el("select", { id: "atk-card" });
    hand
      .filter((c) => c && !NEUTRAL_CARDS.has(c))
      .forEach((c) => cardSel.appendChild(el("option", {}, [c])));
    box.appendChild(el("p", {}, ["Attack:"]));
    box.appendChild(vulnSel);
    box.appendChild(cardSel);
    const atkBtn = el("button", { type: "button", class: "secondary" }, ["Launch attack"]);
    atkBtn.addEventListener("click", async () => {
      await send({
        type: "night_black",
        mode: "attack",
        vuln_id: Number(vulnSel.value),
        card: cardSel.value,
      });
    });
    box.appendChild(atkBtn);
    const passBtn = el("button", { type: "button", class: "secondary" }, ["Pass"]);
    passBtn.addEventListener("click", async () => {
      await send({ type: "night_black", mode: "pass" });
    });
    box.appendChild(passBtn);
    push([box]);
    return;
  }

  if (s.phase === "night_white" && s.pending_defense_player === you) {
    const pa = s.pending_attack;
    const box = el("div", { class: "block" });
    box.appendChild(
      el("p", {}, [
        `Defend against attack on vulnerability #${pa?.target_vuln_id ?? "?"}.`,
      ])
    );
    const hand = s.players[you].hand || [];
    const defSel = el("select", { id: "def-card" });
    hand.forEach((c) => defSel.appendChild(el("option", {}, [c])));
    box.appendChild(defSel);
    box.appendChild(
      el("button", {}, [
        "Play defense card",
      ])
    );
    box.querySelector("button").addEventListener("click", async () => {
      await send({ type: "night_white", card: defSel.value });
    });
    box.appendChild(
      el("button", { class: "secondary" }, [
        "Pass (attack succeeds)",
      ])
    );
    box.querySelector("button.secondary").addEventListener("click", async () => {
      await send({ type: "night_white", pass: true });
    });
    push([box]);
    return;
  }

  if (s.phase === "night_gray" && s.players[you].role === "gray_hat") {
    const box = el("div", { class: "block" });
    box.appendChild(el("p", {}, ["Gray hat — resolve, exploit, or pass."]));
    const hand = s.players[you].hand || [];
    const vsel = el("select", { id: "g-vuln" });
    s.vulnerabilities.forEach((v) => {
      vsel.appendChild(el("option", { value: String(v.id) }, [`#${v.id} (${v.kind})`]));
    });
    const csel = el("select", { id: "g-card" });
    hand.forEach((c) => csel.appendChild(el("option", {}, [c])));
    box.appendChild(vsel);
    box.appendChild(csel);
    const resBtn = el("button", { type: "button" }, ["Resolve (defensive card)"]);
    resBtn.addEventListener("click", async () => {
      await send({
        type: "night_gray",
        mode: "resolve",
        vuln_id: Number(vsel.value),
        card: csel.value,
      });
    });
    box.appendChild(resBtn);
    const expBtn = el("button", { type: "button", class: "secondary" }, ["Exploit (offensive card)"]);
    expBtn.addEventListener("click", async () => {
      await send({
        type: "night_gray",
        mode: "exploit",
        vuln_id: Number(vsel.value),
        card: csel.value,
      });
    });
    box.appendChild(expBtn);
    const passBtn = el("button", { type: "button", class: "secondary" }, ["Pass"]);
    passBtn.addEventListener("click", async () => {
      await send({ type: "night_gray", mode: "pass" });
    });
    box.appendChild(passBtn);
    push([box]);
    return;
  }

  push([
    el("div", { class: "block" }, [
      el("p", {}, ["Waiting on bots or phase transition — use Refresh if the UI looks stale."]),
    ]),
  ]);
}

async function send(payload) {
  const data = await postJSON("/api/game/action", payload);
  if (data.ok === false && data.error) {
    alert(data.error || "Action failed");
  }
  applyState(data);
}

function applyState(s) {
  if (!s || s.ok === false) {
    showLobbyError(s?.error || "Request failed");
    return;
  }
  document.getElementById("lobby").classList.add("hidden");
  document.getElementById("game").classList.remove("hidden");

  document.getElementById("g-round").textContent = String(s.round);
  document.getElementById("g-phase").textContent = phaseLabel(s.phase);
  document.getElementById("g-role").textContent = s.players[s.you].role;
  const win = document.getElementById("g-winner");
  if (s.winner) {
    win.textContent = `Winner: ${s.winner}`;
    win.classList.remove("hidden");
  } else {
    win.classList.add("hidden");
  }

  renderHand(s.players[s.you].hand);
  renderVulns(s.vulnerabilities || []);
  renderPlayers(s.players, s.you);
  renderLog(s.log);
  renderActions(s);
}

async function startGame() {
  showLobbyError("");
  const name = document.getElementById("player-name").value.trim() || "You";
  const player_count = Number(document.getElementById("player-count").value);
  try {
    const data = await postJSON("/api/game/new", { name, player_count });
    applyState(data);
  } catch (e) {
    showLobbyError("Could not start a game (network error).");
  }
}

async function refresh() {
  try {
    const data = await getJSON("/api/game/state");
    applyState(data);
  } catch (e) {
    showLobbyError("Could not load state.");
  }
}

function wire() {
  document.getElementById("btn-new-game").addEventListener("click", startGame);
  document.getElementById("btn-refresh").addEventListener("click", refresh);
  document.getElementById("btn-restart").addEventListener("click", startGame);
}

wire();
