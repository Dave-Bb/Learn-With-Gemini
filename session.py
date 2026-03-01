"""
Gemini Live API session manager for Learn With Gemini.
Handles the bidirectional streaming: mic + screen → Gemini → audio + tool calls.
Auto-reconnects on server errors.
"""

import asyncio
import base64
import io
import os
import random
import re
import struct
import queue as thread_queue

from dotenv import load_dotenv
load_dotenv()

import aiohttp
import mss
from PIL import Image, ImageDraw, ImageFont
from google import genai
from google.genai import types

from audio import AudioManager
from overlay import OverlaySignals
from tools import ALL_TOOLS

MODEL = "gemini-2.5-flash-native-audio-preview-12-2025"
MAX_RECONNECTS = 5

# Grid overlay — drawn on screenshots for Gemini, invisible to the user
GRID_COLS = 16  # A-P
GRID_ROWS = 9   # 1-9

# Send images at this resolution — small enough for Gemini to process reliably,
# large enough for grid labels to be clearly readable
SEND_IMAGE_W = 1280
SEND_IMAGE_H = 720


_grid_saved = False  # save first grid image for debugging (reset to re-save after grid changes)


def draw_grid_on_image(img):
    """Draw a labeled grid onto a PIL image. Returns a copy with the grid."""
    global _grid_saved
    img = img.copy()
    draw = ImageDraw.Draw(img)
    w, h = img.size
    cell_w = w // GRID_COLS
    cell_h = h // GRID_ROWS

    # Load font — large centered label in each cell
    try:
        font_large = ImageFont.truetype("arial.ttf", 16)
    except Exception:
        font_large = ImageFont.load_default()

    line_color = (200, 200, 80)  # yellow — clearly visible

    # Vertical lines
    for i in range(1, GRID_COLS):
        x = i * cell_w
        draw.line([(x, 0), (x, h)], fill=line_color, width=2)

    # Horizontal lines
    for j in range(1, GRID_ROWS):
        y = j * cell_h
        draw.line([(0, y), (w, y)], fill=line_color, width=2)

    # Cell labels — LARGE centered text in each cell
    for col in range(GRID_COLS):
        for row in range(GRID_ROWS):
            label = f"{chr(65 + col)}{row + 1}"
            cx = col * cell_w + cell_w // 2
            cy = row * cell_h + cell_h // 2

            # Get text size for centering
            bbox = draw.textbbox((0, 0), label, font=font_large)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]

            lx = cx - tw // 2
            ly = cy - th // 2

            # Dark background behind label
            pad = 2
            draw.rectangle(
                [lx - pad, ly - pad, lx + tw + pad, ly + th + pad],
                fill=(0, 0, 0)
            )
            draw.text((lx, ly), label, fill=(255, 255, 80), font=font_large)

    # Save first grid image for debugging
    if not _grid_saved:
        try:
            img.save("debug_grid.png")
            print(f"[grid] Saved debug_grid.png ({w}x{h}, cell={cell_w}x{cell_h})")
        except Exception as e:
            print(f"[grid] Could not save debug image: {e}")
        _grid_saved = True

    return img


def grid_cell_to_rect(cell_name, screen_w, screen_h):
    """Convert a grid cell name like 'B3' to (x, y, w, h) in screen coordinates."""
    cell_name = cell_name.strip().upper()
    col = ord(cell_name[0]) - ord('A')
    row = int(cell_name[1:]) - 1

    col = max(0, min(col, GRID_COLS - 1))
    row = max(0, min(row, GRID_ROWS - 1))

    cell_w = screen_w // GRID_COLS
    cell_h = screen_h // GRID_ROWS

    return (col * cell_w, row * cell_h, cell_w, cell_h)

SYSTEM_PROMPT = """\
You are Learn With Gemini, a screen-aware teaching assistant. You see the user's screen, hear them speak, and speak back.

Tutorial: {topic}
Steps: {steps_text}

WORKFLOW:
- SPEAK instructions conversationally. One step at a time.
- Call draw_text_box ONCE per step with "Step N: <summary>" to update the progress tracker.
- Use find_and_highlight only when the user asks "where is that?" or "show me".
- Do NOT clutter the screen. Speak first, draw only when needed.

draw_text_box MUST contain "Step N: " or progress won't update.

[SCREEN UPDATE] messages describe what's on screen (errors, code, terminal output). \
If an error is reported, address it immediately.

Ignore grid lines/labels in screen images. Start speaking immediately.
"""

