(function () {
  'use strict';

  const state = {
    recognition: null,
    listening: false,
    finalText: ''
  };

  function el(id) {
    return document.getElementById(id);
  }

  function setStatus(message, level) {
    const node = el('voiceReportStatus');
    if (!node) return;
    node.textContent = message;
    node.dataset.state = level || 'info';
  }

  function setButton(listening) {
    const button = el('voiceReportButton');
    if (!button) return;
    button.disabled = listening;
    button.textContent = listening ? '🎙 Listening…' : '🎙 Start Voice Report';
  }

  function getRecognitionConstructor() {
    return window.SpeechRecognition || window.webkitSpeechRecognition || null;
  }

  async function ensureMicrophonePermission() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error('This browser cannot request microphone access.');
    }

    // Explicitly request microphone access so failures are visible instead of
    // being hidden inside the browser speech-recognition service.
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    stream.getTracks().forEach(function (track) { track.stop(); });
  }

  function describeMicError(error) {
    const name = error && error.name ? error.name : '';
    if (name === 'NotAllowedError' || name === 'PermissionDeniedError') {
      return 'Microphone permission is blocked. Click the lock/site icon near the address bar → Microphone → Allow, then try again.';
    }
    if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
      return 'No microphone was detected. Connect/enable a microphone and try again.';
    }
    if (name === 'NotReadableError' || name === 'TrackStartError') {
      return 'The microphone is busy or unavailable. Close other apps using the microphone and try again.';
    }
    return (error && error.message) ? error.message : 'Microphone access failed.';
  }

  function speechErrorMessage(code) {
    const map = {
      'not-allowed': 'Speech recognition was blocked. Allow microphone access for this site and retry.',
      'service-not-allowed': 'The browser speech-recognition service is blocked by browser or system policy.',
      'audio-capture': 'The browser could not capture microphone audio.',
      'no-speech': 'No speech was detected. Speak clearly and try again.',
      'network': 'The browser speech-recognition service could not reach its online service. Check internet connection or try Chrome.',
      'aborted': 'Voice capture was stopped before speech was recognized.',
      'language-not-supported': 'The selected language is not supported by this browser speech service.'
    };
    return map[code] || ('Voice recognition error: ' + code + '.');
  }

  function applyTranscript(text) {
    const description = el('reportDescription');
    if (!description) {
      setStatus('Voice was captured, but the report description field could not be found.', 'error');
      return;
    }

    description.value = (text || '').trim();
    description.dispatchEvent(new Event('input', { bubbles: true }));

    const title = el('reportTitle');
    if (title && !title.value.trim() && description.value.trim()) {
      const words = description.value.trim().split(/\s+/).slice(0, 10).join(' ');
      title.value = words.slice(0, 78);
      title.dispatchEvent(new Event('input', { bubbles: true }));
    }
  }

  async function startCivicVoice() {
    if (state.listening) return;

    const SpeechRecognition = getRecognitionConstructor();
    if (!SpeechRecognition) {
      setStatus('This browser does not expose SpeechRecognition. Open CivicOS in current Google Chrome for this free browser-based voice mode.', 'error');
      return;
    }

    setButton(true);
    setStatus('Requesting microphone permission…', 'working');

    try {
      await ensureMicrophonePermission();
    } catch (error) {
      setButton(false);
      setStatus(describeMicError(error), 'error');
      return;
    }

    const recognition = new SpeechRecognition();
    state.recognition = recognition;
    state.finalText = '';
    state.listening = true;

    recognition.lang = (el('voiceLanguage') && el('voiceLanguage').value) || 'en-IN';
    recognition.interimResults = true;
    recognition.continuous = false;
    recognition.maxAlternatives = 1;

    recognition.onstart = function () {
      setStatus('Listening now — speak your civic issue naturally.', 'working');
    };

    recognition.onaudiostart = function () {
      setStatus('Microphone connected. Speak now…', 'working');
    };

    recognition.onspeechstart = function () {
      setStatus('Speech detected — transcribing…', 'working');
    };

    recognition.onresult = function (event) {
      let interim = '';
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          state.finalText += transcript + ' ';
        } else {
          interim += transcript;
        }
      }

      const combined = (state.finalText + interim).trim();
      if (combined) applyTranscript(combined);
      setStatus(interim ? ('Transcribing: ' + interim) : 'Voice captured. Review the generated description before submitting.', 'success');
    };

    recognition.onerror = function (event) {
      setStatus(speechErrorMessage(event.error), 'error');
    };

    recognition.onend = function () {
      state.listening = false;
      state.recognition = null;
      setButton(false);
      if (state.finalText.trim()) {
        applyTranscript(state.finalText.trim());
        setStatus('Voice captured successfully. Review/edit the description, confirm location and submit.', 'success');
      } else if (el('voiceReportStatus') && !/error|blocked|failed|No speech/i.test(el('voiceReportStatus').textContent)) {
        setStatus('Voice capture ended without a final transcript. Try again and speak after “Listening now” appears.', 'warning');
      }
    };

    try {
      recognition.start();
    } catch (error) {
      state.listening = false;
      state.recognition = null;
      setButton(false);
      setStatus('Could not start browser speech recognition: ' + (error.message || error.name || 'unknown error'), 'error');
    }
  }

  function init() {
    const button = el('voiceReportButton');
    if (!button) return;

    button.addEventListener('click', function () {
      startCivicVoice();
    });

    // Expose for diagnostics in DevTools and compatibility with older markup.
    window.startCivicVoice = startCivicVoice;

    const ctor = getRecognitionConstructor();
    if (!window.isSecureContext) {
      setStatus('Microphone access requires HTTPS or localhost/127.0.0.1. Open CivicOS through a secure/local URL.', 'warning');
    } else if (!ctor) {
      setStatus('Voice recognition is unavailable in this browser. Use current Google Chrome for this browser-based mode.', 'warning');
    } else {
      setStatus('Voice ready. Click Start Voice Report; CivicOS will ask for microphone permission.', 'ready');
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
