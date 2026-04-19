/* ─────────────────────────────────────────────────────────────────────────
   LangChat – app.js
   Conecta o frontend ao backend FastAPI.
───────────────────────────────────────────────────────────────────────── */

const API = '';   // mesmo origin

// ── State ────────────────────────────────────────────────────────────────────
let running     = false;
let ttsEnabled  = true;    // leitura em voz alta da resposta (ativo por padrão)
let recognition = null;    // instância SpeechRecognition

// ── DOM refs ─────────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const promptInput   = $('promptInput');
const runBtn        = $('runBtn');
const btnSpinner    = $('btnSpinner');
const btnText       = runBtn.querySelector('.btn-text');
const resultCard    = $('resultCard');
const resultBody    = $('resultBody');
const resultMetrics = $('resultMetrics');
const errorCard     = $('errorCard');
const errorBody     = $('errorBody');
const tablesList    = $('tablesList');
const runsList      = $('runsList');
const tempSlider    = $('tempSlider');
const tempValue     = $('tempValue');
const charCounter   = $('charCounter');
const headerBadges  = $('headerBadges');
const tablePreviewCard  = $('tablePreviewCard');
const tablePreviewTitle = $('tablePreviewTitle');
const tablePreviewBody  = $('tablePreviewBody');
const modalOverlay  = $('modalOverlay');
const modalTitle    = $('modalTitle');
const modalBody     = $('modalBody');
// Voice
const micBtn           = $('micBtn');
const ttsToggleBtn     = $('ttsToggleBtn');
const ttsIcon          = $('ttsIcon');
const jarvisOverlay    = $('jarvisOverlay');
const jarvisStatus     = $('jarvisStatus');
const jarvisTranscript = $('jarvisTranscript');
const jarvisStopBtn    = $('jarvisStopBtn');