PLAN_PROMPT = """\
Create a step-by-step tutorial plan for: {topic}

Return ONLY short step descriptions, one per line. No numbers, no bullets, \
no extra text. Use 8-12 steps — break things down into small, clear actions. \
Each step should be a single concrete thing the user does. Example:

Open Visual Studio Code
Click File then New File
Select Python as the language
Type the print hello world code
Save the file with Ctrl+S
Choose a filename and location
Open the terminal with Ctrl+backtick
Type python and the filename to run it
Check the output says Hello World
Try changing the message and run again
"""

CALIBRATION_PROMPT = """\
You are a screen coordinate calibration assistant.

You can SEE the user's screen in real-time and HEAR them speaking.
You can SPEAK back and use tools to highlight areas on their screen.

Your ONLY job:
- The user will ask you to find things on their screen (buttons, menus, text, icons, etc.)
- Use find_and_highlight to locate and highlight the element
- Just describe what the user asked you to find — the system locates it precisely

There is a MAGENTA CIRCLE with crosshairs on the screen — this is a calibration target.
When the user asks you to find it, use find_and_highlight with description \
"the magenta circle with crosshairs" to highlight its area.

IMPORTANT: Start immediately! Say "Hi! I can see your screen. I can see the magenta \
calibration target. Tell me to highlight it whenever you're ready, or ask me to find \
anything else on screen." Then wait for their request.

Ignore any grid lines or labels in the screen images — those are for the system's \
internal use. Focus on the actual screen content.
"""

GREETING_PROMPT = """\
You are Learn With Gemini, a friendly screen-aware teaching assistant. \
You can see the user's screen, hear them speak, and speak back.

You just started. Greet the user warmly and briefly — say hello, welcome them, \
and let them know they can pick a tutorial from the menu on screen or just tell you \
what they'd like to learn about. Keep it short, friendly, and natural. \
Do NOT list tutorials yourself — the menu is already visible on screen.

When you receive a [TUTORIAL STARTED] message with a topic and steps, begin tutoring:
- SPEAK instructions conversationally. One step at a time.
- Call draw_text_box ONCE per step with "Step N: <summary>" to update the progress tracker.
- Use find_and_highlight only when the user asks "where is that?" or "show me".
- Do NOT clutter the screen. Speak first, draw only when needed.

draw_text_box MUST contain "Step N: " or progress won't update.

[SCREEN UPDATE] messages describe what's on screen (errors, code, terminal output). \
If an error is reported, address it immediately.

Ignore grid lines/labels in screen images.
"""


# Vision model — used for precise element location (much better than audio model)
VISION_MODEL = "gemini-3.1-flash-image-preview"

# Cloud Run URL — vision calls are routed through this service
CLOUD_RUN_URL = os.environ.get("CLOUD_RUN_URL", "")

VISION_PROMPT = """\
Look at this screenshot. It has a grid overlay with columns A-P (left to right) \
and rows 1-9 (top to bottom). Each cell is labeled with yellow text like A1, B2, etc.

Find: {description}

Reply with ONLY the grid cell that contains this element (e.g. "B3"). \
Nothing else — just the cell reference."""

# Periodic screen analysis — vision model reads the screen for the audio model
SCREEN_CHECK_INTERVAL = 5  # seconds between vision checks

SCREEN_CHECK_PROMPT = """\
Describe what you see on this screen. Be concise and factual. Focus on:
- Any terminal/console output, especially ERROR MESSAGES or warnings
- Code visible in any editor (note any syntax errors or issues you spot)
- Any dialog boxes, popups, or notifications
- What application(s) are open and their current state

If there is an error message, quote it exactly. Keep your response under 150 words."""


