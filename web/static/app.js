/* Light Agent — интерфейс.
 * Ключевые моменты:
 *  - голосовой ввод: interim-результат ЗАМЕНЯЕТ текст, а не дописывает,
 *    иначе слова дублируются;
 *  - общение с агентом через SSE: видно вызовы инструментов в реальном времени;
 *  - дерево файлов с превью картинок.
 */
'use strict';

/* =================== Утилиты =================== */
const $ = (s) => document.querySelector(s);
const el = (t, c) => { const e = document.createElement(t); if (c) e.className = c; return e; };

function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

let toastTimer;
function toast(msg) {
  const t = $('#toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove('show'), 2600);
}

const KB = (n) => (n < 1024 ? n + ' Б'
  : n < 1048576 ? (n / 1024).toFixed(1) + ' КБ' : (n / 1048576).toFixed(1) + ' МБ');

/* =================== Состояние =================== */
const state = {
  project: localStorage.getItem('la_project') || 'default',
  sessionId: localStorage.getItem('la_session') || '',
  model: localStorage.getItem('la_model') || '',
  busy: false,
  ctrl: null,       // AbortController текущего запроса
  selPath: null,
  pending: [],      // файлы, прикреплённые к сообщению
  sidebar: localStorage.getItem('la_side') !== '0',
};

/* =================== Markdown =================== */
function highlight(code, lang) {
  const esc2 = (s) => s.replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
  if (lang === 'python' || lang === 'py') {
    return esc2(code)
      .replace(/(#[^\n]*)/g, '<span class="tk-c">$1</span>')
      .replace(/("""[\s\S]*?"""|'''[\s\S]*?''')/g, '<span class="tk-s">$1</span>')
      .replace(/(".*?"|'.*?')/g, '<span class="tk-s">$1</span>')
      .replace(/\b(def|class|return|if|elif|else|for|while|import|from|as|with|try|except|finally|raise|lambda|yield|None|True|False|and|or|not|in|is|pass|break|continue|global)\b/g,
        '<span class="tk-k">$1</span>')
      .replace(/\b(\d+(\.\d+)?)\b/g, '<span class="tk-n">$1</span>');
  }
  if (/^(js|javascript|ts|typescript|json|html|css|bash|sh)$/.test(lang)) {
    return esc2(code)
      .replace(/(\/\*[\s\S]*?\*\/|\/\/[^\n]*)/g, '<span class="tk-c">$1</span>')
      .replace(/(".*?"|'.*?'|`.*?`)/g, '<span class="tk-s">$1</span>')
      .replace(/\b(function|return|const|let|var|if|else|for|while|import|export|class|new|await|async|try|catch|throw|typeof|null|true|false)\b/g,
        '<span class="tk-k">$1</span>')
      .replace(/\b(\d+(\.\d+)?)\b/g, '<span class="tk-n">$1</span>');
  }
  return esc2(code);
}

/* Мини-разбор markdown: заголовки, списки, код, таблицы, ссылки, жирный. */
function md(src) {
  if (!src) return '';
  const blocks = [];
  let s = String(src);

  // Код в тройных кавычках
  s = s.replace(/```(\w+)?\n?([\s\S]*?)```/g, (m, lang, code) => {
    const l = (lang || '').toLowerCase();
    const id = 'c' + blocks.length;
    blocks.push(`<div class="codewrap"><pre><code>${highlight(code.replace(/\n$/, ''), l)}</code></pre></div>`);
    return ' ' + id + ' ';
  });

  s = esc(s);

  // Таблицы
  s = s.replace(/^\|([^\n]+)\|\n\|([\s|: -]+)\|\n?((?:\|[^\n]*\|\n?)*)/gm, (m, h, d, rows) => {
    const th = h.split('|').map(c => `<th>${c.trim()}</th>`).join('');
    const tb = rows.trim().split('\n').filter(Boolean)
      .map(r => '<tr>' + r.split('|').map(c => `<td>${c.trim()}</td>`).join('') + '</tr>').join('');
    return `<table><thead><tr>${th}</tr></thead><tbody>${tb}</tbody></table> `;
  });
  // Diff в блоках кода: строки + добавить, - удалить, @@ заголовок
  s = s.replace(/```diff\n?([\s\S]*?)```/g, (m, body) => {
    const rows = body.replace(/\n$/, '').split('\n').map(l => {
      const t = esc(l);
      if (/^@@/.test(l)) return `<div class="diffline diff-h">${t}</div>`;
      if (/^\+\+\+|^---/.test(l)) return `<div class="diffline diff-h">${t}</div>`;
      if (l.startsWith('+')) return `<div class="diffline diff-add">${t}</div>`;
      if (l.startsWith('-')) return `<div class="diffline diff-del">${t}</div>`;
      return `<div class="diffline">${t}</div>`;
    }).join('');
    return ' ' + blocks.length + ' ';
  });
  const lines = s.split('\n');
  const out = [];
  let inList = false, listTag = 'ul';

  const inline = (t) => t
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|\W)\*([^*\n]+)\*/g, '$1<em>$2</em>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');

  for (let raw of lines) {
    const line = raw.replace(/ (\d+) /g, ' {B$1} ');

    const h = line.match(/^(#{1,4})\s+(.*)$/);
    if (h) {
      if (inList) { out.push(`</${listTag}>`); inList = false; }
      out.push(`<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`);
      continue;
    }
    if (/^(-{3,}|\*{3,})$/.test(line.trim())) {
      if (inList) { out.push(`</${listTag}>`); inList = false; }
      out.push('<hr>');
      continue;
    }
    const ul = line.match(/^\s*[-*+]\s+(.*)$/);
    const ol = line.match(/^\s*\d+\.\s+(.*)$/);
    if (ul || ol) {
      const want = ul ? 'ul' : 'ol';
      if (!inList) { out.push(`<${want}>`); inList = true; listTag = want; }
      else if (want !== listTag) { out.push(`</${listTag}><${want}>`); listTag = want; }
      out.push(`<li>${inline((ul || ol)[1])}</li>`);
      continue;
    }
    if (line.trim() === '') { if (inList) { out.push(`</${listTag}>`); inList = false; } continue; }
    if (inList) { out.push(`</${listTag}>`); inList = false; }
    if (/^>\s?/.test(line)) { out.push(`<blockquote>${inline(line.replace(/^>\s?/, ''))}</blockquote>`); continue; }
    out.push(`<p>${inline(line)}</p>`);
  }
  if (inList) out.push(`</${listTag}>`);

  return `<div class="md">${out.join('')}</div>`
    .replace(/ \{B(\d+)\} /g, (m, i) => blocks[+i]);
}

/* =================== Оформление инструментов =================== */
/* Имя инструмента -> роль и подпись в стиле Claude Code.
   Роли задают цвет: Read-синий, Write-зелёный, Edit-янтарный,
   Bash-терракотовый, поиск-фиолетовый. */
const TOOL_ROLE = {
  read_file:     ['read',   'Read'],
  write_file:    ['write',  'Write'],
  edit_file:     ['edit',   'Edit'],
  run_python_file: ['bash', 'Bash'],
  execute_code:  ['bash',   'Bash'],
  delete_file:   ['bash',   'Delete'],
  delete_dir:    ['bash',   'Delete'],
  make_dir:      ['write',  'Mkdir'],
  move_file:     ['edit',   'Move'],
  list_files:    ['read',   'List'],
  tree:          ['read',   'Tree'],
  view_image:    ['read',   'Image'],
  grep:          ['search', 'Grep'],
  web_search:    ['search', 'Search'],
  fetch_url:     ['net',    'Fetch'],
  cloud_upload:  ['net',    'Upload'],
  delegate_task: ['subagent', 'Субагент'],
  subagent_roles: ['subagent', 'Субагенты'],
  github_sync:   ['net',    'GitHub Sync'],
  github_clone:  ['write',  'GitHub Clone'],
  github_search: ['search', 'GitHub Search'],
  validate_code: ['bash',   'Проверка кода'],
  run_test:      ['bash',   'Тесты'],
  project_state_get: ['read', 'Паспорт проекта'],
  project_state_update: ['edit', 'Паспорт проекта'],
  infra_deploy_project: ['net', 'Деплой'],
};

function toolLine(name, preview) {
  const [role, label] = TOOL_ROLE[name] || ['other', name];
  const d = document.createElement('div');
  d.className = 'act r-' + role;
  const args = (preview || '').trim();
  d.innerHTML = `<span class="nm">${esc(label)}</span>` +
    (args ? `<span class="ar">(${esc(args)})</span>` : '');
  return d;
}

/* =================== Голосовой ввод =================== */
/* Ключевая идея: interim-результат показываем в отдельном поле и
 * подставляем в textarea при финальном result. Иначе текст дублируется,
 * т.к. onresult приходит несколько раз с растущим interim. */
const voice = { rec: null, active: false, base: '', final: '' };

function toggleMic() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { toast('Браузер не поддерживает речь. Откройте в Chrome или Edge.'); return; }
  if (voice.active) { voice.rec.stop(); return; }

  const inp = $('#in');
  voice.base = inp.value;   // что было до начала диктовки
  voice.final = '';

  const rec = new SR();
  voice.rec = rec;
  rec.lang = 'ru-RU';
  rec.interimResults = true;
  rec.continuous = false;

  rec.onstart = () => {
    voice.active = true;
    $('#mic').classList.add('rec');
    $('#hintRight').textContent = 'Идёт запись… говорите';
  };

  rec.onresult = (e) => {
    let interim = '';
    voice.final = '';
    // Обрабатываем ВСЕ результаты с последней обработанной позиции.
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const r = e.results[i];
      if (r.isFinal) voice.final += r[0].transcript;
      else interim += r[0].transcript;
    }
    // ЗАМЕНЯЕМ, а не дописываем: это и есть защита от дублей
    inp.value = (voice.base ? voice.base + ' ' : '') + voice.final + interim;
    grow(inp);
  };

  rec.onerror = (e) => {
    $('#mic').classList.remove('rec');
    voice.active = false;
    if (e.error === 'not-allowed') toast('Нужен доступ к микрофону');
    else if (e.error === 'no-speech') toast('Ничего не услышал');
    else if (e.error !== 'aborted') toast('Ошибка: ' + e.error);
    $('#hintRight').textContent = 'Файлы можно перетащить в окно';
  };

  rec.onend = () => {
    $('#mic').classList.remove('rec');
    voice.active = false;
    $('#hintRight').textContent = 'Файлы можно перетащить в окно';
  };

  try { rec.start(); } catch (e) { toast('Не удалось включить микрофон'); }
}

/* =================== Ввод =================== */
function grow(e) {
  if (!e) return;
  e.style.height = 'auto';
  e.style.height = Math.min(e.scrollHeight, 180) + 'px';
}

function onInputChanged(el) {
  grow(el);
  const val = (el.value || '').trim();
  const sendBtn = $('#bSend');
  if (sendBtn) {
    if (val.length > 0 || (state.pending && state.pending.length > 0)) {
      sendBtn.classList.add('active');
    } else {
      sendBtn.classList.remove('active');
    }
  }
}

function quickPrompt(promptText) {
  const inp = $('#in');
  if (!inp) return;
  inp.value = promptText;
  onInputChanged(inp);
  inp.focus();
}

function onKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  else if (e.key === 'Escape') { stopRun(); }
}

