/**
 * voice_command.js — Speech recognition and voice-controlled
 * instruction input with confirmation workflow.
 *
 * Flow: Listen → Transcribe → Confirm (yes/no) → Execute or Cancel
 */

(function () {
  'use strict';

  // ── Configuration ──────────────────────────────────────────
  const AUTO_CLOSE_DELAY_MS = 2000;
  const CONFIRM_CLOSE_DELAY_MS = 2500;
  const SUCCESS_CLOSE_DELAY_MS = 800;
  const CANCEL_CLOSE_DELAY_MS = 400;

  const YES_WORDS = [
    'yes', 'yeah', 'yep', 'confirm', 'confirmed', 'go',
    'do it', 'okay', 'ok', 'sure', 'proceed', 'execute',
    'affirmative',
  ];

  const NO_WORDS = [
    'no', 'nope', 'cancel', 'stop', 'abort', 'discard',
    'negative', "don't", 'nah',
  ];

  // ── DOM references ─────────────────────────────────────────
  const overlay    = document.getElementById('voice-overlay');
  const title_el   = document.getElementById('voice-title');
  const subtitle_el = document.getElementById('voice-subtitle');
  const transcript_el = document.getElementById('voice-transcript');
  const icon_el    = document.getElementById('voice-icon');
  const mic_button = document.getElementById('mic-btn');
  const instr_input = document.getElementById('instr-input');

  // ── State ──────────────────────────────────────────────────
  const SpeechRecognition = (
    window.SpeechRecognition || window.webkitSpeechRecognition
  );
  let recognition = null;
  let voice_state = 'idle';

  // ── Helpers ────────────────────────────────────────────────

  function set_voice_state(state) {
    voice_state = state;
    overlay.setAttribute('data-state', state);
  }

  function speak(text) {
    return new Promise(function (resolve) {
      const synth = window.speechSynthesis;
      synth.cancel();

      const utterance = new SpeechSynthesisUtterance(text);
      utterance.rate = 1.05;
      utterance.pitch = 1.0;
      utterance.volume = 1.0;

      // Prefer a Google English voice if available
      const voices = synth.getVoices();
      const google_voice = voices.find(function (voice) {
        return voice.lang.startsWith('en') && voice.name.includes('Google');
      });

      if (google_voice) {
        utterance.voice = google_voice;
      } else {
        const english_voice = voices.find(function (voice) {
          return voice.lang.startsWith('en');
        });
        if (english_voice) {
          utterance.voice = english_voice;
        }
      }

      utterance.onend = resolve;
      utterance.onerror = resolve;
      synth.speak(utterance);
    });
  }

  function close_voice() {
    overlay.classList.remove('active');
    voice_state = 'idle';
    mic_button.classList.remove('recording');
  }

  function show_error(title, subtitle, icon, close_delay) {
    title_el.textContent = title;
    subtitle_el.textContent = subtitle;
    set_voice_state('error');
    icon_el.innerHTML = icon;
    mic_button.classList.remove('recording');
    setTimeout(close_voice, close_delay);
  }

  // ── Voice command flow ─────────────────────────────────────

  function start_voice_command() {
    if (!SpeechRecognition) {
      alert('Speech Recognition is not supported in this browser. Please use Chrome.');
      return;
    }

    // Show overlay in listening state
    overlay.classList.add('active');
    set_voice_state('listening');
    title_el.textContent = 'Listening…';
    subtitle_el.textContent = 'Speak your navigation instruction clearly';
    transcript_el.textContent = '';
    icon_el.innerHTML = '&#127908;';
    mic_button.classList.add('recording');

    // Start speech recognition
    recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = 'en-US';
    recognition.maxAlternatives = 1;

    recognition.onresult = function (event) {
      let interim_text = '';
      let final_text = '';

      for (let index = 0; index < event.results.length; index++) {
        if (event.results[index].isFinal) {
          final_text += event.results[index][0].transcript;
        } else {
          interim_text += event.results[index][0].transcript;
        }
      }

      transcript_el.textContent = final_text || interim_text;

      if (final_text) {
        const transcript = final_text.trim();
        const lowerTranscript = transcript.toLowerCase();
        
        // Check if it's a query command (not a navigation instruction)
        if (lowerTranscript.includes('progress') || 
            lowerTranscript.includes('steps left') ||
            lowerTranscript.includes('steps remaining') ||
            lowerTranscript.includes('queued') ||
            lowerTranscript.includes('pending') ||
            lowerTranscript.includes('suggest') ||
            lowerTranscript.includes('what should') ||
            lowerTranscript.includes('system') ||
            lowerTranscript.includes('performance') ||
            lowerTranscript.includes('mode')) {
          
          // Handle as query, not instruction
          if (typeof window.handleVoiceCommand === 'function') {
            window.handleVoiceCommand(transcript);
          }
          
          set_voice_state('confirmed');
          icon_el.innerHTML = '&#10003;';
          title_el.textContent = 'Query received';
          subtitle_el.textContent = 'Processing...';
          mic_button.classList.remove('recording');
          
          setTimeout(close_voice, SUCCESS_CLOSE_DELAY_MS);
          return;
        }
        
        // Otherwise, proceed with normal instruction flow
        instr_input.value = transcript;
        start_confirmation(transcript);
      }
    };

    recognition.onerror = function (event) {
      console.error('Speech recognition error:', event.error);

      if (event.error === 'no-speech') {
        show_error('No speech detected', 'Please try again',
                   '&#128263;', AUTO_CLOSE_DELAY_MS);
      } else if (event.error === 'not-allowed') {
        show_error('Microphone blocked',
                   'Please allow microphone access and try again',
                   '&#128683;', AUTO_CLOSE_DELAY_MS);
      } else {
        show_error('Error occurred', event.error,
                   '&#9888;', AUTO_CLOSE_DELAY_MS);
      }
    };

    recognition.onend = function () {
      if (voice_state === 'listening') {
        show_error('No speech detected', 'Please try again',
                   '&#128263;', AUTO_CLOSE_DELAY_MS);
      }
    };

    recognition.start();
  }

  // ── Confirmation flow ──────────────────────────────────────

  async function start_confirmation(transcript) {
    set_voice_state('confirming');
    icon_el.innerHTML = '&#10067;';
    title_el.textContent = 'Confirm instruction?';
    subtitle_el.innerHTML = (
      'Say <strong style="color:var(--green)">"Yes"</strong> or ' +
      '<strong style="color:var(--green)">"Confirm"</strong> to execute, or ' +
      '<strong style="color:var(--rose)">"No"</strong> / ' +
      '<strong style="color:var(--rose)">"Cancel"</strong> to discard'
    );

    await speak('Your instruction is: ' + transcript + '. Shall I confirm?');

    // Listen for yes/no confirmation
    const confirm_recognition = new SpeechRecognition();
    confirm_recognition.continuous = false;
    confirm_recognition.interimResults = false;
    confirm_recognition.lang = 'en-US';
    confirm_recognition.maxAlternatives = 3;

    confirm_recognition.onresult = function (event) {
      const reply = event.results[0][0].transcript.toLowerCase().trim();
      console.log('Confirmation reply:', reply);

      const is_yes = YES_WORDS.some(function (word) {
        return reply.includes(word);
      });
      const is_no = NO_WORDS.some(function (word) {
        return reply.includes(word);
      });

      if (is_yes && !is_no) {
        handle_confirmed(transcript);
      } else {
        handle_cancelled();
      }
    };

    confirm_recognition.onerror = function (event) {
      console.error('Confirmation recognition error:', event.error);
      show_error(
        'Could not hear response',
        'Instruction kept in input — press Set to confirm manually',
        '&#9888;',
        CONFIRM_CLOSE_DELAY_MS
      );
    };

    confirm_recognition.onend = function () {
      if (voice_state === 'confirming') {
        show_error(
          'No response heard',
          'Instruction kept in input — press Set to confirm manually',
          '&#128263;',
          CONFIRM_CLOSE_DELAY_MS
        );
      }
    };

    confirm_recognition.start();
  }

  function handle_confirmed(transcript) {
    set_voice_state('confirmed');
    icon_el.innerHTML = '&#10003;';
    title_el.textContent = 'Confirmed!';
    subtitle_el.textContent = 'Executing instruction…';
    mic_button.classList.remove('recording');

    speak('Confirmed. Executing instruction now.').then(function () {
      // Trigger the set instruction action from dashboard.js
      if (typeof window.setInstruction === 'function') {
        window.setInstruction();
      }
      if (typeof window.addLine === 'function') {
        window.addLine('[VOICE] Instruction confirmed: ' + transcript);
      }
      setTimeout(close_voice, SUCCESS_CLOSE_DELAY_MS);
    });
  }

  function handle_cancelled() {
    set_voice_state('cancelled');
    icon_el.innerHTML = '&#10007;';
    title_el.textContent = 'Cancelled';
    subtitle_el.textContent = 'Instruction discarded';
    mic_button.classList.remove('recording');
    instr_input.value = '';

    speak('Cancelled.').then(function () {
      if (typeof window.addLine === 'function') {
        window.addLine('[VOICE] Instruction cancelled by user');
      }
      setTimeout(close_voice, SUCCESS_CLOSE_DELAY_MS);
    });
  }

  // ── Cancel ─────────────────────────────────────────────────

  function cancel_voice() {
    if (recognition) {
      try { recognition.abort(); } catch (error) { /* ignore */ }
    }
    window.speechSynthesis.cancel();
    mic_button.classList.remove('recording');
    set_voice_state('cancelled');
    icon_el.innerHTML = '&#10007;';
    title_el.textContent = 'Cancelled';
    subtitle_el.textContent = '';
    setTimeout(close_voice, CANCEL_CLOSE_DELAY_MS);
  }

  // ── Initialization ─────────────────────────────────────────

  // Preload voices (Chrome loads them asynchronously)
  if (window.speechSynthesis) {
    window.speechSynthesis.getVoices();
    window.speechSynthesis.onvoiceschanged = function () {
      window.speechSynthesis.getVoices();
    };
  }

  // Close voice overlay with Escape key
  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape' && overlay.classList.contains('active')) {
      cancel_voice();
    }
  });

  // ── Expose functions to HTML onclick attributes ────────────
  window.startVoiceCommand = start_voice_command;
  window.cancelVoice       = cancel_voice;
})();
