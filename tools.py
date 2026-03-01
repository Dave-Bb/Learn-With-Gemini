"""
Tool/function definitions for Gemini Live API.
These define the overlay actions Gemini can call to guide the user visually.
"""

DRAW_POINTER = {
    "name": "draw_pointer",
    "description": (
        "Draw an arrow/pointer on the user's screen pointing at a specific location "
        "with a label. Use this to show the user where to click, look, or interact. "
        "Coordinates are pixel positions matching what you see in the screen capture."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "x": {"type": "INTEGER", "description": "X pixel coordinate on screen"},
            "y": {"type": "INTEGER", "description": "Y pixel coordinate on screen"},
            "label": {
                "type": "STRING",
                "description": "Short text label, e.g. 'Click here', 'Type here', 'This button'",
            },
        },
        "required": ["x", "y", "label"],
    },
}

DRAW_TEXT_BOX = {
    "name": "draw_text_box",
    "description": (
        "Show an instruction text box on the user's screen. Use for longer instructions "
        "the user should read, like what to type or important notes."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "x": {"type": "INTEGER", "description": "X coordinate for the text box"},
            "y": {"type": "INTEGER", "description": "Y coordinate for the text box"},
            "text": {
                "type": "STRING",
                "description": "The instruction text to display",
            },
        },
        "required": ["x", "y", "text"],
    },
}

HIGHLIGHT_REGION = {
    "name": "highlight_region",
    "description": (
        "Highlight a rectangular region on the user's screen with a colored border. "
        "Use to draw attention to a UI area, menu, panel, or section."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "x": {"type": "INTEGER", "description": "Left X coordinate of the region"},
            "y": {"type": "INTEGER", "description": "Top Y coordinate of the region"},
            "width": {"type": "INTEGER", "description": "Width in pixels"},
            "height": {"type": "INTEGER", "description": "Height in pixels"},
        },
        "required": ["x", "y", "width", "height"],
    },
}

CLEAR_OVERLAYS = {
    "name": "clear_overlays",
    "description": (
        "Clear all current overlay hints from the user's screen. "
        "Use when the user has completed a step and the hints are no longer needed."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {},
    },
}

FIND_AND_HIGHLIGHT = {
    "name": "find_and_highlight",
    "description": (
        "Find something on the user's screen and highlight the area around it. "
        "Describe what you want to find — a button, menu, icon, text field, etc. "
        "The system will locate it precisely and highlight the correct area. "
        "This is the PREFERRED way to point at things on screen. "
        "Just describe what to find, and the system handles the rest."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "description": {
                "type": "STRING",
                "description": (
                    "Description of what to find on screen, e.g. "
                    "'the File menu button in the top menu bar', "
                    "'the search bar', 'the magenta calibration target', "
                    "'the Save button'"
                ),
            },
            "label": {
                "type": "STRING",
                "description": "Short label to show the user, e.g. 'Click here', 'Type here'",
            },
        },
        "required": ["description", "label"],
    },
}

SET_TUTORIAL_PLAN = {
    "name": "set_tutorial_plan",
    "description": (
        "Set the step-by-step tutorial plan. Call this ONCE at the very start of the "
        "tutorial to define all the steps the user will follow. The steps will be shown "
        "in a persistent panel on screen so the user can always see their progress."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "title": {
                "type": "STRING",
                "description": "Tutorial title, e.g. 'Python: Hello World'",
            },
            "steps": {
                "type": "STRING",
                "description": (
                    "All steps separated by | (pipe character). Example: "
                    "'Open VS Code|Create a new file|Write the code|Run the program'"
                ),
            },
        },
        "required": ["title", "steps"],
    },
}

SET_CURRENT_TASK = {
    "name": "set_current_task",
    "description": (
        "Show the current task instruction prominently on screen. Use this to tell "
        "the user exactly what to do RIGHT NOW. This stays visible until you change "
        "it or clear it. Also highlights which step in the plan this belongs to."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "step_number": {
                "type": "INTEGER",
                "description": "Which step this belongs to (1-based, matches the plan)",
            },
            "instruction": {
                "type": "STRING",
                "description": (
                    "Clear, specific instruction for what the user should do now, e.g. "
                    "'Click the File menu at the top left', "
                    "'Type: print(\"Hello World\")', "
                    "'Press Ctrl+S to save the file'"
                ),
            },
        },
        "required": ["step_number", "instruction"],
    },
}

COMPLETE_STEP = {
    "name": "complete_step",
    "description": (
        "Mark a tutorial step as completed. Call this when you can see on screen "
        "that the user has finished a step. It will show a checkmark on the step."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "step_number": {
                "type": "INTEGER",
                "description": "Which step was completed (1-based, matches the plan)",
            },
        },
        "required": ["step_number"],
    },
}

# Tools for the Live API audio session.
# Only the original 5 tools that are stable with the audio-native model.
# Tutorial state (plan panel, current task bar, step tracking) is managed client-side.
ALL_TOOLS = [
    {
        "function_declarations": [
            FIND_AND_HIGHLIGHT,
            DRAW_TEXT_BOX,
            HIGHLIGHT_REGION,
            DRAW_POINTER,
            CLEAR_OVERLAYS,
        ]
    }
]