document.addEventListener('keydown', (e) => {
  if (e.ctrlKey && e.key === 'b') { e.preventDefault(); toggleSide(); }
});

/* =================== Файлы и вложения в чате =================== */
function getFileIcon(name) {
  const ext = (name || '').split('.').pop().toLowerCase();
  if (['py'].includes(ext)) return '🐍';
  if (['js', 'ts', 'jsx', 'tsx'].includes(ext)) return '⚡';
  if (['html', 'css', 'json', 'yaml', 'yml'].includes(ext)) return '🌐';
  if (['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp'].includes(ext)) return '🖼️';
  if (['pdf'].includes(ext)) return '📕';
  if (['zip', 'tar', 'gz', 'rar', '7z'].includes(ext)) return '📦';
  if (['csv', 'xlsx', 'sql'].includes(ext)) return '📊';
  return '📄';
}

function pickChatFiles() {
  const inp = $('#chatFilePick');
  if (inp) {
    inp.value = '';
    inp.click();
  }
}

function handleChatFiles(fileList) {
  if (!fileList || !fileList.length) return;
  for (let i = 0; i < fileList.length; i++) {
    const f = fileList[i];
    const isImage = f.type.startsWith('image/') || /\.(png|jpe?g|gif|svg|webp)$/i.test(f.name);
    let previewUrl = null;
    if (isImage) {
      try { previewUrl = URL.createObjectURL(f); } catch (_) {}
    }
    state.pending.push({
      file: f,
      name: f.name,
      size: f.size,
      type: f.type,
      isImage: isImage,
      previewUrl: previewUrl,
    });
  }
  renderAtt();
}

/* =================== Сообщения =================== */
function addMsg(who, text, attachments = []) {
  if ($('#welcome')) { $('#welcome').remove(); }
  const m = el('div', 'msg ' + who);
  const av = who === 'u' ? 'Вы' : '<img src="/static/icons/claude-icon.png" class="av-img" alt="Claude">';
  m.innerHTML = `<div class="av">${av}</div>
                 <div class="body"><div class="bub"></div></div>`;
  const body = m.querySelector('.body');
  const bub = m.querySelector('.bub');

  // Если были прикреплены файлы, отображаем карточки или превью картинок
  if (attachments && attachments.length) {
    const grid = el('div', 'chat-att-grid');
    attachments.forEach(att => {
      if (att.isImage && att.url) {
        const img = el('img', 'chat-att-img');
        img.src = att.url;
        img.alt = att.name;
        img.title = att.name + ' (нажмите для просмотра)';
        img.onclick = () => window.open(att.url, '_blank');
        grid.appendChild(img);
      } else {
        const card = el('div', 'chat-att-card');
        const icon = getFileIcon(att.name);
        card.innerHTML = `<span>${icon}</span><span style="font-weight:500">${esc(att.name)}</span><span style="opacity:0.6;font-size:10px">${KB(att.size)}</span>`;
        if (att.url) {
          card.style.cursor = 'pointer';
          card.title = 'Открыть в редакторе';
          card.onclick = () => viewFile(att.path || att.name);
        }
        grid.appendChild(card);
      }
    });
    bub.appendChild(grid);
  }

  if (text) {
    const txtNode = el('div');
    txtNode.textContent = text;
    bub.appendChild(txtNode);
  }

  $('#chatInner').appendChild(m);
  scrollDown();
  return body;
}

function setBusy(on) {
  state.busy = on;
  $('#bSend').hidden = on;
  $('#bStop').hidden = !on;
  $('#dot').className = 'dot' + (on ? ' busy' : ' online');
}

