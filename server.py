"""HTTP routes for the robotics AI tutor backend."""

import os
import uvicorn
import base64
from contextlib import asynccontextmanager
from google import genai
from google.genai import types
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Tuple

# Import local modules
import parser
import nav_loader

# Initialize Gemini
# Uses GEIMINI_API_KEY environment variable
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

# State
SESSIONS: Dict[str, List[Tuple[str, str]]] = {}
nav_map: Dict[str, str] = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load navigation map on startup."""
    # Load navigation map (assuming backend is inside root)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    root_path = os.path.abspath(os.path.join(current_dir, ".."))
    
    global nav_map
    nav_map = nav_loader.load_navigation_map(root_path)
    print(f"Loading navigation map... Found {len(nav_map)} sections.")
    yield

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    """Chat request model for AI tutor interactions."""
    session_id: str
    context: str
    message: str
    images: List[Dict[str, str]] = [] # list of {name: str, data: base64_str}

@app.post("/chat", description="""
Process a chat message and return an AI-generated response.

This endpoint handles student questions about robotics textbook content,
providing context-aware answers based on the current section and conversation history.
""")
async def chat_endpoint(request: ChatRequest):
    """Process chat messages and return AI responses."""
    # 1. Parse HTML Context directly from request
    try:
        parsed_text = parser.parse_textbook_content(request.context)
    except Exception as e:
        print(f"Error parsing HTML context: {e}")
        raise HTTPException(status_code=500, detail="Failed to parse HTML content.")

    # 3. Setup Gemini Content
    # system_prompt = (
    #     "You are an AI tutor for a robotics textbook. Answer strictly based on the provided context. "
    #     "Use the provided figures to explain concepts. Do not hallucinate. "
    #     "If the answer is not in the context or figures, explicitly say 'I cannot find that information in this section.'."
    # )

    system_prompt = (
        "You are an AI tutor for a robotics textbook. Answer using only the provided context and figures. "
        "Use figures when they help explain the concept. Do not introduce facts, definitions, or terminology "
        "that are not supported by the context or figures.\n\n"
        "If a question is not explicitly answered in the context or figures, respond by giving the most relevant "
        "explanation or insight that can be reasonably inferred from the given material, clearly grounding your "
        "answer in what *is* present. Do not speculate beyond the scope of this section."
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
        response = client.models.generate_content(  # type: ignore
            model='gemini-2.5-flash',
            contents=[types.Content(parts=parts)]
        )
        reply_text = response.text if response.text is not None else "No response from AI."
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
    uvicorn.run(app, host="0.0.0.0", port=8152)
