# Learn With Gemini

An interactive AI tutor that watches your screen, listens to your voice, speaks back, and draws overlay annotations to guide you through tutorials step by step.

Built for the Gemini Live Agent Challenge hackathon.

## What It Does

Learn With Gemini breaks the "text box" paradigm of traditional AI assistants. Instead of reading instructions and alt-tabbing between windows, you have a tutor that:

- Sees your screen in real time via periodic screen capture
- Listens to you speak and responds with natural audio (supports interruptions)
- Draws highlights, pointers, and text annotations directly on your screen using a transparent overlay
- Generates a step-by-step tutorial plan and tracks your progress as you work through it
- Reads your screen content (errors, code, terminal output) and responds to what it sees

You pick a topic (or type your own), and the tutor walks you through it conversationally while pointing at the actual UI elements on your screen.

## Architecture

```
Desktop Client (PyQt6)              Google Cloud (learn-with-gemini-2026)
+---------------------+             +----------------------------------+
|                     |             |                                  |
|  learn_with_gemini.py |           |  Cloud Run: learn-with-gemini-vision   |
|  session.py         |             |  +----------------------------+  |
|  overlay.py         |             |  | POST /generate-plan        |  |
|  audio.py           |   HTTPS     |  | POST /find-element         |  |
|                     +------------>|  | POST /analyze-screen       |  |
|  Vision requests    |             |  |                            |  |
|                     |             |  | Calls Gemini Vision API    |  |
|                     |             |  +----------------------------+  |
|                     |             |                                  |
|  Live API audio  +--------------->|  Gemini Live API (WebSocket)     |
|  (direct stream)    |             |  Audio model for conversation    |
+---------------------+             +----------------------------------+
```

**Two-model system:**

- Audio model (`gemini-2.5-flash-native-audio-preview`) handles the real-time voice conversation and tool calls via the Gemini Live API (WebSocket streaming)
- Vision model (`gemini-2.5-flash`) handles plan generation, UI element location, and screen reading via the standard Gemini API, hosted on Cloud Run

**Grid system:** Screenshots are captured at 1280x720 with a 16x9 grid overlay (columns A-P, rows 1-9). The vision model identifies UI elements by grid cell reference, which gets converted to screen coordinates for the overlay. The grid is invisible to the user.

## Tech Stack

- Python 3, PyQt6 (transparent overlay UI), mss (screen capture), PyAudio (mic/speaker)
- Google GenAI SDK (`google-genai`)
- Gemini Live API for real-time audio conversation
- Gemini Vision API for screen understanding
- Google Cloud Run (vision service backend)
- FastAPI + Docker (cloud service)

## Project Structure

```
learn_with_gemini.py  Main entry point, launcher UI
session.py            Gemini Live API session, two-model architecture, tool handlers
overlay.py            Transparent overlay widgets (highlights, pointers, text, tutorial panel)
audio.py              Mic capture (16kHz PCM) and speaker playback (24kHz PCM)
tools.py              Tool/function definitions for Gemini (5 tools)
requirements.txt      Desktop dependencies
deploy.bat            Automated Cloud Run deployment script
cloud/
  main.py             FastAPI vision service (3 endpoints)
  requirements.txt    Cloud service dependencies
  Dockerfile          Container definition for Cloud Run
```

## Setup

### Prerequisites

- Python 3.12+
- A Google Cloud account with billing enabled
- A Gemini API key (generate at https://aistudio.google.com/apikey)
- A working microphone and speakers
- Windows (tested on Windows 11, 2560x1440)

### Installation

```bash
git clone https://github.com/your-username/LearnWithMe.git
cd LearnWithMe
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```
GOOGLE_API_KEY=your-gemini-api-key-here
CLOUD_RUN_URL=https://learn-with-gemini-vision-740218009940.us-central1.run.app
```

### Running

```bash
python learn_with_gemini.py
```

This opens a launcher window where you pick a tutorial topic or type your own. The tutor will:

1. Generate a step-by-step plan (via Cloud Run)
2. Display the plan in a persistent side panel
3. Start speaking and guiding you through each step
4. Highlight UI elements on your screen when needed
5. Track your progress as you complete each step

### Cloud Deployment

The vision service is deployed on Google Cloud Run. To redeploy after changes:

```bash
deploy.bat
```

Or manually:

```bash
cd cloud
gcloud run deploy learn-with-gemini-vision --source . --region us-central1 --project learn-with-gemini-2026 --allow-unauthenticated --set-env-vars="GOOGLE_API_KEY=your-key" --memory=512Mi
```

See DEPLOYMENT.md for full deployment details and instructions for recording proof-of-deployment.

## Tools

The audio model can call 5 tools to draw on the user's screen:

| Tool | Purpose |
|---|---|
| `find_and_highlight` | Locate a UI element by description and highlight it (uses vision model) |
| `draw_text_box` | Show instruction text and update step progress |
| `draw_pointer` | Draw an arrow pointing at a screen location |
| `highlight_region` | Highlight a rectangular area |
| `clear_overlays` | Remove all overlay drawings |

## Known Limitations

- The Gemini Live API audio model occasionally disconnects with 1008 errors. The session auto-reconnects up to 5 times.
- Adding custom tools beyond the original 5 causes the audio model to crash. Tutorial state is managed client-side instead.
- Array-type parameters in tool definitions cause immediate disconnection.
- Screen capture and overlay are currently Windows-only (PyQt6 transparent window behavior differs on macOS/Linux).

## License

MIT