function scrollDown() {
  const c = $('#chat');
  c.scrollTop = c.scrollHeight;
}

function stopRun() {
  if (state.ctrl) { state.ctrl.abort(); }
  fetch('/api/cancel', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: state.sessionId })
  }).catch(() => {});
  state.ctrl = null;
  setBusy(false);
  toast('Остановлено');
}

/* =================== Отправка (SSE) =================== */
function renderAtt() {
  const box = $('#attbar');
  if (!box) return;
  box.innerHTML = '';
  if (!state.pending.length) {
    box.style.display = 'none';
    return;
  }
  box.style.display = 'flex';
  state.pending.forEach((f, i) => {
    const d = el('div', 'att');
    if (f.isImage && f.previewUrl) {
      const img = el('img');
      img.src = f.previewUrl;
      d.appendChild(img);
    } else {
      const icon = el('div', 'att-icon');
      icon.textContent = getFileIcon(f.name);
      d.appendChild(icon);
    }
    const info = el('div', 'att-info');
    info.innerHTML = `<span class="att-name">${esc(f.name)}</span><span class="att-size">${KB(f.size)}</span>`;
    d.appendChild(info);

    const b = el('button');
    b.innerHTML = '✕';
    b.title = 'Удалить';
    b.onclick = () => {
      state.pending.splice(i, 1);
      renderAtt();
    };
    d.appendChild(b);
    box.appendChild(d);
  });
}

async function send() {
  if (state.busy) return;
  let msg = $('#in').value.trim();
  if (!msg && !state.pending.length) return;

  const currentPending = [...state.pending];
  state.pending = [];
  renderAtt();

  const inp = $('#in');
  inp.value = '';
  onInputChanged(inp);

  // Загружаем прикрепленные файлы в активный проект
  const uploadedAtts = [];
  let extraPrompt = '';

  if (currentPending.length) {
    setBusy(true);
    for (const item of currentPending) {
      try {
        const fd = new FormData();
        fd.append('file', item.file, item.name);
        const upRes = await fetch('/api/upload?project=' + encodeURIComponent(state.project), {
          method: 'POST',
          body: fd,
        });
        const rawUrl = `/api/raw?path=${encodeURIComponent(item.name)}&project=${encodeURIComponent(state.project)}`;
        uploadedAtts.push({
          name: item.name,
          size: item.size,
          isImage: item.isImage,
          url: rawUrl,
          path: item.name,
        });

        // Если это текстовый файл или код до 64 КБ, встраиваем содержимое в промпт для мгновенного анализа
        const isText = /\.(py|js|ts|jsx|tsx|json|html|css|txt|md|csv|yml|yaml|sh|sql|xml|env|log)$/i.test(item.name);
        if (isText && item.size < 65536) {
          try {
            const txt = await item.file.text();
            extraPrompt += `\n\n[Прикреплённый файл '${item.name}' (${KB(item.size)})]:\n\`\`\`\n${txt}\n\`\`\`\n`;
          } catch (_) {}
        } else {
          extraPrompt += `\n\n[Пользователь прикрепил файл '${item.name}' (${KB(item.size)}), он сохранён в папку проекта '${state.project}']`;
        }
      } catch (err) {
        console.error('Ошибка загрузки файла в проект:', err);
      }
    }
    loadTree();
  }

  // Отображаем сообщение пользователя в чате с файлами
  addMsg('u', msg, uploadedAtts);

  let fullPrompt = msg;
  if (extraPrompt) {
    fullPrompt = (msg ? msg + '\n' : '') + extraPrompt;
  }

  const body = addMsg('a', '');
  const acts = el('details', 'acts');
  acts.innerHTML = '<summary><span class="chev">▶</span> Действия агента' +
    '<span class="cnt">0</span></summary>';
  const actList = el('div');
  acts.appendChild(actList);
  body.appendChild(acts);

  const live = el('div', 'thinking');
  live.innerHTML =
    '<span class="spin-wrap">' +
      '<svg class="spin-svg" viewBox="0 0 20 20" width="14" height="14" style="vertical-align:middle;flex-shrink:0;">' +
        '<circle cx="10" cy="10" r="7.5" stroke="rgba(255,255,255,0.22)" stroke-width="2.5" fill="none"/>' +
        '<circle cx="10" cy="10" r="7.5" stroke="#d97757" stroke-width="2.5" stroke-dasharray="13 35" stroke-linecap="round" fill="none"/>' +
        '<animateTransform attributeName="transform" type="rotate" from="0 10 10" to="360 10 10" dur="0.8s" repeatCount="indefinite"/>' +
      '</svg>' +
    '</span>' +
    '<span class="think-text">Думаю</span>' +
    '<span class="dots" aria-hidden="true"><span class="dot">.</span><span class="dot">.</span><span class="dot">.</span></span>' +
    '<span class="caret-block"></span>' +
    '<span class="step">шаг 1</span>';
  body.appendChild(live);

  const actsBox = el('div', 'bub');
  body.appendChild(actsBox);

  const meta = el('div', 'meta');
  body.appendChild(meta);

  setBusy(true);
  state.ctrl = new AbortController();

  const t0 = Date.now();
  let answer = '';
  let finished = false;
  let sawTool = false;

  const apiUrl = state.model
    ? '/api/chat/stream?model=' + encodeURIComponent(state.model)
    : '/api/chat/stream';

  try {
    const res = await fetch(apiUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: fullPrompt,
        session_id: state.sessionId,
        project: state.project,
        model: state.model || undefined,
      }),
      signal: state.ctrl.signal,
    });

    if (!res.ok) throw new Error('HTTP ' + res.status);

    const reader = res.body.getReader();
    const dec = new TextDecoder('utf-8');
    let buf = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });

      // SSE-сообщения разделены пустой строкой
      let idx;
      while ((idx = buf.indexOf('\n\n')) >= 0) {
        const raw = buf.slice(0, idx);
        buf = buf.slice(idx + 2);

        let ev = 'message', data = '';
        raw.split('\n').forEach(l => {
          if (l.startsWith('event:')) ev = l.slice(6).trim();
          else if (l.startsWith('data:')) data += l.slice(5).trim();
        });
        if (!data) continue;

        let d;
        try { d = JSON.parse(data); } catch (e) { continue; }

        if (ev === 'step') {
          const stepEl = live.querySelector('.step');
          if (stepEl) {
            stepEl.textContent = 'шаг ' + d.index + (d.max ? ' из ' + d.max : '');
          }
        } else if (ev === 'tool') {
          sawTool = true;
          actList.appendChild(toolLine(d.name, d.preview));
          acts.open = true;
          const n = actList.children.length;
          const badge = acts.querySelector('.cnt');
          if (badge) badge.textContent = n;
          const textEl = live.querySelector('.think-text');
          if (textEl) {
            const toolLabels = {
              'bash': 'Выполняю bash',
              'view': 'Читаю код',
              'edit': 'Редактирую',
              'write': 'Записываю',
              'glob': 'Сканирую файлы',
              'grep': 'Ищу по коду',
              'agent': 'Субагент',
              'todo': 'Планирую',
              'web_search': 'Поиск в сети',
              'fetch_url': 'Читаю веб'
            };
            textEl.textContent = toolLabels[d.name] || 'Думаю';
          }
        } else if (ev === 'done') {
          finished = true;
          if (d.ok === false && !d.answer) {
            answer = '⚠️ ' + (d.error || 'Ошибка при выполнении задачи');
          } else {
            answer = d.answer || (d.error ? ('⚠️ ' + d.error) : 'Готово.');
          }
          actsBox.innerHTML = md(answer);
          const sec = ((Date.now() - t0) / 1000).toFixed(1);
          meta.innerHTML =
            `<span class="pill">${esc(d.provider || '')}</span>` +
            `<span class="pill">${sec} с</span>` +
            (d.steps && d.steps.length ? `<span class="pill">${d.steps.length} действий</span>` : '');
          if (d.steps && d.steps.length) { loadTree(); loadProjects(); }
        } else if (ev === 'error') {
          finished = true;
          actsBox.innerHTML = md('⚠️ ' + (d.error || 'Ошибка соединения с агентом'));
        }
      }
      if (finished) { try { reader.cancel(); } catch (e) { } break; }
    }

    if (!finished) {
      actsBox.innerHTML = md(answer || '⚠️ Соединение прервалось');
    }
    live.remove();
    scrollDown();
  } catch (e) {
    live.remove();
    if (e.name === 'AbortError') {
      actsBox.innerHTML = md(answer || '_Задача остановлена_');
    } else {
      actsBox.innerHTML = md('⚠️ Ошибка связи: ' + e.message);
    }
  } finally {
    state.ctrl = null;
    setBusy(false);
    state.pending = [];
    renderAtt();
    loadSessions();
    loadProjects();
  }
}