class TutorSession:
    def __init__(self, topic, overlay_signals: OverlaySignals, audio: AudioManager,
                 logical_w: int = 1920, logical_h: int = 1080):
        self.topic = topic  # None = greeting mode, set later via set_topic()
        self.overlay = overlay_signals
        self.audio = audio
        self._running = False
        # mss screen capture — created lazily in run() so it lives in the async thread
        # (mss uses thread-local handles that fail if created in a different thread)
        self._screen = None
        self._monitor = None
        # Qt logical screen dimensions — the overlay draws in this coordinate space
        self._logical_w = logical_w
        self._logical_h = logical_h
        self._scale_ready = False
        # Gemini client — set during connect, reused for vision lookups
        self._client = None
        # Track whether the model is mid-turn (speaking/generating)
        # Vision checks must NOT send_client_content during an active model turn
        self._model_turn_active = False
        # Cached plan — generated once, reused across reconnects
        self._plan_steps = None
        # Thread-safe queue for receiving topic from UI thread
        self._topic_queue = thread_queue.Queue()
        # Only emit connection_ready once (not on reconnects)
        self._first_connection = True

    async def run(self):
        """Connect to Gemini and run the session. Auto-reconnects on errors."""
        api_key = os.environ.get(
            "GOOGLE_API_KEY",
            os.environ.get("GEMINI_API_KEY", ""),
        )
        if not api_key:
            print("ERROR: No API key found. Set GOOGLE_API_KEY env var.")
            return

        # Create mss in the async thread — mss uses thread-local handles
        self._screen = mss.mss()
        self._monitor = self._screen.monitors[1]

        self.audio.start()
        reconnect_count = 0

        while reconnect_count < MAX_RECONNECTS:
            try:
                await self._connect_and_stream(api_key)
                # Clean exit (e.g. user quit)
                break
            except Exception as e:
                reconnect_count += 1
                print(f"\nSession error (attempt {reconnect_count}/{MAX_RECONNECTS}): {e}")
                if reconnect_count < MAX_RECONNECTS:
                    self.overlay.set_status.emit(f"Reconnecting ({reconnect_count})...")
                    self.audio.clear_playback()
                    await asyncio.sleep(2)
                else:
                    self.overlay.set_status.emit("Error: max reconnects reached")

        self._running = False
        self.audio.stop()
        self.overlay.set_status.emit("Session ended")
        print("Session ended.")

    async def _generate_plan(self, topic: str) -> list:
        """Use Cloud Run vision service to pre-generate a tutorial plan."""
        print(f"[plan] Generating tutorial plan for: '{topic}'")
        self.overlay.set_status.emit("Planning tutorial...")
        try:
            if CLOUD_RUN_URL:
                async with aiohttp.ClientSession() as http:
                    async with http.post(
                        f"{CLOUD_RUN_URL}/generate-plan",
                        json={"topic": topic},
                    ) as resp:
                        data = await resp.json()
                        clean = data.get("steps", ["Follow the tutorial instructions"])
            else:
                # Fallback: direct API call if no Cloud Run URL configured
                response = await self._client.aio.models.generate_content(
                    model=VISION_MODEL,
                    contents=[{"role": "user", "parts": [{"text": PLAN_PROMPT.format(topic=topic)}]}],
                )
                lines = [line.strip() for line in response.text.strip().split("\n") if line.strip()]
                clean = []
                for line in lines:
                    cleaned = re.sub(r"^[\d]+[.)]\s*", "", line)
                    cleaned = re.sub(r"^[-*]\s*", "", cleaned)
                    if cleaned:
                        clean.append(cleaned)
            print(f"[plan] Generated {len(clean)} steps:")
            for i, s in enumerate(clean):
                print(f"       {i+1}. {s}")
            return clean
        except Exception as e:
            print(f"[plan] ERROR generating plan: {e}")
            return ["Follow the tutorial instructions"]

    async def _connect_and_stream(self, api_key: str):
        """Single connection attempt to Gemini Live API."""
        client = genai.Client(api_key=api_key)
        self._client = client  # store for vision lookups

        mss_w = self._monitor["width"]
        mss_h = self._monitor["height"]
        print(f"[scale] Qt logical: {self._logical_w}x{self._logical_h}, mss monitor: {mss_w}x{mss_h}")
        print(f"[scale] Sending images at: {SEND_IMAGE_W}x{SEND_IMAGE_H} (with grid overlay)")

        # Determine system prompt based on current state
        if self.topic == "CALIBRATION_MODE":
            system_instruction = CALIBRATION_PROMPT
        elif self.topic:
            # Have a topic — generate plan and use tutorial prompt
            if self._plan_steps is None:
                self._plan_steps = await self._generate_plan(self.topic)
                self.overlay.set_tutorial.emit(
                    self.topic.split(":")[0] if ":" in self.topic else "Tutorial",
                    self._plan_steps,
                )
            plan_steps = self._plan_steps or []
            steps_text = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(plan_steps))
            system_instruction = SYSTEM_PROMPT.format(topic=self.topic, steps_text=steps_text)
        else:
            # No topic yet — greeting mode
            system_instruction = GREETING_PROMPT

        config = {
            "response_modalities": ["AUDIO"],
            "system_instruction": system_instruction,
            "tools": ALL_TOOLS,
        }

        print(f"Connecting to Gemini Live API ({MODEL})...")
        self.overlay.set_status.emit("Connecting...")

        async with client.aio.live.connect(model=MODEL, config=config) as session:
            print("Connected! Session is live.")
            self.overlay.set_status.emit("Connected — starting...")
            self._running = True

            # Send an initial screen frame so Gemini can see what's on screen
            try:
                sct_img = self._screen.grab(self._monitor)
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                img.thumbnail((SEND_IMAGE_W, SEND_IMAGE_H))
                grid_img = draw_grid_on_image(img)
                buffer = io.BytesIO()
                grid_img.save(buffer, format="JPEG", quality=80)
                await session.send_realtime_input(
                    media={"data": buffer.getvalue(), "mime_type": "image/jpeg"}
                )
                print("[init] Sent initial screen frame (with grid)")
            except Exception as e:
                print(f"[init] Failed to send initial frame: {e}")

            # In calibration mode, place a magenta target on screen
            if self.topic == "CALIBRATION_MODE":
                margin = 150
                tx = random.randint(margin, self._logical_w - margin)
                ty = random.randint(margin, self._logical_h - margin)
                self.overlay.set_target.emit(tx, ty)
                # Figure out which grid cell the target is in
                target_col = min(tx * GRID_COLS // self._logical_w, GRID_COLS - 1)
                target_row = min(ty * GRID_ROWS // self._logical_h, GRID_ROWS - 1)
                target_cell = f"{chr(65 + target_col)}{target_row + 1}"
                print(f"[calibration] Target at logical ({tx}, {ty}), should be grid cell {target_cell}")

            # Send a kick message to get Gemini to speak first
            if self.topic == "CALIBRATION_MODE":
                kick = "Session started. There is a magenta calibration target on screen. Introduce yourself and tell the user you can see the target. Wait for them to ask you to point at it."
            elif self.topic:
                kick = f"Session started. The user wants to learn: {self.topic}. The tutorial plan is already visible on screen. Introduce yourself briefly, then use draw_text_box to show 'Step 1: ...' and begin guiding."
            else:
                kick = "Session started. The user just opened the app. Greet them warmly and let them know they can pick a tutorial from the menu or tell you what they'd like to learn."
            await session.send_client_content(
                turns=[{"role": "user", "parts": [{"text": kick}]}],
                turn_complete=True,
            )
            print(f"[init] Sent kick message")
            self.overlay.set_status.emit("Ready")
            if self._first_connection:
                self._first_connection = False
                self.overlay.connection_ready.emit()

            tasks = []
            try:
                async with asyncio.TaskGroup() as tg:
                    tasks.append(tg.create_task(self._send_mic(session)))
                    tasks.append(tg.create_task(self._send_screen(session)))
                    tasks.append(tg.create_task(self._receive(session)))
                    tasks.append(tg.create_task(self.audio.capture_mic()))
                    tasks.append(tg.create_task(self.audio.play_speaker()))
                    if not self.topic:
                        # Greeting mode — wait for topic selection
                        tasks.append(tg.create_task(self._wait_for_topic(session)))
                    elif self.topic != "CALIBRATION_MODE":
                        tasks.append(tg.create_task(self._periodic_vision_check(session)))
            except* Exception as eg:
                # Re-raise the first real error for the reconnect logic
                for e in eg.exceptions:
                    if not isinstance(e, asyncio.CancelledError):
                        raise e
            finally:
                self._running = False

    async def _send_mic(self, session):
        """Forward mic audio to Gemini."""
        sent = 0
        mic_was_active = False
        while self._running:
            data = await self.audio.mic_queue.get()
            await session.send_realtime_input(
                audio={"data": data, "mime_type": "audio/pcm"}
            )
            sent += 1

            # Detect mic activity from audio level (every 10 chunks ~100ms)
            if sent % 10 == 0:
                samples = struct.unpack(f"<{len(data)//2}h", data)
                rms = (sum(s * s for s in samples) / len(samples)) ** 0.5
                is_active = rms > 500
                if is_active != mic_was_active:
                    mic_was_active = is_active
                    self.overlay.mic_active.emit(is_active)
                    if is_active:
                        self.overlay.set_status.emit("Listening...")
                    else:
                        self.overlay.set_status.emit("Processing...")

            if sent % 100 == 1:
                print(f"[mic] Sent {sent} audio chunks")

    async def _send_screen(self, session):
        """Capture screen and send frames to Gemini at ~1 FPS."""
        while self._running:
            try:
                sct_img = self._screen.grab(self._monitor)
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                img.thumbnail((SEND_IMAGE_W, SEND_IMAGE_H))

                if not self._scale_ready:
                    actual_w, actual_h = img.size
                    print(f"[screen] Sending {actual_w}x{actual_h} images with grid to Gemini")
                    self._scale_ready = True

                # Draw grid overlay on a copy (user never sees it)
                grid_img = draw_grid_on_image(img)

                buffer = io.BytesIO()
                grid_img.save(buffer, format="JPEG", quality=80)
                jpeg_bytes = buffer.getvalue()

                await session.send_realtime_input(
                    media={"data": jpeg_bytes, "mime_type": "image/jpeg"}
                )
            except Exception as e:
                if self._running:
                    print(f"[screen] ERROR: {e}")

            await asyncio.sleep(1.0)

    async def _receive(self, session):
        """Receive audio and tool calls from Gemini."""
        print("[receive] Starting receive loop...")
        while self._running:
            turn = session.receive()
            async for response in turn:
                has_content = bool(response.server_content)
                has_tool = bool(response.tool_call)

                if has_content and response.server_content.model_turn:
                    self._model_turn_active = True
                    parts = response.server_content.model_turn.parts
                    for part in parts:
                        if part.inline_data and isinstance(part.inline_data.data, bytes):
                            self.audio.queue_audio(part.inline_data.data)
                            self.overlay.speaker_active.emit(True)
                            self.overlay.set_status.emit("Speaking...")
                        elif part.text:
                            print(f"[receive] Text: {part.text[:80]}")
                            self.overlay.set_subtitle.emit(part.text)

                if has_content and response.server_content.turn_complete:
                    self._model_turn_active = False
                    print("[receive] Turn complete")
                    self.overlay.speaker_active.emit(False)
                    self.overlay.set_status.emit("Listening...")

                if has_content and response.server_content.interrupted:
                    self._model_turn_active = False
                    print("[receive] Interrupted")
                    self.audio.clear_playback()
                    self.overlay.speaker_active.emit(False)

                if has_tool:
                    print(f"[receive] Tool call")
                    await self._handle_tool_calls(session, response.tool_call)

    async def _vision_find(self, description: str) -> str:
        """Use Cloud Run vision service to find an element on screen.

        Takes a fresh screenshot, adds the grid overlay, sends it to the
        Cloud Run service, and returns the grid cell reference (e.g. 'B3').
        """
        # Grab fresh screenshot with grid
        sct_img = self._screen.grab(self._monitor)
        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
        img.thumbnail((SEND_IMAGE_W, SEND_IMAGE_H))
        grid_img = draw_grid_on_image(img)

        buffer = io.BytesIO()
        grid_img.save(buffer, format="JPEG", quality=85)
        jpeg_bytes = buffer.getvalue()

        print(f"[vision] Finding: '{description}'")
        try:
            if CLOUD_RUN_URL:
                img_b64 = base64.b64encode(jpeg_bytes).decode("utf-8")
                async with aiohttp.ClientSession() as http:
                    async with http.post(
                        f"{CLOUD_RUN_URL}/find-element",
                        json={"description": description, "image": img_b64},
                    ) as resp:
                        data = await resp.json()
                        cell = data.get("cell", "D3").strip().upper()
            else:
                # Fallback: direct API call
                prompt = VISION_PROMPT.format(description=description)
                response = await self._client.aio.models.generate_content(
                    model=VISION_MODEL,
                    contents=[{
                        "role": "user",
                        "parts": [
                            {"inline_data": {"mime_type": "image/jpeg", "data": jpeg_bytes}},
                            {"text": prompt},
                        ],
                    }],
                )
                cell = response.text.strip().upper()

            if len(cell) >= 2 and cell[0].isalpha() and cell[1:].isdigit():
                print(f"[vision] Found: cell {cell}")
                return cell
            else:
                print(f"[vision] Unexpected response: '{cell}', defaulting to D3")
                return "D3"
        except Exception as e:
            print(f"[vision] ERROR: {e}")
            return "D3"

    async def _periodic_vision_check(self, session):
        """Periodically send screenshots to Cloud Run for screen reading.

        The audio model can't reliably read text on screen (errors, code, terminal output).
        This sends clean screenshots (no grid) to the Cloud Run vision service, which
        describes what it sees. That description is injected into the Live session so the
        audio model has accurate context.
        """
        while self._running:
            await asyncio.sleep(SCREEN_CHECK_INTERVAL)
            if not self._running:
                break
            # Skip if model is mid-turn — sending client content during an active
            # model turn causes 1008 disconnects
            if self._model_turn_active:
                print("[vision-check] Skipping — model is mid-turn")
                continue
            try:
                # Grab clean screenshot — NO grid overlay (we want to read text, not cells)
                sct_img = self._screen.grab(self._monitor)
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                img.thumbnail((SEND_IMAGE_W, SEND_IMAGE_H))

                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=80)
                jpeg_bytes = buffer.getvalue()

                if CLOUD_RUN_URL:
                    img_b64 = base64.b64encode(jpeg_bytes).decode("utf-8")
                    async with aiohttp.ClientSession() as http:
                        async with http.post(
                            f"{CLOUD_RUN_URL}/analyze-screen",
                            json={"image": img_b64},
                        ) as resp:
                            data = await resp.json()
                            description = data.get("description", "")
                else:
                    # Fallback: direct API call
                    response = await self._client.aio.models.generate_content(
                        model=VISION_MODEL,
                        contents=[{
                            "role": "user",
                            "parts": [
                                {"inline_data": {"mime_type": "image/jpeg", "data": jpeg_bytes}},
                                {"text": SCREEN_CHECK_PROMPT},
                            ],
                        }],
                    )
                    description = response.text.strip()

                print(f"[vision-check] {description[:120]}")

                # Inject into the Live session as context for the audio model
                await session.send_client_content(
                    turns=[{"role": "user", "parts": [{"text": f"[SCREEN UPDATE] {description}"}]}],
                    turn_complete=True,
                )
            except Exception as e:
                if self._running:
                    print(f"[vision-check] ERROR: {e}")

    def _parse_step_from_text(self, text: str) -> int:
        """Extract step number from text like 'Step 3: Do something'. Returns 0 if not found.

        Searches anywhere in the text (not just the start) and handles various formats:
        'Step 3: ...', 'Step 3 -', 'step 3.', etc.
        """
        m = re.search(r"Step\s+(\d+)", text, re.IGNORECASE)
        return int(m.group(1)) if m else 0

    async def _handle_tool_calls(self, session, tool_call):
        """Process tool calls from Gemini and send responses."""
        function_responses = []

        for fc in tool_call.function_calls:
            name = fc.name
            args = fc.args or {}
            print(f"  Tool: {name}({args})")

            if name == "find_and_highlight":
                description = str(args.get("description", ""))
                label = str(args.get("label", ""))
                # Use vision model to find the element precisely
                cell = await self._vision_find(description)
                x, y, w, h = grid_cell_to_rect(
                    cell, self._logical_w, self._logical_h
                )
                print(f"    → vision found cell {cell} → screen ({x}, {y}, {w}x{h}) label='{label}'")
                self.overlay.clear_all.emit()
                self.overlay.add_highlight_labeled.emit(x, y, w, h, label)
                result = {"status": "highlighted", "area": cell}

            elif name == "draw_pointer":
                x = int(args.get("x", 0))
                y = int(args.get("y", 0))
                label = str(args.get("label", ""))
                print(f"    → screen ({x}, {y})")
                self.overlay.add_pointer.emit(x, y, label)
                result = {"status": "drawn"}

            elif name == "draw_text_box":
                x = int(args.get("x", 0))
                y = int(args.get("y", 0))
                text = str(args.get("text", ""))
                print(f"    → task: {text[:80]}")
                # Show in the tutorial panel's task section (no floating overlay box)
                self.overlay.set_current_task.emit(text)
                step = self._parse_step_from_text(text)
                if step > 0:
                    # Complete previous step and advance
                    if step > 1:
                        self.overlay.complete_step.emit(step - 1)
                    self.overlay.set_current_step.emit(step)
                    print(f"    → step tracking: now on step {step}")
                    result = {"status": "drawn", "step_tracked": step}
                else:
                    print(f"    → step tracking: NO step number found in text")
                    result = {
                        "status": "drawn",
                        "warning": "No 'Step N:' found in text — step progress was NOT updated. "
                                   "Always include 'Step N: ' in draw_text_box text.",
                    }

            elif name == "highlight_region":
                x = int(args.get("x", 0))
                y = int(args.get("y", 0))
                w = int(args.get("width", 100))
                h = int(args.get("height", 100))
                print(f"    → screen ({x}, {y}, {w}x{h})")
                self.overlay.add_highlight.emit(x, y, w, h)
                result = {"status": "highlighted"}

            elif name == "clear_overlays":
                self.overlay.clear_all.emit()
                result = {"status": "cleared"}

            else:
                result = {"error": f"Unknown function: {name}"}

            function_responses.append(
                types.FunctionResponse(
                    id=fc.id,
                    name=fc.name,
                    response=result,
                )
            )

        await session.send_tool_response(function_responses=function_responses)

    def set_topic(self, topic: str):
        """Called from the UI thread when user selects a tutorial topic."""
        self._topic_queue.put(topic)

    async def _wait_for_topic(self, session):
        """Poll for topic selection from the UI thread."""
        while self._running:
            try:
                topic = self._topic_queue.get_nowait()
                self.topic = topic
                if topic == "CALIBRATION_MODE":
                    await self._start_calibration(session)
                else:
                    await self._start_tutorial(session, topic)
                return
            except thread_queue.Empty:
                await asyncio.sleep(0.1)

    async def _start_tutorial(self, session, topic):
        """Generate plan and inject tutorial context into the live session."""
        self._plan_steps = await self._generate_plan(topic)
        self.overlay.set_tutorial.emit(
            topic.split(":")[0] if ":" in topic else "Tutorial",
            self._plan_steps,
        )
        steps_text = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(self._plan_steps))
        inject = (
            f"[TUTORIAL STARTED] Topic: {topic}\n"
            f"Steps:\n{steps_text}\n\n"
            f"The tutorial plan is now visible on screen. "
            f"Begin guiding the user with Step 1. Use draw_text_box with 'Step 1: ...' to track progress."
        )
        if not self._model_turn_active:
            await session.send_client_content(
                turns=[{"role": "user", "parts": [{"text": inject}]}],
                turn_complete=True,
            )
        print(f"[topic] Tutorial started: {topic}")
        # Start periodic vision checks now that we have a topic
        asyncio.create_task(self._periodic_vision_check(session))

    async def _start_calibration(self, session):
        """Set up calibration mode after greeting."""
        margin = 150
        tx = random.randint(margin, self._logical_w - margin)
        ty = random.randint(margin, self._logical_h - margin)
        self.overlay.set_target.emit(tx, ty)
        target_col = min(tx * GRID_COLS // self._logical_w, GRID_COLS - 1)
        target_row = min(ty * GRID_ROWS // self._logical_h, GRID_ROWS - 1)
        target_cell = f"{chr(65 + target_col)}{target_row + 1}"
        print(f"[calibration] Target at logical ({tx}, {ty}), grid cell {target_cell}")

        inject = (
            "[CALIBRATION MODE] A magenta circle with crosshairs has been placed on screen. "
            "Tell the user you can see the calibration target and wait for them to ask you to "
            "point at it. Use find_and_highlight with 'the magenta circle with crosshairs' when asked."
        )
        if not self._model_turn_active:
            await session.send_client_content(
                turns=[{"role": "user", "parts": [{"text": inject}]}],
                turn_complete=True,
            )
