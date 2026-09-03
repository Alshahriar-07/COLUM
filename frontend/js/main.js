/**
 * COLUM Frontend - Main Application Logic
 */

(function() {
    'use strict';

    // Configuration
    const WS_URL = `ws://${window.location.hostname}:8766/ws`;
    const API_URL = `http://${window.location.hostname}:8765/api`;

    // State
    let ws = null;
    let reconnectAttempts = 0;
    const maxReconnectAttempts = 10;
    let currentTab = 'chat';
    let messageId = 0;

    // DOM Elements
    const elements = {
        statusDot: document.getElementById('statusDot'),
        statusText: document.getElementById('statusText'),
        chatMessages: document.getElementById('chatMessages'),
        messageInput: document.getElementById('messageInput'),
        sendBtn: document.getElementById('sendBtn'),
        micBtn: document.getElementById('micBtn'),
        voiceStatus: document.getElementById('voiceStatus'),
        clearChatBtn: document.getElementById('clearChatBtn'),
        navItems: document.querySelectorAll('.nav-item'),
        tabContents: document.querySelectorAll('.tab-content'),
        workspaceSelect: document.getElementById('workspaceSelect'),
        toolsGrid: document.getElementById('toolsGrid'),
        conversationHistory: document.getElementById('conversationHistory'),
        taskHistory: document.getElementById('taskHistory'),
        logLevelFilter: document.getElementById('logLevelFilter'),
        logsList: document.getElementById('logsList'),
        clearLogsBtn: document.getElementById('clearLogsBtn'),
        refreshLogsBtn: document.getElementById('refreshLogsBtn'),
        toastContainer: document.getElementById('toastContainer'),
        prefModel: document.getElementById('prefModel'),
        prefVoiceEnabled: document.getElementById('prefVoiceEnabled'),
        prefWakeWordEnabled: document.getElementById('prefWakeWordEnabled'),
        savePrefsBtn: document.getElementById('savePrefsBtn'),
    };

    // Initialize
    document.addEventListener('DOMContentLoaded', init);

    function init() {
        setupEventListeners();
        connectWebSocket();
        loadInitialData();
    }

    function setupEventListeners() {
        // Tab navigation
        elements.navItems.forEach(item => {
            item.addEventListener('click', () => switchTab(item.dataset.tab));
        });

        // Chat input
        elements.messageInput.addEventListener('keydown', handleInputKeydown);
        elements.sendBtn.addEventListener('click', sendMessage);
        elements.clearChatBtn.addEventListener('click', clearChat);

        // Voice button
        elements.micBtn.addEventListener('click', toggleVoiceInput);

        // Workspace selector
        elements.workspaceSelect.addEventListener('change', handleWorkspaceChange);

        // Logs
        elements.logLevelFilter.addEventListener('change', filterLogs);
        elements.clearLogsBtn.addEventListener('click', clearLogs);
        elements.refreshLogsBtn.addEventListener('click', loadLogs);

        // Preferences
        elements.savePrefsBtn.addEventListener('click', savePreferences);

        // Window controls
        document.getElementById('minimizeBtn').addEventListener('click', () => {
            if (window.electronAPI) {
                window.electronAPI.minimize();
            }
        });

        document.getElementById('closeBtn').addEventListener('click', () => {
            if (window.electronAPI) {
                window.electronAPI.close();
            }
        });

        document.getElementById('settingsBtn').addEventListener('click', () => {
            switchTab('memory');
        });
    }

    // WebSocket Connection
    function connectWebSocket() {
        ws = new WebSocket(WS_URL);

        ws.onopen = () => {
            console.log('WebSocket connected');
            reconnectAttempts = 0;
            updateConnectionStatus(true);
            showToast('Connected to COLUM backend', 'success');
        };

        ws.onclose = () => {
            console.log('WebSocket disconnected');
            updateConnectionStatus(false);
            attemptReconnect();
        };

        ws.onerror = (error) => {
            console.error('WebSocket error:', error);
        };

        ws.onmessage = (event) => {
            try {
                const message = JSON.parse(event.data);
                handleWebSocketMessage(message);
            } catch (e) {
                console.error('Failed to parse WebSocket message:', e);
            }
        };
    }

    function attemptReconnect() {
        if (reconnectAttempts >= maxReconnectAttempts) {
            showToast('Failed to reconnect to backend', 'error');
            return;
        }

        reconnectAttempts++;
        const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 30000);
        setTimeout(connectWebSocket, delay);
    }

    function updateConnectionStatus(connected) {
        if (connected) {
            elements.statusDot.classList.add('connected');
            elements.statusDot.classList.remove('error', 'listening', 'thinking');
            elements.statusText.textContent = 'Connected';
        } else {
            elements.statusDot.classList.remove('connected');
            elements.statusDot.classList.add('error');
            elements.statusText.textContent = 'Disconnected';
        }
    }

    function handleWebSocketMessage(message) {
        switch (message.type) {
            case 'connected':
                break;
            case 'pong':
                break;
            case 'assistant_state':
                updateAssistantState(message.data);
                break;
            case 'message':
                addMessage(message.data);
                break;
            case 'tool_started':
                addToolMessage(message.data, 'started');
                break;
            case 'tool_completed':
                addToolMessage(message.data, 'completed');
                break;
            default:
                console.log('Unknown message type:', message.type);
        }
    }

    function updateAssistantState(data) {
        const state = data.state || 'idle';
        elements.statusDot.classList.remove('connected', 'listening', 'thinking', 'error');

        switch (state) {
            case 'listening':
                elements.statusDot.classList.add('listening');
                elements.statusText.textContent = 'Listening...';
                elements.voiceStatus.textContent = 'Voice: Listening';
                break;
            case 'thinking':
                elements.statusDot.classList.add('thinking');
                elements.statusText.textContent = 'Thinking...';
                elements.voiceStatus.textContent = 'Voice: Processing';
                break;
            case 'speaking':
                elements.statusText.textContent = 'Speaking...';
                elements.voiceStatus.textContent = 'Voice: Speaking';
                break;
            case 'error':
                elements.statusDot.classList.add('error');
                elements.statusText.textContent = 'Error';
                elements.voiceStatus.textContent = 'Voice: Error';
                break;
            default:
                elements.statusDot.classList.add('connected');
                elements.statusText.textContent = 'Ready';
                elements.voiceStatus.textContent = 'Voice: Ready';
        }
    }

    // Chat Functions
    function handleInputKeydown(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    }

    function sendMessage() {
        const text = elements.messageInput.value.trim();
        if (!text) return;

        elements.messageInput.value = '';
        elements.messageInput.style.height = 'auto';

        // Add user message locally
        addMessage({
            sender: 'user',
            text: text,
            time: new Date().toISOString()
        });

        // Send to backend
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
                type: 'chat',
                message: text
            }));
        } else {
            showToast('Not connected to backend', 'error');
        }
    }

    function addMessage(data) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${data.sender || 'system'}`;

        const time = data.time ? new Date(data.time) : new Date();
        const timeStr = time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

        const senderNames = {
            user: 'You',
            system: 'COLUM',
            assistant: 'COLUM',
            tool: 'Tool',
            error: 'Error'
        };

        messageDiv.innerHTML = `
            <div class="message-avatar">${getAvatarChar(data.sender)}</div>
            <div class="message-content">
                <div class="message-header">
                    <span class="message-sender">${senderNames[data.sender] || data.sender}</span>
                    <span class="message-time">${timeStr}</span>
                </div>
                <div class="message-text">${escapeHtml(data.text || data.message || '')}</div>
            </div>
        `;

        elements.chatMessages.appendChild(messageDiv);
        scrollToBottom();
    }

    function addToolMessage(data, status) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message tool`;

        const time = new Date();
        const timeStr = time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

        const toolName = data.tool || 'Unknown Tool';
        const text = status === 'started'
            ? `Executing: ${toolName}${data.args ? ` (${JSON.stringify(data.args)})` : ''}`
            : `Completed: ${toolName}${data.result ? ` - ${JSON.stringify(data.result).substring(0, 200)}` : ''}`;

        messageDiv.innerHTML = `
            <div class="message-avatar">🔧</div>
            <div class="message-content">
                <div class="message-header">
                    <span class="message-sender">Tool ${status === 'started' ? 'Started' : 'Completed'}</span>
                    <span class="message-time">${timeStr}</span>
                </div>
                <div class="message-text">${escapeHtml(text)}</div>
            </div>
        `;

        elements.chatMessages.appendChild(messageDiv);
        scrollToBottom();
    }

    function clearChat() {
        elements.chatMessages.innerHTML = '';
        addMessage({
            sender: 'system',
            text: 'Chat cleared. How can I help you?',
            time: new Date().toISOString()
        });
    }

    function scrollToBottom() {
        elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
    }

    function getAvatarChar(sender) {
        const avatars = {
            user: 'U',
            system: 'C',
            assistant: 'C',
            tool: '🔧',
            error: '!'
        };
        return avatars[sender] || '?';
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Voice Input
    function toggleVoiceInput() {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
                type: 'voice_toggle'
            }));
        }
    }

    // Tab Switching
    function switchTab(tabName) {
        currentTab = tabName;

        elements.navItems.forEach(item => {
            item.classList.toggle('active', item.dataset.tab === tabName);
        });

        elements.tabContents.forEach(content => {
            content.classList.toggle('active', content.id === `${tabName}Tab`);
        });

        // Load tab-specific data
        if (tabName === 'logs') {
            loadLogs();
        } else if (tabName === 'memory') {
            loadMemoryData();
        }
    }

    // Workspace
    function handleWorkspaceChange(e) {
        const workspace = e.target.value;
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
                type: 'workspace_change',
                workspace: workspace
            }));
        }
    }

    // Logs
    function loadLogs() {
        fetch(`${API_URL}/logs`)
            .then(res => res.json())
            .then(data => renderLogs(data.logs || []))
            .catch(err => {
                console.error('Failed to load logs:', err);
                elements.logsList.innerHTML = '<p class="empty-state">Failed to load logs</p>';
            });
    }

    function renderLogs(logs) {
        if (!logs.length) {
            elements.logsList.innerHTML = '<p class="empty-state">No logs available</p>';
            return;
        }

        const filter = elements.logLevelFilter.value;
        const filtered = filter ? logs.filter(l => l.level === filter) : logs;

        elements.logsList.innerHTML = filtered.map(log => `
            <div class="log-entry">
                <span class="log-time">${new Date(log.timestamp).toLocaleTimeString()}</span>
                <span class="log-level ${log.level}">${log.level}</span>
                <span class="log-message">${escapeHtml(log.message)}</span>
            </div>
        `).join('');
    }

    function filterLogs() {
        loadLogs();
    }

    function clearLogs() {
        elements.logsList.innerHTML = '<p class="empty-state">Logs cleared</p>';
    }

    // Memory
    function loadMemoryData() {
        loadConversationHistory();
        loadTaskHistory();
        loadPreferences();
    }

    function loadConversationHistory() {
        fetch(`${API_URL}/memory/conversations`)
            .then(res => res.json())
            .then(data => renderConversationHistory(data.conversations || []))
            .catch(err => console.error('Failed to load conversations:', err));
    }

    function renderConversationHistory(conversations) {
        if (!conversations.length) {
            elements.conversationHistory.innerHTML = '<p class="empty-state">No conversation history yet</p>';
            return;
        }

        elements.conversationHistory.innerHTML = conversations.map(conv => `
            <div class="memory-item">
                <div class="memory-item-header">
                    <span class="memory-item-time">${new Date(conv.timestamp).toLocaleString()}</span>
                </div>
                <div class="memory-item-text">${escapeHtml(conv.text.substring(0, 200))}${conv.text.length > 200 ? '...' : ''}</div>
            </div>
        `).join('');
    }

    function loadTaskHistory() {
        fetch(`${API_URL}/memory/tasks`)
            .then(res => res.json())
            .then(data => renderTaskHistory(data.tasks || []))
            .catch(err => console.error('Failed to load tasks:', err));
    }

    function renderTaskHistory(tasks) {
        if (!tasks.length) {
            elements.taskHistory.innerHTML = '<p class="empty-state">No tasks completed yet</p>';
            return;
        }

        elements.taskHistory.innerHTML = tasks.map(task => `
            <div class="memory-item">
                <div class="memory-item-header">
                    <span class="memory-item-time">${new Date(task.timestamp).toLocaleString()}</span>
                    <span class="memory-item-status ${task.status}">${task.status}</span>
                </div>
                <div class="memory-item-text">${escapeHtml(task.description)}</div>
            </div>
        `).join('');
    }

    function loadPreferences() {
        fetch(`${API_URL}/config`)
            .then(res => res.json())
            .then(data => {
                if (data.openrouter) {
                    elements.prefModel.value = data.openrouter.mode || 'auto';
                }
            })
            .catch(err => console.error('Failed to load preferences:', err));
    }

    function savePreferences() {
        const prefs = {
            openrouter: {
                mode: elements.prefModel.value
            },
            voice: {
                stt_provider: elements.prefVoiceEnabled.checked ? 'whisper_local' : 'disabled',
                tts_provider: elements.prefVoiceEnabled.checked ? 'edge' : 'disabled'
            }
        };

        fetch(`${API_URL}/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(prefs)
        })
        .then(res => res.json())
        .then(() => showToast('Preferences saved', 'success'))
        .catch(err => {
            console.error('Failed to save preferences:', err);
            showToast('Failed to save preferences', 'error');
        });
    }

    // Initial Data Load
    function loadInitialData() {
        // Load tools
        fetch(`${API_URL}/tools`)
            .then(res => res.json())
            .then(data => renderTools(data.tools || []))
            .catch(err => console.error('Failed to load tools:', err));
    }

    function renderTools(tools) {
        // Tools are rendered statically in HTML for now
        // This could be enhanced to render dynamically
    }

    // Toast Notifications
    function showToast(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = `
            <span class="toast-message">${escapeHtml(message)}</span>
            <button class="toast-close">&times;</button>
        `;

        toast.querySelector('.toast-close').addEventListener('click', () => {
            toast.remove();
        });

        elements.toastContainer.appendChild(toast);

        setTimeout(() => {
            toast.style.animation = 'slideInRight 0.3s ease reverse';
            setTimeout(() => toast.remove(), 300);
        }, 5000);
    }

    // Send message to backend via HTTP (fallback)
    async function sendHttpMessage(message) {
        try {
            const res = await fetch(`${API_URL}/chat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message })
            });
            return await res.json();
        } catch (err) {
            console.error('HTTP chat failed:', err);
            throw err;
        }
    }

    // Expose globally for debugging
    window.COLUM = {
        sendMessage,
        showToast,
        switchTab,
        ws: () => ws
    };
})();