/* =================== Дерево файлов =================== */
const ICONS = { dir: '▸', image: '🖼', pdf: '📕', audio: '🎵', video: '🎬', markdown: '📝', file: '📄' };

async function loadTree() {
  const box = $('#tree');
  try {
    const r = await fetch('/api/tree?depth=4&project=' + encodeURIComponent(state.project));
    const d = await r.json();
    box.innerHTML = '';
    if (!d.tree || !d.tree.length) {
      box.innerHTML = '<div class="hint">Папка проекта пуста.<br>Попросите агента<br>создать файлы.</div>';
      return;
    }

    const build = (items, depth) => {
      items.forEach(it => {
        const n = el('div', 'tnode');
        if (it.path === state.selPath) n.classList.add('sel');
        n.style.paddingLeft = (depth * 12 + 6) + 'px';
        n.innerHTML =
          (it.type === 'dir' ? '<span class="ic" data-open="1">▾</span>'
            : `<span class="ic">${ICONS[it.type] || ICONS.file}</span>`) +
          `<span class="nm">${esc(it.name)}</span>` +
          (it.type !== 'dir' ? `<span class="sz">${KB(it.size)}</span>` : '');
        n.onclick = () => {
          if (it.type === 'dir') {
            const ic = n.querySelector('[data-open]');
            const open = ic.getAttribute('data-open') === '1';
            ic.setAttribute('data-open', open ? '0' : '1');
            ic.textContent = open ? '▸' : '▾';
            const kids = n.nextElementSibling;
            if (kids && kids.classList.contains('kids')) {
              kids.style.display = open ? 'none' : '';
            }
          } else {
            openFile(it.path);
          }
        };
        box.appendChild(n);

        if (it.children && it.children.length) {
          const kids = el('div', 'kids');
          build(it.children, depth + 1);
          kids.style.display = '';
          box.appendChild(kids);
        }
      });
    };
    build(d.tree, 0);
  } catch (e) {
    box.innerHTML = '<div class="hint">Не удалось загрузить список</div>';
  }
}

/* =================== Просмотр файла =================== */
async function openFile(path) {
  state.selPath = path;
  $('#fpanel').classList.remove('hidden');
  $('#fpPath').textContent = path;
  const body = $('#fpBody');
  body.innerHTML = '<div class="hint">Загрузка…</div>';

  if (isMobile()) {
    $('#side').classList.add('collapsed');
    state.sidebar = false;
    showScrim(true);
  }

  const rawUrl = `/api/raw?path=${encodeURIComponent(path)}&project=${encodeURIComponent(state.project)}`;
  const fileName = esc(path.split('/').pop());

  try {
    const r = await fetch('/api/file?path=' + encodeURIComponent(path) + '&project=' + encodeURIComponent(state.project));
    const d = await r.json();

    if (d.is_pdf) {
      body.innerHTML =
        `<div class="file-view-container pdf-container">
          <div class="file-view-bar">
            <span class="file-badge">📕 PDF Документ</span>
            <span class="file-meta">${KB(d.size || 0)}</span>
            <a href="${rawUrl}" target="_blank" rel="noopener" class="file-btn" title="Открыть в новой вкладке">↗ На весь экран</a>
            <a href="${rawUrl}" download="${fileName}" class="file-btn" title="Скачать">⬇ Скачать</a>
          </div>
          <iframe src="${rawUrl}#toolbar=1&navpanes=1" class="pdf-frame" title="${esc(path)}"></iframe>
        </div>`;
      $('#bSave').style.visibility = 'hidden';
      return;
    }

    if (d.is_audio) {
      body.innerHTML =
        `<div class="file-view-container media-container">
          <div class="file-view-bar">
            <span class="file-badge">🎵 Аудиозапись</span>
            <span class="file-meta">${KB(d.size || 0)}</span>
            <a href="${rawUrl}" download="${fileName}" class="file-btn">⬇ Скачать</a>
          </div>
          <div class="media-body">
            <audio controls src="${rawUrl}" style="width:100%; max-width:440px;"></audio>
          </div>
        </div>`;
      $('#bSave').style.visibility = 'hidden';
      return;
    }

    if (d.is_video) {
      body.innerHTML =
        `<div class="file-view-container media-container">
          <div class="file-view-bar">
            <span class="file-badge">🎬 Видео</span>
            <span class="file-meta">${KB(d.size || 0)}</span>
            <a href="${rawUrl}" target="_blank" rel="noopener" class="file-btn">↗ На весь экран</a>
            <a href="${rawUrl}" download="${fileName}" class="file-btn">⬇ Скачать</a>
          </div>
          <div class="media-body">
            <video controls src="${rawUrl}" style="max-width:100%; max-height:480px; border-radius:8px; background:#000;"></video>
          </div>
        </div>`;
      $('#bSave').style.visibility = 'hidden';
      return;
    }

    if (d.is_image) {
      body.innerHTML =
        `<div class="file-view-container imgview-container">
          <div class="file-view-bar">
            <span class="file-badge">🖼️ Изображение</span>
            <span class="file-meta">${KB(d.size || 0)} · ${esc(d.mime || '')}</span>
            <a href="${rawUrl}" target="_blank" rel="noopener" class="file-btn">↗ На весь экран</a>
            <a href="${rawUrl}" download="${fileName}" class="file-btn">⬇ Скачать</a>
          </div>
          <div class="imgview">
            <img src="${rawUrl}" alt="${esc(path)}">
          </div>
        </div>`;
      $('#bSave').style.visibility = 'hidden';
      return;
    }

    if (d.is_markdown) {
      $('#bSave').style.visibility = 'visible';
      body.innerHTML =
        `<div class="file-view-container">
          <div class="file-view-bar">
            <span class="file-badge">📝 Markdown</span>
            <span class="file-meta">${KB(d.size || 0)}</span>
            <button class="file-btn" id="bMdToggle" type="button">👁 Превью</button>
            <a href="${rawUrl}" download="${fileName}" class="file-btn">⬇ Скачать</a>
          </div>
          <div id="mdEditorWrap" style="height:100%; display:flex; flex-direction:column;">
            <textarea spellcheck="false" style="flex:1; width:100%; border:none; padding:12px 14px; background:var(--bg); color:var(--code); font-family:var(--mono); font-size:12.5px; line-height:1.65; resize:none;"></textarea>
          </div>
          <div id="mdPreviewWrap" class="md-preview" style="display:none; height:100%; flex:1;"></div>
        </div>`;
      const ta = body.querySelector('textarea');
      ta.value = d.content || '';
      const toggleBtn = $('#bMdToggle');
      const edWrap = $('#mdEditorWrap');
      const prevWrap = $('#mdPreviewWrap');
      let previewMode = false;
      toggleBtn.onclick = () => {
        previewMode = !previewMode;
        if (previewMode) {
          prevWrap.innerHTML = md(ta.value);
          prevWrap.style.display = 'block';
          edWrap.style.display = 'none';
          toggleBtn.textContent = '📝 Код';
        } else {
          prevWrap.style.display = 'none';
          edWrap.style.display = 'flex';
          toggleBtn.textContent = '👁 Превью';
        }
      };
      $('#bSave').disabled = false;
      return;
    }

    $('#bSave').style.visibility = 'visible';
    if (d.too_big) {
      body.innerHTML = `<div class="hint">${esc(d.message || 'Файл слишком большой')}
        <br><br><a href="${rawUrl}" download="${fileName}" class="file-btn" style="margin:0 auto;">⬇ Скачать файл (${KB(d.size || 0)})</a>
      </div>`;
      $('#bSave').style.visibility = 'hidden';
      return;
    }
    body.innerHTML = '<textarea spellcheck="false"></textarea>';
    const ta = body.querySelector('textarea');
    ta.value = d.content || '';
    $('#bSave').disabled = false;
  } catch (e) {
    body.innerHTML = '<div class="hint">Ошибка загрузки файла</div>';
  }
  loadTree();
}

