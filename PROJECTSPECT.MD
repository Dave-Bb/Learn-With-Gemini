# Project Specification: Ghost Tutor (Gemini Live Hackathon)

## Overview
Ghost Tutor is a real-time, vision-enabled AI assistant designed to break the "text box" paradigm. It observes the user's screen, listens to their microphone, speaks back with natively generated audio, and physically points to UI elements on the user's screen using a transparent overlay. 

**Hackathon Track:** Live Agents 🗣️ (Also touches UI Navigator ☸️)
**Core Tech:** Gemini Multimodal Live API, Google GenAI SDK, Google Cloud Run, PyQt6, FastAPI.

## System Architecture
The application is split into two components to satisfy the Hackathon's Cloud Hosting requirement while maintaining a lightweight desktop presence.

1.  **Cloud Relay (FastAPI - Backend)**
    * **Host:** Google Cloud Run.
    * **Role:** Acts as the secure WebSocket proxy between the Desktop Client and the Gemini Live API. It holds the Google API keys and manages the session configuration, including the system instructions and tool definitions (function declarations).
2.  **Ghost Client (Python/PyQt6 - Frontend)**
    * **Host:** User's local machine.
    * **Role:** Captures microphone audio (16kHz PCM) and screen frames (1 FPS via `mss`). It streams these to the Cloud Relay. It also runs a frameless, 100% transparent PyQt6 window that ignores mouse clicks. When it receives a `draw_hint` command from the backend, it renders graphics (arrows, text boxes) onto this transparent canvas.

## API Contracts & Data Flow

### WebSocket Connection (`ws://[CLOUD_RUN_URL]/ws`)
The Desktop Client connects to the FastAPI backend via a single WebSocket. Communication is bidirectional and uses JSON payloads.

**Client -> Server (Uplink)**
* **Audio Data:** `{"type": "audio", "data": "<base64_encoded_pcm_16000hz>"}`
* **Video Frame:** `{"type": "image", "data": "<base64_encoded_jpeg>", "mime_type": "image/jpeg"}`

**Server -> Client (Downlink)**
* **Audio Output:** `{"type": "audio", "data": "<base64_encoded_pcm_24000hz>"}`
* **Tool Call (UI Overlay):** `{"type": "tool_call", "function": "draw_hint", "args": {"x": 100, "y": 200, "text": "Click here", "hint_type": "arrow"}}`
* **Clear Overlay:** `{"type": "clear_hint"}`

## Setup Instructions
1. `pip install fastapi uvicorn google-genai websockets` (Backend)
2. `pip install PyQt6 mss pyaudio websockets` (Frontend)
3. Set `GOOGLE_API_KEY` in the backend environment.