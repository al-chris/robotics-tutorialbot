import os
import uvicorn
import base64
from google import genai
from google.genai import types
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Optional

# Import local modules
import parser
import nav_loader

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Gemini
# Uses GEIMINI_API_KEY environment variable
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

# State
SESSIONS = {} 
NAV_MAP = {}

@app.on_event("startup")
async def startup_event():
    # Load navigation map (assuming backend is inside root)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    root_path = os.path.abspath(os.path.join(current_dir, ".."))
    
    global NAV_MAP
    NAV_MAP = nav_loader.load_navigation_map(root_path)
    print(f"Loading navigation map... Found {len(NAV_MAP)} sections.")

class ChatRequest(BaseModel):
    session_id: str
    section_id: str
    message: str
    images: List[Dict[str, str]] = [] # list of {name: str, data: base64_str}

@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    # 1. Get filepath for section
    # Try exact match first
    file_path = NAV_MAP.get(request.section_id)
    
    if not file_path:
        # Try simplified matching (e.g. if request is 2.12.1 but map has 2.12.1a)
        # or partial match
        print(f"Direct match failed for section '{request.section_id}'. Available keys sample: {list(NAV_MAP.keys())[:5]}")
        # Very simple heuristic fallback
        for k, v in NAV_MAP.items():
            if k == request.section_id or k.startswith(request.section_id):
                file_path = v
                break

    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"Section {request.section_id} content not found.")

    # 2. Parse Text Context
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        parsed_text = parser.parse_textbook_content(html_content)
    except Exception as e:
        print(f"Error parsing file {file_path}: {e}")
        # Continue with empty context rather than crashing? No, fail early for debugging.
        raise HTTPException(status_code=500, detail="Failed to parse section content.")

    # 3. Setup Gemini Content
    system_prompt = (
        "You are an AI tutor for a robotics textbook. Answer strictly based on the provided context. "
        "Use the provided figures to explain concepts. Do not hallucinate. "
        "If the answer is not in the context or figures, explicitly say 'I cannot find that information in this section.'."
    )
    
    # Prepare history
    history_list = SESSIONS.get(request.session_id, [])
    history_text = "___CONVERSATION HISTORY___\n"
    for role, msg in history_list:
        history_text += f"{role}: {msg}\n"
    
    full_prompt_text = (
        f"{system_prompt}\n\n"
        f"___SECTION CONTEXT___\n{parsed_text}\n\n"
        f"{history_text}\n"
        f"Student Question: {request.message}"
    )
    
    # Prepare contents list (Text + Images)
    parts = [types.Part(text=full_prompt_text)]
    
    # Add Binary Images
    for img in request.images:
        # Determine mime type
        mime = "image/png"
        name_lower = img.get("name", "").lower()
        if "jpg" in name_lower or "jpeg" in name_lower:
            mime = "image/jpeg"
            
        try:
            image_bytes = base64.b64decode(img["data"])
            parts.append(types.Part(
                inline_data=types.Blob(
                    mime_type=mime,
                    data=image_bytes
                )
            ))
        except Exception as e:
            print(f"Skipping invalid image {name_lower}: {e}")

    # 4. Generate
    try:
        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=[types.Content(parts=parts)]
        )
        reply_text = response.text
    except Exception as e:
        print(f"Gemini Error: {e}")
        reply_text = "I'm having trouble connecting to the AI model right now. Please check the server logs."

    # 5. Save History
    if request.session_id not in SESSIONS: 
        SESSIONS[request.session_id] = []
    
    # Append
    SESSIONS[request.session_id].append(("Student", request.message))
    SESSIONS[request.session_id].append(("Tutor", reply_text))
    
    # Limit History (Optional, keep last 10 turns)
    if len(SESSIONS[request.session_id]) > 20: 
        SESSIONS[request.session_id] = SESSIONS[request.session_id][-20:]
    
    return {"reply": reply_text}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