function closeFile() {
  $('#fpanel').classList.add('hidden');
  state.selPath = null;
  if (isMobile()) showScrim(false);
  loadTree();
}

async function saveFile() {
  if (!state.selPath) return;
  const ta = $('#fpBody').querySelector('textarea');
  if (!ta) return;
  try {
    const r = await fetch('/api/file', {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: state.selPath, content: ta.value, project: state.project }),
    });
    const d = await r.json();
    if (d.ok) toast('Сохранено · ' + KB(d.size));
    else toast('Ошибка: ' + (d.detail || '?'));
  } catch (e) { toast('Ошибка сети'); }
}

function downloadFile() {
  if (state.selPath) location.href = '/api/raw?path=' + encodeURIComponent(state.selPath) + '&project=' + encodeURIComponent(state.project);
}

function runFile() {
  if (!state.selPath) return;
  $('#in').value = 'Запусти файл ' + state.selPath + ' и покажи результат';
  grow($('#in'));
  send();
}

function askAboutFile() {
  if (!state.selPath) return;
  $('#in').value = 'Прочитай файл ' + state.selPath + ' и объясни, что он делает';
  grow($('#in'));
  send();
}

async function delFile() {
  if (!state.selPath || !confirm('Удалить ' + state.selPath + '?')) return;
  if (isMobile()) showScrim(false);
  let r = await fetch('/api/file?path=' + encodeURIComponent(state.selPath) + '&project=' + encodeURIComponent(state.project), { method: 'DELETE' });
  if (!r.ok) {
    const e = await r.json();
    if ((e.detail || '').includes('не пустая') && confirm(e.detail + ' Продолжить?')) {
      r = await fetch('/api/file?path=' + encodeURIComponent(state.selPath) + '&recursive=true&project=' + encodeURIComponent(state.project), { method: 'DELETE' });
    } else { toast(e.detail || 'Не удалось'); return; }
  }
  toast('Удалено');
  closeFile();
}

/* =================== Проекты =================== */
async function loadProjects() {
  try {
    const r = await fetch('/api/projects');
    const d = await r.json();
    const sel = $('#projSelect');
    if (!sel) return;
    sel.innerHTML = '';
    const list = d.projects || [];
    let found = false;
    list.forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.slug;
      const countLabel = p.messages ? `${p.messages} сообщ.` : (p.files ? `${p.files} ф.` : '0 сообщ.');
      opt.textContent = `${p.name} (${countLabel})`;
      if (p.slug === state.project) {
        opt.selected = true;
        found = true;
      }
      sel.appendChild(opt);
    });

    if (!found && list.length) {
      state.project = list[0].slug;
      localStorage.setItem('la_project', state.project);
      sel.value = state.project;
    }

    const b = $('#bProj');
    if (b) b.textContent = '📁 ' + state.project;
    const t = $('#filesHeadTitle');
    if (t) t.textContent = '📄 ' + state.project;
  } catch (e) {
    console.warn('Не удалось загрузить список проектов', e);
  }
}

async function switchProject(slug) {
  if (!slug) return;
  state.project = slug;
  localStorage.setItem('la_project', slug);
  const b = $('#bProj');
  if (b) b.textContent = '📁 ' + slug;
  const t = $('#filesHeadTitle');
  if (t) t.textContent = '📄 ' + slug;
  const wt = $('#winTitleProject');
  if (wt) wt.textContent = slug;
  const sel = $('#projSelect');
  if (sel && sel.value !== slug) sel.value = slug;

  toast('Проект: ' + slug);
  await loadTree();
  await loadSessions();
}

async function newProjectPrompt() {
  const name = prompt('Имя нового проекта (например: my-website, bot, parser):');
  if (!name || !name.trim()) return;
  try {
    const r = await fetch('/api/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name.trim() })
    });
    const d = await r.json();
    if (d.ok) {
      toast('Проект создан: ' + (d.name || name.trim()));
      await loadProjects();
      await switchProject(d.slug || name.trim());
    } else {
      toast('Ошибка: ' + (d.detail || d.error || 'не удалось'));
    }
  } catch (e) {
    toast('Ошибка сети');
  }
}

/* =================== Сессии и история =================== */
let welcomeTemplate = '';

async function renderRecentSessionChips() {
  try {
    const r = await fetch('/api/sessions?project=' + encodeURIComponent(state.project));
    const d = await r.json();
    const sessions = (d.sessions || []).filter(s => s.message_count > 0).slice(0, 5);
    if (!sessions.length) return;
    const welcomeEl = $('#welcome');
    if (!welcomeEl) return;
    let chipWrap = welcomeEl.querySelector('.recent-chats-wrap');
    if (chipWrap) chipWrap.remove();
    chipWrap = document.createElement('div');
    chipWrap.className = 'recent-chats-wrap';
    chipWrap.style.cssText = 'margin:14px 0 10px;padding:12px;background:var(--bg2,#212120);border:1px solid var(--line,#343432);border-radius:10px;text-align:left;';
    const heading = document.createElement('div');
    heading.style.cssText = 'font-size:11.5px;font-weight:600;color:var(--dim,#999);text-transform:uppercase;letter-spacing:0.05em;margin-bottom:8px;';
    heading.textContent = '💬 Недавние диалоги проекта ' + state.project + ' (нажмите, чтобы открыть):';
    chipWrap.appendChild(heading);
    const listDiv = document.createElement('div');
    listDiv.className = 'recent-chats-list';
    listDiv.style.cssText = 'display:flex;flex-direction:column;gap:6px;';
    sessions.forEach(s => {
      const item = document.createElement('button');
      item.className = 'recent-chat-btn';
      item.style.cssText = 'display:flex;align-items:center;justify-content:space-between;gap:8px;padding:8px 11px;background:var(--bg,#181817);border:1px solid var(--line2,#3e3e3b);border-radius:6px;color:var(--txt,#ececec);font-size:12.5px;cursor:pointer;text-align:left;transition:all 0.15s;width:100%;';
      item.onmouseenter = () => { item.style.borderColor = 'var(--acc,#d97757)'; item.style.background = '#252523'; };
      item.onmouseleave = () => { item.style.borderColor = 'var(--line2,#3e3e3b)'; item.style.background = 'var(--bg,#181817)'; };
      const titleSpan = document.createElement('span');
      titleSpan.style.cssText = 'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;font-weight:500;';
      titleSpan.textContent = s.title || s.id;
      const countSpan = document.createElement('span');
      countSpan.style.cssText = 'font-size:10.5px;color:var(--dim,#888);background:rgba(255,255,255,0.06);padding:2px 7px;border-radius:10px;flex-shrink:0;';
      countSpan.textContent = `${s.message_count} сообщ.`;
      item.appendChild(titleSpan);
      item.appendChild(countSpan);
      item.onclick = () => switchSession(s.id);
      listDiv.appendChild(item);
    });
    chipWrap.appendChild(listDiv);
    const hint = welcomeEl.querySelector('.hintline');
    if (hint) {
      welcomeEl.insertBefore(chipWrap, hint.nextSibling);
    } else {
      welcomeEl.appendChild(chipWrap);
    }
  } catch (e) {
    console.warn('Не удалось загрузить недавние диалоги', e);
  }
}