// ── Helpers ───────────────────────────────────────────────────────────────────
async function api(path, opts = {}) {
  const res = await fetch(API + path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

function dbUrl() {
  return $('dbUrl').value.trim();
}

function renderTable(rows) {
  if (!rows || rows.length === 0) return '<p style="color:var(--text-dim);font-size:13px">Sem dados.</p>';
  const cols = Object.keys(rows[0]);
  const head = cols.map(c => `<th>${c}</th>`).join('');
  const body = rows.map(r =>
    `<tr>${cols.map(c => `<td>${r[c] ?? ''}</td>`).join('')}</tr>`
  ).join('');
  return `<table class="data-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

// ── Init: healthcheck + config ────────────────────────────────────────────────
async function loadConfig() {
  try {
    const cfg = await api('/api/config');
    const badges = [];

    if (cfg.openai_configured) {
      badges.push(`<div class="badge badge-ok">OpenAI ✓</div>`);
    } else {
      badges.push(`<div class="badge badge-error">OpenAI ✗</div>`);
    }
    if (cfg.langsmith_configured) {
      badges.push(`<div class="badge badge-ok">LangSmith ✓</div>`);
    } else {
      badges.push(`<div class="badge badge-warn">LangSmith não configurado</div>`);
    }
    badges.push(`<div class="badge" style="border-color:var(--border);color:var(--text-muted)">${cfg.model}</div>`);
    badges.push(`<div class="badge" style="border-color:var(--border);color:var(--text-muted)">🗄 ${cfg.default_db}</div>`);

    headerBadges.innerHTML = badges.join('');

    // selecionar o model no select
    const sel = $('modelSelect');
    if ([...sel.options].some(o => o.value === cfg.model)) {
      sel.value = cfg.model;
    }
  } catch {
    headerBadges.innerHTML = `<div class="badge badge-error">Backend offline</div>`;
  }
}

// ── Tables ────────────────────────────────────────────────────────────────────
async function loadTables() {
  tablesList.innerHTML = `
    <div class="skeleton-row"></div>
    <div class="skeleton-row"></div>
    <div class="skeleton-row"></div>`;
  try {
    const url = dbUrl();
    const data = await api('/api/tables' + (url ? `?db_url=${encodeURIComponent(url)}` : ''));
    if (!data.tables.length) {
      tablesList.innerHTML = `<p class="runs-empty">Nenhuma tabela encontrada.</p>`;
      return;
    }
    tablesList.innerHTML = data.tables.map(t => `
      <button class="table-chip" data-table="${t}">
        <span class="table-chip-icon">▣</span>
        ${t}
      </button>
    `).join('');

    tablesList.querySelectorAll('.table-chip').forEach(btn => {
      btn.addEventListener('click', () => previewTable(btn.dataset.table));
    });
  } catch (e) {
    tablesList.innerHTML = `<p class="runs-empty" style="color:var(--red)">${e.message}</p>`;
  }
}

async function previewTable(table) {
  const url = dbUrl();
  tablePreviewCard.style.display = 'block';
  tablePreviewTitle.textContent = `Prévia – ${table}`;
  tablePreviewBody.innerHTML = `<div class="skeleton-row" style="height:80px"></div>`;
  try {
    const data = await api(
      `/api/sample/${table}` + (url ? `?db_url=${encodeURIComponent(url)}` : '')
    );
    tablePreviewBody.innerHTML = renderTable(data.rows);
  } catch (e) {
    tablePreviewBody.innerHTML = `<p style="color:var(--red);font-size:13px">${e.message}</p>`;
  }
  tablePreviewCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

$('closePreviewBtn').addEventListener('click', () => {
  tablePreviewCard.style.display = 'none';
});

$('refreshTablesBtn').addEventListener('click', loadTables);

// ── Runs ──────────────────────────────────────────────────────────────────────
async function loadRuns() {
  runsList.innerHTML = `
    <div class="skeleton-row"></div>
    <div class="skeleton-row"></div>
    <div class="skeleton-row"></div>`;
  try {
    const data = await api('/api/runs');
    if (!data.runs.length) {
      runsList.innerHTML = `<p class="runs-empty">Nenhum run encontrado.<br>Execute um prompt para começar.</p>`;
      return;
    }
    // Check for error-only response
    if (data.runs[0]?.error && data.runs.length === 1 && !data.runs[0]?.id) {
      runsList.innerHTML = `<p class="runs-empty" style="color:var(--text-dim)">LangSmith não configurado ou sem runs.</p>`;
      return;
    }
    runsList.innerHTML = data.runs.map(r => {
      const statusClass = r.error ? 'error' : (r.status === 'success' ? 'success' : 'pending');
      const statusLabel = r.error ? 'erro' : (r.status || '?');
      const time = r.start_time ? new Date(r.start_time).toLocaleTimeString('pt-BR') : '–';
      const tokens = r.total_tokens ? `${r.total_tokens} tokens` : '';
      return `
        <div class="run-item">
          <div class="run-name" title="${r.name}">${r.name}</div>
          <div class="run-meta">
            <span class="run-badge ${statusClass}">${statusLabel}</span>
            <span class="run-badge dim">${time}</span>
            ${tokens ? `<span class="run-badge dim">${tokens}</span>` : ''}
          </div>
        </div>`;
    }).join('');
  } catch (e) {
    runsList.innerHTML = `<p class="runs-empty" style="color:var(--text-dim)">LangSmith não configurado.</p>`;
  }
}

$('refreshRunsBtn').addEventListener('click', loadRuns);

// ── Temperature slider ────────────────────────────────────────────────────────
tempSlider.addEventListener('input', () => {
  tempValue.textContent = parseFloat(tempSlider.value).toFixed(1);
});

// ── Char counter ──────────────────────────────────────────────────────────────
promptInput.addEventListener('input', () => {
  charCounter.textContent = `${promptInput.value.length} chars`;
});

// ── Quick prompts ─────────────────────────────────────────────────────────────
$('quickPrompts').addEventListener('click', e => {
  const btn = e.target.closest('.quick-btn');
  if (!btn) return;
  promptInput.value = btn.textContent.trim();
  charCounter.textContent = `${promptInput.value.length} chars`;
  promptInput.focus();
});

// ── Voice: JARVIS Mode ────────────────────────────────────────────────────────
const SpeechRecognitionAPI = window.SpeechRecognition || window.webkitSpeechRecognition;

function initRecognition() {
  if (!SpeechRecognitionAPI) {
    micBtn.title  = 'Reconhecimento de voz não suportado (use Chrome/Edge)';
    micBtn.style.opacity = '0.4';
    micBtn.style.cursor  = 'not-allowed';
    return null;
  }
  const rec = new SpeechRecognitionAPI();
  rec.lang            = 'pt-BR';
  rec.interimResults  = true;   // resultado parcial em tempo real
  rec.continuous      = false;  // para automaticamente após silêncio
  rec.maxAlternatives = 1;

  rec.onstart = () => {
    jarvisOverlay.classList.remove('hidden');
    micBtn.classList.add('mic-active');
    jarvisStatus.textContent    = 'OUVINDO...';
    jarvisTranscript.textContent = '';
  };

  rec.onresult = (event) => {
    let interim = '', final = '';
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const t = event.results[i][0].transcript;
      if (event.results[i].isFinal) final += t;
      else interim += t;
    }
    const display = final || interim;
    jarvisTranscript.textContent = display;
    if (final) {
      promptInput.value = final.trim();
      charCounter.textContent = `${promptInput.value.length} chars`;
    }
  };

  rec.onspeechend = () => {
    jarvisStatus.textContent = 'PROCESSANDO...';
    rec.stop();
  };

  rec.onend = () => {
    closeJarvis();
    if (promptInput.value.trim()) setTimeout(executePrompt, 300);
  };

  rec.onerror = (e) => {
    const msgs = {
      'not-allowed': 'Permissão de microfone negada.',
      'no-speech'  : 'Nenhuma fala detectada. Tente de novo.',
      'network'    : 'Erro de rede no reconhecimento de voz.',
    };
    jarvisStatus.textContent = msgs[e.error] || `Erro: ${e.error}`;
    setTimeout(closeJarvis, 2000);
  };

  return rec;
}

function openJarvis() {
  recognition = initRecognition();
  if (!recognition) return;
  recognition.start();
}

function closeJarvis() {
  jarvisOverlay.classList.add('hidden');
  micBtn.classList.remove('mic-active');
}

micBtn.addEventListener('click', () => {
  if (jarvisOverlay.classList.contains('hidden')) openJarvis();
  else { if (recognition) recognition.stop(); closeJarvis(); }
});

jarvisStopBtn.addEventListener('click', () => {
  if (recognition) recognition.stop();
  closeJarvis();
});

// ── TTS toggle ────────────────────────────────────────────────────────────────
function syncTtsButton() {
  ttsIcon.textContent = ttsEnabled ? '🔊' : '🔇';
  ttsToggleBtn.classList.toggle('tts-active', ttsEnabled);
  ttsToggleBtn.title = ttsEnabled ? 'TTS ativado — clique para desativar' : 'Ativar leitura em voz alta';
}
syncTtsButton(); // sincroniza estado inicial

ttsToggleBtn.addEventListener('click', () => {
  ttsEnabled = !ttsEnabled;
  syncTtsButton();
  getAudioCtx(); // garante que o AudioContext foi criado no clique
});

let audioCtx = null;
let currentSource = null;

function getAudioCtx() {
  if (!audioCtx || audioCtx.state === 'closed') {
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  }
  if (audioCtx.state === 'suspended') audioCtx.resume();
  return audioCtx;
}

// Inicializa o AudioContext no primeiro clique do usuário
document.addEventListener('click', () => getAudioCtx(), { once: true });

async function speakText(text) {
  if (!ttsEnabled) return;
  if (currentSource) { try { currentSource.stop(); } catch(_) {} currentSource = null; }
  try {
    const res = await fetch('/api/tts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    if (!res.ok) throw new Error(`TTS error ${res.status}`);
    const arrayBuffer = await res.arrayBuffer();
    const ctx = getAudioCtx();
    const decoded = await ctx.decodeAudioData(arrayBuffer);
    currentSource = ctx.createBufferSource();
    currentSource.buffer = decoded;
    currentSource.connect(ctx.destination);
    currentSource.start(0);
  } catch (err) {
    console.error('ElevenLabs TTS falhou:', err);
  }
}

// ── Execute prompt ────────────────────────────────────────────────────────────
runBtn.addEventListener('click', executePrompt);
promptInput.addEventListener('keydown', e => {
  if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') executePrompt();
});

async function executePrompt() {
  const prompt = promptInput.value.trim();
  if (!prompt || running) return;

  running = true;
  runBtn.disabled = true;
  btnText.textContent = 'Executando…';
  btnSpinner.classList.remove('hidden');
  resultCard.style.display  = 'none';
  errorCard.style.display   = 'none';

  try {
    const body = {
      prompt,
      db_url: dbUrl(),
      temperature: parseFloat(tempSlider.value),
      model: $('modelSelect').value,
      run_name: $('runName').value.trim() || prompt.substring(0, 60),
    };

    const data = await api('/api/prompt', {
      method: 'POST',
      body: JSON.stringify(body),
    });

    if (data.error) {
      errorCard.style.display = 'block';
      errorBody.textContent   = data.error;
    } else {
      resultCard.style.display = 'block';
      resultBody.textContent   = data.answer || '(sem resposta)';

      // TTS: ler a resposta em voz alta
      speakText(data.answer || '');

      // Metrics
      const chips = [];
      if (data.latency_ms) chips.push(`⏱ ${data.latency_ms}ms`);
      if (data.total_tokens) chips.push(`🔢 ${data.total_tokens} tokens`);
      if (data.model) chips.push(data.model);
      resultMetrics.innerHTML = chips.map(c =>
        `<span class="metric-chip">${c}</span>`
      ).join('');
    }

    // Atualiza runs após execução
    setTimeout(loadRuns, 1500);

  } catch (e) {
    errorCard.style.display = 'block';
    errorBody.textContent   = e.message;
  } finally {
    running = false;
    runBtn.disabled = false;
    btnText.textContent = 'Executar';
    btnSpinner.classList.add('hidden');
  }
}

// ── DB URL change → reload tables ─────────────────────────────────────────────
$('dbUrl').addEventListener('change', loadTables);

// ── Modal ─────────────────────────────────────────────────────────────────────
$('closeModalBtn').addEventListener('click', () => modalOverlay.classList.add('hidden'));
modalOverlay.addEventListener('click', e => {
  if (e.target === modalOverlay) modalOverlay.classList.add('hidden');
});

// ── Bootstrap ─────────────────────────────────────────────────────────────────
(async () => {
  await loadConfig();
  await Promise.all([loadTables(), loadRuns()]);
})();
