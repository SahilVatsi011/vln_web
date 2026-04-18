/**
 * dashboard.js — Log viewer, stats panel, controls, and SSE connection
 * for the live inference dashboard.
 */

(function () {
  'use strict';

  // ── Configuration ──────────────────────────────────────────
  const MAX_LOG_LINES = 500;
  const SCROLL_THRESHOLD = 40;

  // ── DOM references ─────────────────────────────────────────
  const log_element    = document.getElementById('log');
  const status_badge   = document.getElementById('status');
  const stat_instr     = document.getElementById('stat-instr');
  const stat_step      = document.getElementById('stat-step');
  const stat_action    = document.getElementById('stat-action');
  const stat_latency   = document.getElementById('stat-lat');
  const instr_input    = document.getElementById('instr-input');
  const set_button     = document.getElementById('set-btn');
  const pause_button   = document.getElementById('pause-btn');
  const filter_button  = document.getElementById('filter-btn');
  const scroll_button  = document.getElementById('scroll-btn');
  const cam_tag_right  = document.getElementById('cam-tag-r');
  const action_pill    = document.getElementById('action-pill');

  // ── State ──────────────────────────────────────────────────
  let is_paused = false;
  let is_auto_scroll = true;

  // ── Utilities ──────────────────────────────────────────────

  function get_timestamp() {
    return new Date().toTimeString().slice(0, 8);
  }

  function set_badge(text, css_class) {
    status_badge.innerHTML = '<span class="dot"></span> ' + text;
    status_badge.className = 'badge ' + css_class;
  }

  function set_paused(paused) {
    is_paused = paused;
    document.body.classList.toggle('is-paused', paused);
    pause_button.innerHTML = paused ? '&#9654; Resume' : '&#x23F8; Pause';

    if (paused) {
      set_badge('Paused', 'paused');
    } else {
      set_badge('Live', 'live');
    }
  }

  // ── Log line classification ────────────────────────────────

  function classify_line(text) {
    if (text.includes('***') ||
        text.includes('[RESTART]') ||
        text.includes('[INSTRUCTION]')) {
      return 'system';
    }
    if (text.includes('[Step'))        return 'step';
    if (text.includes('[Go1]') ||
        text.includes('DRY-RUN'))     return 'action';
    if (text.match(/Instruction\s*:/)) return 'instr';
    if (text.includes('Error') ||
        text.includes('Traceback'))   return 'err';
    if (text.toLowerCase().includes('warn')) return 'warn';
    return 'info';
  }

  // ── Log line parsing ──────────────────────────────────────

  function parse_step(text) {
    const match = text.match(
      /\[Step\s+(\d+)\]\s+([\d.]+)s\s*[\u2192\-\>]+\s*([A-Z][^(]*?)(?:\s{2,}|$)/
    );
    if (!match) return null;
    return {
      step: match[1],
      latency: parseFloat(match[2]),
      action: match[3].trim(),
    };
  }

  function parse_go1_action(text) {
    const match = text.match(/\[Go1\]\s+(.+?)\s+\(/);
    return match ? match[1].trim() : null;
  }

  // ── Add log line ───────────────────────────────────────────

  function add_line(text) {
    if (!text) return;

    const line_class = classify_line(text);
    const row = document.createElement('div');
    row.className = 'line ' + line_class;
    row.innerHTML = '<span class="ts"></span><span class="txt"></span>';
    row.children[0].textContent = get_timestamp();
    row.children[1].textContent = text;
    log_element.appendChild(row);

    // Trim old lines
    if (log_element.children.length > MAX_LOG_LINES) {
      log_element.removeChild(log_element.firstChild);
    }

    if (is_auto_scroll) {
      log_element.scrollTop = log_element.scrollHeight;
    }

    // Update stats from parsed data
    update_stats_from_line(text);
  }

  function update_stats_from_line(text) {
    const step_info = parse_step(text);
    if (step_info) {
      stat_step.textContent    = '#' + step_info.step;
      stat_action.textContent  = step_info.action;
      stat_latency.textContent = step_info.latency > 0
        ? step_info.latency.toFixed(1) + 's'
        : '< 0.1s (cached)';
      cam_tag_right.textContent = 'STEP ' + step_info.step + ' · ' + step_info.action;
      action_pill.textContent   = step_info.action;
    }

    const go1_action = parse_go1_action(text);
    if (go1_action) {
      stat_action.textContent = go1_action;
      action_pill.textContent = go1_action;
    }

    const instr_match = text.match(/Instruction\s*:\s*(.+)/);
    if (instr_match) {
      stat_instr.textContent = instr_match[1].trim();
    }

    const new_instr_match = text.match(
      /NEW INSTRUCTION \*\*\*\s*[\u2192\-\>]+\s*(.+)/
    );
    if (new_instr_match) {
      stat_instr.textContent = new_instr_match[1].trim();
    }

    if (text.includes('PAUSED'))          set_paused(true);
    if (text.includes('RESUMED'))         set_paused(false);
    if (text.includes('NEW INSTRUCTION')) set_paused(false);
  }

  // ── Control actions ────────────────────────────────────────

  function set_instruction() {
    const value = instr_input.value.trim();
    if (!value) {
      instr_input.focus();
      return;
    }

    set_button.disabled = true;

    fetch('/set_instruction', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ instruction: value }),
    })
      .then(function (response) { return response.json(); })
      .then(function (data) {
        stat_instr.textContent = data.instruction;
        add_line('[INSTRUCTION] -> ' + data.instruction);
        instr_input.value = '';
      })
      .finally(function () {
        set_button.disabled = false;
        instr_input.focus();
      });
  }

  function toggle_pause() {
    const next_state = !is_paused;

    fetch('/pause', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ paused: next_state }),
    }).then(function () {
      set_paused(next_state);
      add_line(next_state ? '[PAUSED] by user' : '[RESUMED] by user');
    });
  }

  function restart_session() {
    if (!confirm('Restart inference session? Step counter will reset.')) {
      return;
    }

    fetch('/restart', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ instruction: '' }),
    }).then(function () {
      add_line('[RESTART] Session reset');
      stat_step.textContent    = '\u2014';
      stat_action.textContent  = '\u2014';
      stat_latency.textContent = '\u2014';
      cam_tag_right.textContent = '\u2014';
      action_pill.textContent  = 'Awaiting instruction\u2026';
      clear_log();
      set_paused(true);
      instr_input.focus();
    });
  }

  function toggle_filter() {
    const is_on = !filter_button.classList.contains('on');
    filter_button.classList.toggle('on', is_on);
    document.body.classList.toggle('filter-on', is_on);
  }

  function clear_log() {
    log_element.innerHTML = '';
  }

  function scroll_to_bottom() {
    is_auto_scroll = true;
    log_element.scrollTop = log_element.scrollHeight;
    scroll_button.classList.remove('show');
  }

  // ── Event listeners ────────────────────────────────────────

  log_element.addEventListener('scroll', function () {
    const at_bottom = (
      log_element.scrollHeight - log_element.scrollTop - log_element.clientHeight
    ) < SCROLL_THRESHOLD;
    is_auto_scroll = at_bottom;
    scroll_button.classList.toggle('show', !at_bottom);
  });

  instr_input.addEventListener('keydown', function (event) {
    if (event.key === 'Enter') {
      set_instruction();
    }
  });

  // ── Initial state ──────────────────────────────────────────

  // "Important only" filter is ON by default
  document.body.classList.add('filter-on');

  // Load current instruction
  fetch('/get_instruction')
    .then(function (response) { return response.json(); })
    .then(function (data) {
      if (data.instruction) {
        stat_instr.textContent = data.instruction;
      }
    });

  // Connect SSE log stream
  const event_source = new EventSource('/events');

  event_source.onopen = function () {
    if (!is_paused) {
      set_badge('Live', 'live');
    }
  };

  event_source.onerror = function () {
    set_badge('Offline', 'offline');
  };

  event_source.onmessage = function (event) {
    add_line(event.data);
  };

  // ── Expose functions to HTML onclick attributes ────────────
  window.setInstruction  = set_instruction;
  window.togglePause     = toggle_pause;
  window.restartSession  = restart_session;
  window.toggleFilter    = toggle_filter;
  window.clearLog        = clear_log;
  window.scrollToBottom  = scroll_to_bottom;
  window.addLine         = add_line;  // Expose for voice_command.js
})();