function showWelcome() {
  const inner = $('#chatInner');
  if (!welcomeTemplate && $('#welcome')) {
    welcomeTemplate = $('#welcome').outerHTML;
  }
  if (welcomeTemplate) {
    inner.innerHTML = welcomeTemplate;
    document.querySelectorAll('.sugg').forEach(s => {
      s.onclick = () => {
        $('#in').value = s.dataset.q;
        grow($('#in'));
        send();
      };
    });
    renderRecentSessionChips();
  } else {
    inner.innerHTML = '';
  }
}

function renderMessages(msgs) {
  const chat = $('#chatInner');
  chat.innerHTML = '';
  if (!msgs || !msgs.length) {
    showWelcome();
    return;
  }
  msgs.forEach(m => {
    const who = m.role === 'user' ? 'u' : 'a';
    const div = el('div', 'msg ' + who);
    const av = who === 'u' ? 'Вы' : '<img src="/static/icons/claude-icon.png" class="av-img" alt="Claude">';
    const timeStr = m.created_at ? new Date(m.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '';
    div.innerHTML = `<div class="av">${av}</div>
      <div class="body">
        <div class="bub">${who === 'u' ? esc(m.content) : md(m.content)}</div>
        ${timeStr ? `<div class="meta"><span class="pill">${timeStr}</span></div>` : ''}
      </div>`;
    chat.appendChild(div);
  });
  scrollDown();
}

async function loadHistory(id) {
  if (!id) {
    try {
      const pr = await fetch('/api/project/' + encodeURIComponent(state.project) + '/messages');
      const pd = await pr.json();
      if (pd.messages && pd.messages.length) {
        renderMessages(pd.messages);
        return;
      }
    } catch (e) {}
    showWelcome();
    return;
  }
  try {
    const r = await fetch('/api/session/' + encodeURIComponent(id) + '/messages');
    const d = await r.json();
    const msgs = d.messages || [];
    if (!msgs.length) {
      // Fallback: check project-wide messages
      try {
        const pr = await fetch('/api/project/' + encodeURIComponent(state.project) + '/messages');
        const pd = await pr.json();
        if (pd.messages && pd.messages.length) {
          renderMessages(pd.messages);
          return;
        }
      } catch (e) {}
      showWelcome();
      return;
    }
    renderMessages(msgs);
  } catch (e) {
    console.warn('Не удалось загрузить историю сессии', e);
    showWelcome();
  }
}

async function loadSessions() {
  try {
    const r = await fetch('/api/sessions?project=' + encodeURIComponent(state.project));
    const d = await r.json();
    const box = $('#sessList');
    box.innerHTML = '';
    const list = d.sessions || [];

    const savedSess = localStorage.getItem('la_session_' + state.project);
    let chosenId = '';

    if (savedSess && list.some(s => s.id === savedSess)) {
      chosenId = savedSess;
    } else if (list.length > 0) {
      chosenId = list[0].id;
    }

    if (!list.length) {
      box.innerHTML = '<div class="hint" style="padding:8px 4px;font-size:11px">Нет диалогов в этом проекте</div>';
      state.sessionId = 's-' + state.project + '-' + Date.now().toString(36);
      localStorage.setItem('la_session_' + state.project, state.sessionId);
      await loadHistory(null);
      return;
    }

    state.sessionId = chosenId;
    localStorage.setItem('la_session_' + state.project, state.sessionId);

    list.forEach(s => {
      const n = el('div', 'sess');
      if (s.id === state.sessionId) n.classList.add('sel');
      const title = s.title || s.id;
      const short = title.length > 20 ? title.slice(0, 19) + '…' : title;
      const count = s.message_count ? `<span class="cnt">${s.message_count}</span>` : '';
      n.innerHTML = `<span class="nm" title="${esc(title)}">${esc(short)}</span>
                     ${count}
                     <button class="del" title="Удалить диалог" onclick="deleteSession('${esc(s.id)}', event)">✕</button>`;
      n.onclick = () => switchSession(s.id);
      box.appendChild(n);
    });

    await loadHistory(state.sessionId);
  } catch (e) {
    console.warn('Ошибка загрузки сессий', e);
  }
}

async function switchSession(id) {
  state.sessionId = id;
  localStorage.setItem('la_session_' + state.project, id);
  document.querySelectorAll('#sessList .sess').forEach(el => el.classList.remove('sel'));
  loadSessions();
}

function newSession() {
  const id = 's-' + state.project + '-' + Date.now().toString(36);
  state.sessionId = id;
  localStorage.setItem('la_session_' + state.project, id);
  showWelcome();
  loadSessions();
  $('#in').focus();
}

async function deleteSession(id, ev) {
  if (ev) ev.stopPropagation();
  if (!confirm('Удалить этот диалог?')) return;
  try {
    await fetch('/api/session/' + encodeURIComponent(id), { method: 'DELETE' });
    toast('Диалог удалён');
    if (state.sessionId === id) {
      state.sessionId = '';
      localStorage.removeItem('la_session');
    }
    await loadSessions();
  } catch (e) {
    toast('Не удалось удалить');
  }
}

/* =================== Файлы: загрузка, папки =================== */
function uploadPick() { $('#filePick').click(); }

async function doUpload(files) {
  if (!files || !files.length) return;
  for (const f of files) {
    if (f.size > 5 * 1024 * 1024) { toast(f.name + ' больше 5 МБ'); continue; }
    const fd = new FormData();
    fd.append('file', f);
    try {
      const r = await fetch('/api/upload?project=' + encodeURIComponent(state.project), { method: 'POST', body: fd });
      const d = await r.json();
      if (d.ok) { toast('Загружено: ' + d.name + ' · ' + KB(d.size)); }
      else toast('Ошибка: ' + (d.detail || '?'));
    } catch (e) { toast('Ошибка сети при загрузке'); }
  }
  loadTree();
}

let modalAction = null;
function newFolder() { openModal('Новая папка', '', () => mkdir(mInputValue())); }
function renameFile() { openModal('Переименовать', state.selPath || '', (v) => doRename(v)); }

function openModal(title, value, action) {
  $('#mTitle').textContent = title;
  const i = $('#mInput');
  i.value = value;
  modalAction = action;
  $('#modal').classList.add('show');
  setTimeout(() => i.focus(), 30);
}
function mClose() { $('#modal').classList.remove('show'); modalAction = null; }
function mInputValue() { return $('#mInput').value.trim(); }
function mOk() { const v = mInputValue(); if (v && modalAction) modalAction(v); mClose(); }

async function mkdir(path) {
  try {
    const r = await fetch('/api/mkdir', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path, project: state.project }),
    });
    const d = await r.json();
    toast(d.ok ? 'Папка создана: ' + d.path : (d.detail || 'Ошибка'));
    loadTree();
  } catch (e) { toast('Ошибка сети'); }
}

