"""
Learn With Gemini — Cloud Run Vision Service
Handles vision model calls (plan generation, element finding, screen analysis)
so the desktop client doesn't need direct Gemini API access for these.
"""

import base64
import os
import re

from fastapi import FastAPI, HTTPException
from google import genai
from pydantic import BaseModel

app = FastAPI(title="Learn With Gemini Vision Service")

VISION_MODEL = "gemini-2.5-flash"

# --- Prompts (same as desktop client) ---

PLAN_PROMPT = """\
Create a step-by-step tutorial plan for: {topic}

Return ONLY 5-6 short step descriptions, one per line. No numbers, no bullets, \
no extra text. Keep it concise — max 6 steps. Example:

Open Visual Studio Code
Create a new Python file
Write the Hello World code
Save the file
Run the program in terminal
Verify the output
"""

VISION_PROMPT = """\
Look at this screenshot. It has a grid overlay with columns A-P (left to right) \
and rows 1-9 (top to bottom). Each cell is labeled with yellow text like A1, B2, etc.

Find: {description}

Reply with ONLY the grid cell that contains this element (e.g. "B3"). \
Nothing else — just the cell reference."""

SCREEN_CHECK_PROMPT = """\
Describe what you see on this screen. Be concise and factual. Focus on:
- Any terminal/console output, especially ERROR MESSAGES or warnings
- Code visible in any editor (note any syntax errors or issues you spot)
- Any dialog boxes, popups, or notifications
- What application(s) are open and their current state

If there is an error message, quote it exactly. Keep your response under 150 words."""


# --- Request/Response models ---

class PlanRequest(BaseModel):
    topic: str

class PlanResponse(BaseModel):
    steps: list[str]

class FindElementRequest(BaseModel):
    description: str
    image: str  # base64-encoded JPEG

class FindElementResponse(BaseModel):
    cell: str

class AnalyzeScreenRequest(BaseModel):
    image: str  # base64-encoded JPEG

class AnalyzeScreenResponse(BaseModel):
    description: str


# --- Gemini client (lazy init) ---

_client = None

def get_client():
    global _client
    if _client is None:
        api_key = os.environ.get("GOOGLE_API_KEY", "")
        if not api_key:
            raise HTTPException(status_code=500, detail="GOOGLE_API_KEY not set")
        _client = genai.Client(api_key=api_key)
    return _client


# --- Endpoints ---

@app.get("/")
async def health():
    return {
        "status": "ok",
        "service": "Learn With Gemini Vision Service",
        "model": VISION_MODEL,
    }


@app.post("/generate-plan", response_model=PlanResponse)
async def generate_plan(req: PlanRequest):
    client = get_client()
    prompt = PLAN_PROMPT.format(topic=req.topic)

    response = await client.aio.models.generate_content(
        model=VISION_MODEL,
        contents=[{"role": "user", "parts": [{"text": prompt}]}],
    )

    lines = [line.strip() for line in response.text.strip().split("\n") if line.strip()]
    clean = []
    for line in lines:
        cleaned = re.sub(r"^[\d]+[.)]\s*", "", line)
        cleaned = re.sub(r"^[-*]\s*", "", cleaned)
        if cleaned:
            clean.append(cleaned)

    return PlanResponse(steps=clean)


@app.post("/find-element", response_model=FindElementResponse)
async def find_element(req: FindElementRequest):
    client = get_client()
    jpeg_bytes = base64.b64decode(req.image)
    prompt = VISION_PROMPT.format(description=req.description)

    response = await client.aio.models.generate_content(
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
        return FindElementResponse(cell=cell)
    return FindElementResponse(cell="D3")


@app.post("/analyze-screen", response_model=AnalyzeScreenResponse)
async def analyze_screen(req: AnalyzeScreenRequest):
    client = get_client()
    jpeg_bytes = base64.b64decode(req.image)

    response = await client.aio.models.generate_content(
        model=VISION_MODEL,
        contents=[{
            "role": "user",
            "parts": [
                {"inline_data": {"mime_type": "image/jpeg", "data": jpeg_bytes}},
                {"text": SCREEN_CHECK_PROMPT},
            ],
        }],
    )

    return AnalyzeScreenResponse(description=response.text.strip())


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
