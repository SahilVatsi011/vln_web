/**
 * ambient_ui.js — Minimal, auto-hiding UI overlays that appear
 * only when relevant. No buttons, just intelligent information display.
 */

(function () {
  'use strict';

  // ── Configuration ──────────────────────────────────────────
  const AUTO_HIDE_DELAY = 5000; // 5 seconds
  const POLL_INTERVAL = 2000;   // Poll state every 2 seconds

  // ── State ──────────────────────────────────────────────────
  let currentState = null;
  let lastWarnings = [];

  // ── Create ambient overlay elements ────────────────────────

  function createAmbientOverlay() {
    const overlay = document.createElement('div');
    overlay.id = 'ambient-overlay';
    overlay.className = 'ambient-overlay';
    document.body.appendChild(overlay);
    return overlay;
  }

  function createProgressRing() {
    const container = document.createElement('div');
    container.id = 'progress-ring';
    container.className = 'progress-ring';
    container.innerHTML = `
      <svg width="80" height="80">
        <circle class="ring-bg" cx="40" cy="40" r="32" />
        <circle class="ring-progress" cx="40" cy="40" r="32" />
      </svg>
      <div class="ring-text">
        <span class="ring-percent">0%</span>
        <span class="ring-label">Progress</span>
      </div>
    `;
    document.body.appendChild(container);
    return container;
  }

  function createSuggestionCards() {
    const container = document.createElement('div');
    container.id = 'suggestion-cards';
    container.className = 'suggestion-cards';
    document.body.appendChild(container);
    return container;
  }

  // ── Initialize elements ────────────────────────────────────
  const ambientOverlay = createAmbientOverlay();
  const progressRing = createProgressRing();
  const suggestionCards = createSuggestionCards();

  // ── Ambient overlay functions ──────────────────────────────

  function showAmbient(text, type = 'info', duration = AUTO_HIDE_DELAY) {
    ambientOverlay.textContent = text;
    ambientOverlay.className = `ambient-overlay show ${type}`;
    
    setTimeout(() => {
      ambientOverlay.classList.remove('show');
    }, duration);
  }

  function showWarning(text) {
    showAmbient('⚠️ ' + text, 'warning', 7000);
  }

  function showSuccess(text) {
    showAmbient('✓ ' + text, 'success', 3000);
  }

  function showInfo(text) {
    showAmbient(text, 'info', AUTO_HIDE_DELAY);
  }

  // ── Progress ring functions ────────────────────────────────

  function updateProgressRing(percent, label = 'Progress') {
    const circle = progressRing.querySelector('.ring-progress');
    const percentText = progressRing.querySelector('.ring-percent');
    const labelText = progressRing.querySelector('.ring-label');
    
    // Calculate circle dash offset (circumference = 2πr = 201)
    const circumference = 201;
    const offset = circumference - (percent / 100) * circumference;
    
    circle.style.strokeDashoffset = offset;
    percentText.textContent = Math.round(percent) + '%';
    labelText.textContent = label;
    
    // Color based on percentage
    if (percent < 30) {
      circle.style.stroke = 'var(--green, #10b981)';
    } else if (percent < 70) {
      circle.style.stroke = 'var(--cyan, #22d3ee)';
    } else if (percent < 90) {
      circle.style.stroke = 'var(--amber, #f59e0b)';
    } else {
      circle.style.stroke = 'var(--rose, #f43f5e)';
    }
  }

  function showProgressRing() {
    progressRing.classList.add('show');
  }

  function hideProgressRing() {
    progressRing.classList.remove('show');
  }

  // ── Suggestion cards functions ─────────────────────────────

  function showSuggestions(suggestions) {
    if (!suggestions || suggestions.length === 0) {
      suggestionCards.classList.remove('show');
      return;
    }

    suggestionCards.innerHTML = '<div class="suggestions-title">💡 Suggestions</div>';
    
    suggestions.forEach(suggestion => {
      const card = document.createElement('div');
      card.className = `suggestion-card priority-${suggestion.priority}`;
      card.innerHTML = `
        <span class="suggestion-icon">${suggestion.icon}</span>
        <span class="suggestion-text">${suggestion.text}</span>
      `;
      
      // Make it voice-selectable
      card.onclick = () => {
        if (typeof window.speakCommand === 'function') {
          window.speakCommand(suggestion.voice_command);
        }
        showInfo(`Executing: ${suggestion.text}`);
      };
      
      suggestionCards.appendChild(card);
    });
    
    suggestionCards.classList.add('show');
    
    // Auto-hide after 10 seconds
    setTimeout(() => {
      suggestionCards.classList.remove('show');
    }, 10000);
  }

  // ── Voice personality ──────────────────────────────────────

  const personalities = {
    professional: {
      budgetWarning: 'Step budget at {percent}%. Recommend completing mission.',
      lowTurns: 'LLM call budget low. Use simpler instructions.',
      missionComplete: 'Destination reached. Awaiting next instruction.',
      highTemp: 'GPU temperature elevated. Consider reducing workload.',
      highMemory: 'Memory usage high. Restart recommended.',
    },
    friendly: {
      budgetWarning: "Hey, we're at {percent}% of our steps! Maybe wrap this up soon? 😊",
      lowTurns: "We're running low on LLM calls. Let's keep it simple!",
      missionComplete: 'We made it! 🎉 That was fun. What should we do next?',
      highTemp: "It's getting a bit warm in here. Maybe we should take it easy?",
      highMemory: "Memory's getting full. A quick restart might help!",
    },
    minimal: {
      budgetWarning: '{percent}% steps used.',
      lowTurns: 'Low LLM budget.',
      missionComplete: 'Done.',
      highTemp: 'High temp.',
      highMemory: 'High memory.',
    }
  };

  let currentPersonality = 'friendly';

  function setPersonality(mode) {
    if (personalities[mode]) {
      currentPersonality = mode;
      showInfo(`Personality: ${mode}`);
    }
  }

  function speak(key, replacements = {}) {
    let text = personalities[currentPersonality][key];
    
    // Replace placeholders
    Object.keys(replacements).forEach(placeholder => {
      text = text.replace(`{${placeholder}}`, replacements[placeholder]);
    });
    
    // Use speech synthesis
    if (window.speechSynthesis) {
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.rate = 1.05;
      utterance.pitch = 1.0;
      utterance.volume = 1.0;
      
      const voices = window.speechSynthesis.getVoices();
      const englishVoice = voices.find(v => v.lang.startsWith('en'));
      if (englishVoice) {
        utterance.voice = englishVoice;
      }
      
      window.speechSynthesis.speak(utterance);
    }
    
    // Also show as ambient overlay
    showInfo(text);
  }

  // ── State polling and intelligence ─────────────────────────

  function pollRobotState() {
    fetch('/api/robot_state')
      .then(response => response.json())
      .then(state => {
        currentState = state;
        
        // Update progress ring
        updateProgressRing(state.progress_percent, 'Mission');
        
        // Check for new warnings
        state.warnings.forEach(warning => {
          const warningKey = `${warning.type}_${warning.severity}`;
          if (!lastWarnings.includes(warningKey)) {
            // New warning - speak it
            if (warning.type === 'low_steps') {
              speak('budgetWarning', { percent: Math.round(state.progress_percent) });
            } else if (warning.type === 'low_turns') {
              speak('lowTurns');
            }
            
            showWarning(warning.message);
            lastWarnings.push(warningKey);
          }
        });
        
        // Clear old warnings
        if (state.warnings.length === 0) {
          lastWarnings = [];
        }
        
        // Check if mission complete
        if (state.done && !state._completionAnnounced) {
          speak('missionComplete');
          state._completionAnnounced = true;
          
          // Load and show suggestions
          loadSuggestions();
        }
      })
      .catch(err => console.error('Failed to poll robot state:', err));
  }

  function pollSystemMetrics() {
    fetch('/api/system_metrics')
      .then(response => response.json())
      .then(metrics => {
        metrics.warnings.forEach(warning => {
          const warningKey = `${warning.type}_${warning.severity}`;
          if (!lastWarnings.includes(warningKey)) {
            if (warning.type === 'high_gpu_temp') {
              speak('highTemp');
            } else if (warning.type === 'high_memory') {
              speak('highMemory');
            }
            
            showWarning(warning.message);
            lastWarnings.push(warningKey);
          }
        });
      })
      .catch(err => console.error('Failed to poll system metrics:', err));
  }

  function loadSuggestions() {
    fetch('/api/suggestions')
      .then(response => response.json())
      .then(data => {
        if (data.suggestions && data.suggestions.length > 0) {
          showSuggestions(data.suggestions);
        }
      })
      .catch(err => console.error('Failed to load suggestions:', err));
  }

  // ── Voice commands ─────────────────────────────────────────

  function handleVoiceCommand(command) {
    const cmd = command.toLowerCase().trim();
    
    // Progress/status queries
    if (cmd.includes('progress') || cmd.includes('how far')) {
      if (currentState) {
        speak('budgetWarning', { percent: Math.round(currentState.progress_percent) });
        showProgressRing();
        setTimeout(hideProgressRing, 5000);
      }
    }
    
    // Steps remaining
    else if (cmd.includes('steps left') || cmd.includes('steps remaining')) {
      if (currentState) {
        showInfo(`${currentState.steps_remaining} steps remaining`);
        speak('budgetWarning', { percent: Math.round(currentState.progress_percent) });
      }
    }
    
    // Pending actions
    else if (cmd.includes("what's queued") || cmd.includes('pending')) {
      if (currentState && currentState.pending_actions.length > 0) {
        const summary = currentState.pending_actions
          .slice(0, 3)
          .map(a => `${a.action} ${a.value}`)
          .join(', ');
        showInfo(`Queued: ${summary}`);
      } else {
        showInfo('No actions queued');
      }
    }
    
    // Personality change
    else if (cmd.includes('friendly mode')) {
      setPersonality('friendly');
    } else if (cmd.includes('professional mode')) {
      setPersonality('professional');
    } else if (cmd.includes('minimal mode')) {
      setPersonality('minimal');
    }
    
    // System status
    else if (cmd.includes('system') || cmd.includes('performance')) {
      pollSystemMetrics();
    }
    
    // Suggestions
    else if (cmd.includes('suggest') || cmd.includes('what should')) {
      loadSuggestions();
    }
  }

  // ── Initialize ─────────────────────────────────────────────

  // Start polling
  setInterval(pollRobotState, POLL_INTERVAL);
  setInterval(pollSystemMetrics, POLL_INTERVAL * 3); // Poll metrics less frequently
  
  // Initial load
  pollRobotState();

  // ── Expose functions ───────────────────────────────────────
  window.showAmbient = showInfo;
  window.showWarning = showWarning;
  window.showSuccess = showSuccess;
  window.showProgressRing = showProgressRing;
  window.hideProgressRing = hideProgressRing;
  window.showSuggestions = showSuggestions;
  window.setPersonality = setPersonality;
  window.handleVoiceCommand = handleVoiceCommand;
  window.ambientSpeak = speak;
})();