async function doRename(newPath) {
  const old = state.selPath;
  if (!old) return;
  try {
    const r = await fetch('/api/rename', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source: old, destination: newPath, project: state.project }),
    });
    const d = await r.json();
    toast(d.ok ? 'Переименовано' : (d.detail || 'Ошибка'));
    state.selPath = newPath;
    openFile(newPath);
    loadTree();
  } catch (e) { toast('Ошибка сети'); }
}

/* =================== PWA: установка и офлайн =================== */
const PWA = {
  deferred: null,      // beforeinstallprompt
  swReg: null,
  installed: false,
};

/* Регистрируем service worker: делает приложение работоспособным офлайн */
if ('serviceWorker' in navigator) {
  window.addEventListener('load', async () => {
    try {
      const reg = await navigator.serviceWorker.register('/static/sw.js',
        { scope: '/' });
      PWA.swReg = reg;
      // Обновление SW — показываем лог в консоль и перезагружаем один раз
      reg.addEventListener('updatefound', () => {
        const sw = reg.installing;
        if (!sw) return;
        sw.addEventListener('statechange', () => {
          if (sw.state === 'installed' && navigator.serviceWorker.controller) {
            console.info('[pwa] обновление загружено — перезагрузка при следующем визите');
          }
        });
      });
    } catch (e) {
      console.warn('[pwa] service worker не зарегистрирован', e);
    }
  });
}

/* Браузер сообщает, что приложение можно установить */
window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();
  PWA.deferred = e;
  updateInstallUI();
});

/* Приложение установлено — прячем кнопку */
window.addEventListener('appinstalled', () => {
  PWA.deferred = null;
  PWA.installed = true;
  localStorage.setItem('la_installed', '1');
  updateInstallUI();
  toast('Приложение установлено');
});

/* Запуск с ярлыка: обрабатываем шорткаты из манифеста */
(function handleShortcuts() {
  const action = new URLSearchParams(location.search).get('action');
  if (!action) return;
  setTimeout(() => {
    if (action === 'new-session') newSession();
    else if (action === 'upload') { toggleSide(); uploadPick(); }
    else if (action === 'new-project') {
      toggleSide();
      $('#in').value = 'Создай новый проект: спроси у меня имя и цель, ' +
        'затем создай структуру папок и файлов';
      grow($('#in'));
      send();
    }
    history.replaceState(null, '', '/');
  }, 400);
})();

function isStandalone() {
  return window.matchMedia('(display-mode: standalone)').matches ||
    window.navigator.standalone === true;
}

function updateInstallUI() {
  const btn = $('#bInstall');
  if (!btn) return;
  // Показываем кнопку только когда браузер реально предлагает установку
  const canInstall = !!PWA.deferred && !isStandalone();
  btn.hidden = !canInstall;
  if (canInstall) {
    btn.classList.add('pulse');
  } else {
    btn.classList.remove('pulse');
  }
}

async function installApp() {
  if (!PWA.deferred) {
    // Браузер не даёт кнопку — показываем ручную инструкцию
    showInstallHelp();
    return;
  }
  PWA.deferred.prompt();
  try {
    const choice = await PWA.deferred.userChoice;
    if (choice.outcome === 'accepted') {
      toast('Устанавливаю…');
    } else {
      toast('Установка отменена');
    }
  } catch (e) {
    toast('Не удалось установить');
  }
  PWA.deferred = null;
  updateInstallUI();
}

function showInstallHelp() {
  const ua = navigator.userAgent;
  const isIOS = /iPad|iPhone|iPod/.test(ua) ||
    (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  const isAndroid = /Android/.test(ua);

  const msg = isIOS
    ? 'На iPhone: нажмите кнопку «Поделиться» (⬆) внизу экрана Safari, ' +
      'затем выберите «На экран Домой».'
    : isAndroid
      ? 'На Android: откройте меню браузера (⋮) и выберите ' +
        '«Установить приложение» или «Добавить на главный экран».'
      : 'В браузере: откройте меню и выберите «Установить приложение» ' +
        'или «Добавить на главный экран» (Ctrl+Shift+P в Chrome).';

  toast(msg);
}

/* =================== Мобильные панели =================== */
const isMobile = () => window.matchMedia('(max-width: 768px)').matches;

// Подстройка высоты окна под динамическую клавиатуру мобильных браузеров
function syncViewportHeight() {
  const vv = window.visualViewport;
  const h = vv ? vv.height : window.innerHeight;
  document.documentElement.style.setProperty('--vh', `${h * 0.01}px`);
}
window.addEventListener('resize', syncViewportHeight);
if (window.visualViewport) {
  window.visualViewport.addEventListener('resize', syncViewportHeight);
  window.visualViewport.addEventListener('scroll', syncViewportHeight);
}
syncViewportHeight();

function ensureScrim() {
  let scrim = $('#scrim');
  if (!scrim) {
    scrim = el('div', 'scrim');
    scrim.id = 'scrim';
    scrim.onclick = closeAllPanels;
    document.body.appendChild(scrim);
  }
  return scrim;
}

function showScrim(on) {
  ensureScrim().classList.toggle('on', !!on);
}

function closeAllPanels() {
  const side = $('#side');
  if (isMobile()) {
    side.classList.add('collapsed');
    state.sidebar = false;
    localStorage.setItem('la_side', '0');
  }
  $('#fpanel').classList.add('hidden');
  state.selPath = null;
  showScrim(false);
  loadTree();
}

function toggleSide() {
  const side = $('#side');
  if (isMobile()) {
    // На телефоне панель поверх чата, а не рядом
    const willOpen = side.classList.contains('collapsed');
    side.classList.toggle('collapsed', !willOpen);
    $('#fpanel').classList.add('hidden');
    showScrim(willOpen);
    state.sidebar = willOpen;
    localStorage.setItem('la_side', willOpen ? '1' : '0');
    if (willOpen) loadTree();
    return;
  }
  state.sidebar = !state.sidebar;
  side.classList.toggle('collapsed', !state.sidebar);
  localStorage.setItem('la_side', state.sidebar ? '1' : '0');
  if (state.sidebar) loadTree();
}

/* =================== Интерфейс: панели, статус =================== */
/* =================== Панели: статус =================== */
async function loadStatus() {
  try {
    const r = await fetch('/api/status');
    const s = await r.json();

    const models = [];
    (s.providers || []).forEach(p => {
      (p.models || []).forEach(m => {
        const label = (p.model_labels && p.model_labels[m]) ? p.model_labels[m] : m;
        models.push({ id: m, label: label, provider: p.name });
      });
    });

    const bLLM = $('#bLLM');
    if (bLLM) {
      bLLM.textContent = models.length ? models.length + ' мод.' : 'нет LLM';
      bLLM.className = 'badge ' + (models.length ? 'ok' : 'bad');
    }

    const bMem = $('#bMem');
    if (bMem) {
      const hasMem = s.memory && s.memory.enabled;
      const count = s.memory && s.memory.messages ? ` (${s.memory.messages})` : '';
      bMem.textContent = hasMem ? `Supabase${count}` : 'без памяти';
      bMem.className = 'badge ' + (hasMem ? 'ok' : 'bad');
      bMem.title = hasMem ? `Supabase база активна: ${s.memory.messages || 0} сообщений в памяти агента` : 'Память отключена';
    }

    const bSto = $('#bSto');
    if (bSto) {
      bSto.textContent = s.storage && s.storage.enabled ? (s.storage.bucket || 'диск') : 'нет S3';
      bSto.className = 'badge ' + (s.storage && s.storage.enabled ? 'ok' : 'bad');
    }

    // Выбор модели с понятными названиями
    const sel = $('#selModel');
    if (sel && sel.dataset.n !== String(models.length)) {
      const cur = state.model || (models.length ? models[0].id : '');
      sel.innerHTML = models.map(m =>
        `<option value="${esc(m.id)}"${m.id === cur ? ' selected' : ''}>${esc(m.label)}</option>`).join('');
      sel.dataset.n = String(models.length);
      if (!state.model && models.length) { state.model = models[0].id; }
      if (sel.value) state.model = sel.value;
    }

    setNet(true);
  } catch (e) {
    console.error('loadStatus error:', e);
    setNet(false);
  }
}

function setNet(on) {
  const b = $('#bNet');
  if (b) {
    b.textContent = on ? 'онлайн' : 'офлайн';
    b.className = 'badge ' + (on ? 'ok' : 'bad');
  }
  const dot = $('#dot');
  if (dot && !state.busy) {
    dot.className = 'dot' + (on ? ' online' : ' offline');
  }
}

function loadModel() {
  state.model = $('#selModel').value || '';
  localStorage.setItem('la_model', state.model);
  toast('Модель: ' + (state.model || 'авто'));
}
$('#selModel').addEventListener('change', loadModel);

/* =================== Drag & drop и вставка из буфера =================== */
const dz = $('#drop');
window.addEventListener('dragover', e => { e.preventDefault(); if (dz) dz.classList.add('on'); });
window.addEventListener('dragleave', e => {
  if (e.clientX === 0 && e.clientY === 0 && dz) dz.classList.remove('on');
});
window.addEventListener('drop', e => {
  e.preventDefault();
  if (dz) dz.classList.remove('on');
  if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length) {
    handleChatFiles(e.dataTransfer.files);
    toast(`Прикреплено файлов: ${e.dataTransfer.files.length}`);
  }
});

