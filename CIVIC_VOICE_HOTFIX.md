# Civic Voice Hotfix — 2026-08-29

- Moved Civic Voice into an isolated external JavaScript module so errors elsewhere on report.html cannot disable the voice button.
- Added explicit microphone permission request before speech recognition.
- Added detailed microphone and speech-recognition error messages.
- Added runtime status states: ready, requesting permission, listening, speech detected, transcribing, success, and error.
- Added safe transcript insertion into the issue description and automatic title suggestion.
- Preserved English (en-IN), Hindi (hi-IN), and Marathi (mr-IN) language modes.

Important: this remains browser-based speech-to-text. It does not yet perform AI intent extraction/category classification.
