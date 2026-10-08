// AI Wife Coach - Client Script
let activeSessionId = localStorage.getItem('ai_wife_session_id') || null;
let isVoiceOutputEnabled = true;

// Tab Switching
function switchTab(tabName) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
    const target = document.getElementById(`tab-${tabName}`);
    if (target) target.classList.remove('hidden');

    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.classList.remove('text-pink-600', 'font-semibold');
        btn.classList.add('text-slate-400', 'font-medium');
    });

    const activeBtn = document.querySelector(`[data-tab="${tabName}"]`);
    if (activeBtn) {
        activeBtn.classList.remove('text-slate-400', 'font-medium');
        activeBtn.classList.add('text-pink-600', 'font-semibold');
    }

    if (tabName === 'library') loadBooks();
    if (tabName === 'tasks') loadTasks();
    if (tabName === 'coach') loadSessions();
}

// COACH CHAT
async function sendChatMessage(presetText = null) {
    const input = document.getElementById('chat-input');
    const text = presetText || (input ? input.value.trim() : '');
    if (!text) return;

    if (!presetText && input) input.value = '';

    const messagesContainer = document.getElementById('chat-messages');
    if (!messagesContainer) return;

    // Append user message bubble
    const userDiv = document.createElement('div');
    userDiv.className = 'flex items-end justify-end space-x-2';
    userDiv.innerHTML = `
        <div class="bg-gradient-to-r from-pink-500 to-purple-600 text-white rounded-2xl p-3.5 max-w-[85%] text-sm shadow-sm break-words">
            ${escapeHtml(text)}
        </div>
        <div class="w-8 h-8 rounded-full bg-purple-200 flex items-center justify-center text-sm flex-shrink-0">👤</div>
    `;
    messagesContainer.appendChild(userDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;

    // Loading indicator
    const loadingId = 'loading-' + Date.now();
    const loadingDiv = document.createElement('div');
    loadingDiv.id = loadingId;
    loadingDiv.className = 'flex items-start space-x-2';
    loadingDiv.innerHTML = `
        <div class="w-8 h-8 rounded-full bg-pink-200 flex items-center justify-center text-sm flex-shrink-0 animate-pulse">💖</div>
        <div class="bg-pink-50/80 rounded-2xl p-3.5 text-sm text-pink-500 border border-pink-100 italic">Слушаю тебя, дорогая...</div>
    `;
    messagesContainer.appendChild(loadingDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;

    try {
        const payload = { message: text };
        if (activeSessionId) payload.session_id = activeSessionId;

        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const data = await response.json();
        const loadEl = document.getElementById(loadingId);
        if (loadEl) loadEl.remove();

        if (data.session_id) {
            activeSessionId = data.session_id;
            localStorage.setItem('ai_wife_session_id', activeSessionId);
            loadSessions();
        }

        const replyText = data.reply || data.response || data.answer || 'Я рядом с тобой, милая.';
        const gentleQ = data.gentle_question ? `<div class="mt-2 pt-2 border-t border-pink-100 text-xs text-purple-700 font-medium">✨ ${escapeHtml(data.gentle_question)}</div>` : '';

        const replyDiv = document.createElement('div');
        replyDiv.className = 'flex items-start space-x-2';
        replyDiv.innerHTML = `
            <div class="w-8 h-8 rounded-full bg-pink-200 flex items-center justify-center text-sm flex-shrink-0">💖</div>
            <div class="bg-pink-50/80 rounded-2xl p-3.5 max-w-[85%] text-sm border border-pink-100 shadow-sm text-slate-700 break-words">
                ${escapeHtml(replyText)}
                ${gentleQ}
            </div>
        `;
        messagesContainer.appendChild(replyDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;

        // Speak reply softly
        if (isVoiceOutputEnabled) {
            speakText(replyText);
        }
    } catch (e) {
        console.error('Chat error:', e);
        const loadEl = document.getElementById(loadingId);
        if (loadEl) loadEl.remove();

        const errDiv = document.createElement('div');
        errDiv.className = 'text-xs text-rose-500 text-center py-2';
        errDiv.innerText = 'Сервер на связи. Пожалуйста, попробуй отправить ещё раз.';
        messagesContainer.appendChild(errDiv);
    }
}

function sendMood(mood) {
    sendChatMessage(`Мне сейчас ${mood.toLowerCase()}, побудь со мной.`);
}

function clearChat() {
    activeSessionId = null;
    localStorage.removeItem('ai_wife_session_id');
    const messagesContainer = document.getElementById('chat-messages');
    if (messagesContainer) {
        messagesContainer.innerHTML = `
            <div class="flex items-start space-x-2">
                <div class="w-8 h-8 rounded-full bg-pink-200 flex items-center justify-center text-sm flex-shrink-0">💖</div>
                <div class="bg-pink-50/80 rounded-2xl p-3.5 max-w-[85%] text-sm border border-pink-100 shadow-sm">
                    Новый разговор начат. О чём тебе хочется поговорить сейчас, милая?
                </div>
            </div>
        `;
    }
    loadSessions();
}

function handleChatKey(e) {
    if (e.key === 'Enter') sendChatMessage();
}

// VOICE INPUT
function toggleVoice() {
    const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRec) {
        alert('Голосовой ввод не поддерживается браузером. Попробуйте Chrome или Safari.');
        return;
    }

    const recognition = new SpeechRec();
    recognition.lang = 'ru-RU';
    recognition.interimResults = false;
    
    const btn = document.getElementById('voice-btn');
    if (btn) btn.classList.add('bg-pink-500', 'text-white', 'animate-pulse');

    recognition.onresult = function(event) {
        if (event.results && event.results[0]) {
            const transcript = event.results[0][0].transcript;
            const input = document.getElementById('chat-input');
            if (input) input.value = transcript;
        }
        if (btn) btn.classList.remove('bg-pink-500', 'text-white', 'animate-pulse');
    };

    recognition.onerror = function(err) {
        console.warn('Speech error:', err);
        if (btn) btn.classList.remove('bg-pink-500', 'text-white', 'animate-pulse');
    };

    recognition.onend = function() {
        if (btn) btn.classList.remove('bg-pink-500', 'text-white', 'animate-pulse');
    };

    recognition.start();
}

// VOICE OUTPUT (TTS)
function speakText(text) {
    if (!('speechSynthesis' in window)) return;
    try {
        window.speechSynthesis.cancel();
        const clean = text.replace(/[*_#✨💖🌸☕️💡👤]/g, '');
        const utterance = new SpeechSynthesisUtterance(clean);
        utterance.lang = 'ru-RU';
        utterance.rate = 0.95;
        utterance.pitch = 1.05;
        
        const voices = window.speechSynthesis.getVoices();
        const ruVoice = voices.find(v => v.lang.startsWith('ru') && (v.name.includes('Milena') || v.name.includes('Yuri') || v.name.includes('Google') || v.name.includes('Tatyana')));
        if (ruVoice) utterance.voice = ruVoice;

        window.speechSynthesis.speak(utterance);
    } catch (e) {
        console.warn('TTS error:', e);
    }
}

// MULTI-CHAT SESSIONS
async function loadSessions() {
    try {
        const res = await fetch('/api/sessions');
        const sessions = await res.json();
        const container = document.getElementById('chat-sessions-list');
        if (!container) return;
        
        if (!sessions || sessions.length === 0) {
            container.innerHTML = '<div class="text-[11px] text-pink-400 p-2">История диалогов пока пуста</div>';
            return;
        }

        container.innerHTML = sessions.map(s => `
            <button onclick="switchSession('${s.id}')" class="text-left w-full text-xs p-2 rounded-xl transition truncate ${activeSessionId === s.id ? 'bg-pink-200 text-pink-900 font-semibold' : 'hover:bg-pink-100/60 text-slate-600'}">
                💬 ${escapeHtml(s.title || 'Разговор')}
            </button>
        `).join('');
    } catch (e) {
        console.warn('Load sessions err:', e);
    }
}

async function switchSession(sid) {
    activeSessionId = sid;
    localStorage.setItem('ai_wife_session_id', sid);
    loadSessions();

    try {
        const res = await fetch(`/api/sessions/${sid}/messages`);
        const messages = await res.json();
        const messagesContainer = document.getElementById('chat-messages');
        if (!messagesContainer) return;

        messagesContainer.innerHTML = '';
        if (messages && messages.length > 0) {
            messages.forEach(m => {
                if (m.role === 'user') {
                    messagesContainer.innerHTML += `
                        <div class="flex items-end justify-end space-x-2">
                            <div class="bg-gradient-to-r from-pink-500 to-purple-600 text-white rounded-2xl p-3.5 max-w-[85%] text-sm shadow-sm break-words">
                                ${escapeHtml(m.content)}
                            </div>
                            <div class="w-8 h-8 rounded-full bg-purple-200 flex items-center justify-center text-sm flex-shrink-0">👤</div>
                        </div>
                    `;
                } else {
                    const gentleQ = m.gentle_question ? `<div class="mt-2 pt-2 border-t border-pink-100 text-xs text-purple-700 font-medium">✨ ${escapeHtml(m.gentle_question)}</div>` : '';
                    messagesContainer.innerHTML += `
                        <div class="flex items-start space-x-2">
                            <div class="w-8 h-8 rounded-full bg-pink-200 flex items-center justify-center text-sm flex-shrink-0">💖</div>
                            <div class="bg-pink-50/80 rounded-2xl p-3.5 max-w-[85%] text-sm border border-pink-100 shadow-sm text-slate-700 break-words">
                                ${escapeHtml(m.content)}
                                ${gentleQ}
                            </div>
                        </div>
                    `;
                }
            });
        }
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    } catch (e) {
        console.warn('Load session messages err:', e);
    }
}

// GERMAN TRAINER
let currentFlashcards = [];
let currentCardIndex = 0;
let isCardFlipped = false;

async function loadGermanFlashcards(level = 'A1', btnEl = null) {
    document.querySelectorAll('.german-level-btn').forEach(btn => {
        btn.className = 'german-level-btn bg-purple-100 text-purple-700 px-4 py-1.5 rounded-full text-xs font-medium';
    });
    if (btnEl) {
        btnEl.className = 'german-level-btn bg-purple-600 text-white px-4 py-1.5 rounded-full text-xs font-medium shadow';
    }

    try {
        const res = await fetch(`/api/german/card?level=${level}`);
        const data = await res.json();
        currentFlashcards = Array.isArray(data) ? data : [data];
        currentCardIndex = 0;
        isCardFlipped = false;
        renderFlashcard();
    } catch(e) {
        console.warn('German card error:', e);
    }
}

function renderFlashcard() {
    if (!currentFlashcards.length) return;
    const card = currentFlashcards[currentCardIndex % currentFlashcards.length];
    const word = card.word || card.de || '';
    const translation = card.translation || card.ru || '';
    const example = card.example || card.hint || card.de || '';

    const elLevel = document.getElementById('fc-level');
    const elWord = document.getElementById('fc-word');
    const elTrans = document.getElementById('fc-translation');
    const elEx = document.getElementById('fc-example');

    if (elLevel) elLevel.innerText = card.level || 'A1';
    if (elWord) elWord.innerText = isCardFlipped ? translation : word;
    if (elTrans) {
        elTrans.innerText = translation;
        elTrans.classList.toggle('hidden', !isCardFlipped);
    }
    if (elEx) {
        elEx.innerText = `Пример: ${example}`;
        elEx.classList.toggle('hidden', !isCardFlipped);
    }
}

function flipCard() {
    isCardFlipped = !isCardFlipped;
    renderFlashcard();
    if (!isCardFlipped) {
        currentCardIndex++;
        renderFlashcard();
    }
}

async function checkGermanSentence() {
    const input = document.getElementById('german-input');
    const text = input ? input.value.trim() : '';
    if (!text) return;

    try {
        const res = await fetch('/api/german/check', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sentence: text, german_text: text, user_translation: text })
        });
        const data = await res.json();
        const fb = document.getElementById('german-feedback');
        if (fb) {
            fb.classList.remove('hidden');
            const feedbackText = data.feedback || data.message || 'Отлично! Твоя практика зафиксирована.';
            fb.innerHTML = `<strong>Результат:</strong> ${escapeHtml(feedbackText)}`;
        }
    } catch(e) {
        console.error(e);
    }
}

// LIBRARY
async function loadBooks() {
    try {
        const res = await fetch('/api/books');
        const books = await res.json();
        renderBooks(books);
    } catch(e) {
        console.error(e);
    }
}

function renderBooks(books) {
    const container = document.getElementById('books-list');
    if (!container) return;
    if (!books || !books.length) {
        container.innerHTML = '<div class="text-xs text-slate-400 p-4">Книг пока нет</div>';
        return;
    }
    container.innerHTML = books.map(b => `
        <div class="bg-amber-50/50 border border-amber-100 p-4 rounded-2xl shadow-sm flex flex-col justify-between">
            <div>
                <h3 class="font-bold text-slate-800 text-sm">${escapeHtml(b.title || '')}</h3>
                <p class="text-xs text-amber-800 italic mt-1">«${escapeHtml(b.excerpt || b.quote || '')}»</p>
            </div>
            <div class="text-[10px] text-slate-400 mt-3 pt-2 border-t border-amber-100/60">${escapeHtml(b.author || 'Психология')}</div>
        </div>
    `).join('');
}

async function searchBooks() {
    const input = document.getElementById('book-search');
    const q = input ? input.value.trim() : '';
    try {
        const res = await fetch(`/api/books?q=${encodeURIComponent(q)}`);
        const books = await res.json();
        renderBooks(books);
    } catch(e) {
        console.error(e);
    }
}

// TASKS
async function loadTasks() {
    try {
        const res = await fetch('/api/tasks');
        const tasks = await res.json();
        renderTasks(tasks);
    } catch(e) {
        console.error(e);
    }
}

function renderTasks(tasks) {
    const container = document.getElementById('tasks-list');
    if (!container) return;
    if (!tasks || !tasks.length) {
        container.innerHTML = '<div class="text-xs text-slate-400 p-3">Список забот пока пуст</div>';
        return;
    }
    container.innerHTML = tasks.map(t => {
        const taskId = String(t.id);
        return `
            <div class="flex items-center justify-between p-3 bg-pink-50/40 border border-pink-100 rounded-2xl shadow-sm">
                <div class="flex items-center space-x-3">
                    <input type="checkbox" ${t.completed ? 'checked' : ''} onchange="toggleTask('${escapeHtml(taskId)}')" class="w-4 h-4 text-pink-600 rounded border-pink-300 focus:ring-pink-400 cursor-pointer">
                    <span class="text-sm ${t.completed ? 'line-through text-slate-400' : 'text-slate-700 font-medium'}">${escapeHtml(t.title || '')}</span>
                </div>
                <button onclick="deleteTask('${escapeHtml(taskId)}')" class="text-slate-400 hover:text-red-500 text-xs px-2 py-1 transition">✕</button>
            </div>
        `;
    }).join('');
}

async function addNewTask() {
    const input = document.getElementById('new-task-input');
    const title = input ? input.value.trim() : '';
    if (!title) return;

    try {
        await fetch('/api/tasks', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title })
        });
        if (input) input.value = '';
        loadTasks();
    } catch(e) { console.error(e); }
}

async function toggleTask(id) {
    try {
        await fetch(`/api/tasks/${encodeURIComponent(id)}/toggle`, { method: 'POST' });
        loadTasks();
    } catch(e) { console.error(e); }
}

async function deleteTask(id) {
    try {
        await fetch(`/api/tasks/${encodeURIComponent(id)}`, { method: 'DELETE' });
        loadTasks();
    } catch(e) { console.error(e); }
}

function handleTaskKey(e) {
    if (e.key === 'Enter') addNewTask();
}

function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
    return String(text).replace(/[&<>"']/g, function(m) { return map[m]; });
}

// SAFE INITIALIZATION ON DOM READY
document.addEventListener('DOMContentLoaded', () => {
    try {
        loadGermanFlashcards('A1');
        loadTasks();
        loadSessions();
    } catch (e) {
        console.error('Init error:', e);
    }
});