// Вставка изображений или файлов из буфера обмена (Ctrl+V / мобильная вставка)
window.addEventListener('paste', e => {
  if (e.clipboardData && e.clipboardData.files && e.clipboardData.files.length) {
    e.preventDefault();
    handleChatFiles(e.clipboardData.files);
    toast(`Прикреплено из буфера: ${e.clipboardData.files.length}`);
  }
});

/* клик по примеру */
document.querySelectorAll('.sugg').forEach(s => {
  s.onclick = () => {
    $('#in').value = s.dataset.q;
    grow($('#in'));
    send();
  };
});

/* =================== Секреты (шифрованное хранилище) =================== */
/* Список секретов виден всегда, значения — нет: их нельзя прочитать
 * из интерфейса, агент достаёт их сам по имени при работе с API. */
async function loadVault() {
  const box = $('#vaultList');
  if (!box) return;
  try {
    const r = await fetch('/api/vault');
    const d = await r.json();
    const items = d.secrets || [];
    if (!items.length) {
      box.innerHTML = '<div class="vhint" style="padding:6px 8px">' +
        'Пусто. Нажмите ＋, чтобы сохранить API-ключ вне проекта.</div>';
      return;
    }
    box.innerHTML = '';
    items.forEach(s => {
      const n = el('div', 'sec');
      n.innerHTML = '<span class="ic">🔑</span>' +
        '<span class="nm">' + esc(s.name) + '</span>' +
        '<button title="Удалить">✕</button>';
      n.querySelector('button').onclick = (e) => {
        e.stopPropagation();
        if (confirm('Удалить секрет ' + s.name + '?')) delSecret(s.name);
      };
      box.appendChild(n);
    });
  } catch (e) {
    box.innerHTML = '<div class="vhint" style="padding:6px 8px">' +
      'Хранилище недоступно</div>';
  }
}

function openSecretDialog() {
  $('#sForm').style.display = '';
  $('#sView').style.display = 'none';
  $('#sSave').style.display = '';
  $('#sTitle').textContent = 'Новый секрет';
  $('#sName').value = '';
  $('#sValue').value = '';
  $('#sNote').value = '';
  $('#secModal').classList.add('show');
  setTimeout(() => $('#sName').focus(), 30);
}

function secClose() {
  $('#secModal').classList.remove('show');
  // Чистим поле с ключом из памяти вкладки
  $('#sValue').value = '';
}

async function saveSecret() {
  const name = $('#sName').value.trim();
  const value = $('#sValue').value;
  const note = $('#sNote').value.trim();
  if (!name || !value) { toast('Нужны имя и значение'); return; }
  try {
    const r = await fetch('/admin/vault', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + adminToken(),
      },
      body: JSON.stringify({ name, value, note }),
    });
    const j = await r.json();
    if (j.ok) {
      toast('Секрет «' + j.name + '» сохранён');
      secClose();
      loadVault();
    } else {
      toast('Ошибка: ' + (j.detail || '?').slice(0, 60));
    }
  } catch (e) {
    toast('Ошибка сети');
  }
}

async function delSecret(name) {
  try {
    const r = await fetch('/admin/vault?name=' + encodeURIComponent(name), {
      method: 'DELETE',
      headers: { 'Authorization': 'Bearer ' + adminToken() },
    });
    const j = await r.json();
    toast(j.ok ? 'Секрет удалён' : ('Ошибка: ' + (j.detail || '?')));
    loadVault();
  } catch (e) {
    toast('Ошибка сети');
  }
}

/* Токен админа хранится только в памяти вкладки, не в localStorage:
 * иначе он пережил бы перезагрузку и мог утечь на чужом компьютере. */
let _adminToken = '';
function setAdminToken(t) { _adminToken = t || ''; }
function adminToken() { return _adminToken; }
function askAdminToken() {
  const t = prompt('Введите ADMIN_TOKEN (нужен для работы с секретами):');
  if (t) { setAdminToken(t.trim()); loadVault(); }
  return !!t;
}

/* =================== Старт =================== */
$('#bSide').onclick = toggleSide;

// На старте: если это телефон, панель проекта свёрнута — она появляется
// по кнопке. На десктопе восстанавливаем сохранённое состояние.
if (isMobile()) {
  $('#side').classList.add('collapsed');
  state.sidebar = false;
} else if (!state.sidebar) {
  $('#side').classList.add('collapsed');
}

$('#in').focus();
updateInstallUI();

(async function initApp() {
  if (!welcomeTemplate && $('#welcome')) {
    welcomeTemplate = $('#welcome').outerHTML;
  }
  await loadProjects();
  await switchProject(state.project);
  loadStatus();
  loadVault();
})();
setInterval(loadStatus, 30000);
setInterval(() => { if (!state.busy) loadTree(); }, 12000);