"""HTTP routes for the robotics AI tutor backend."""

import os
import uuid
import uvicorn
import base64
from contextlib import asynccontextmanager
from google import genai
from google.genai import types
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Tuple, Any
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Import local modules
import parser

# Initialize Gemini
# Uses GEIMINI_API_KEY environment variable
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

# Initialize Limiter
limiter = Limiter(key_func=get_remote_address)

# State
SESSIONS: Dict[str, List[Tuple[str, str]]] = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup."""
    yield

app = FastAPI(lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    """Chat request model for AI tutor interactions."""
    session_id: uuid.UUID
    context: str
    message: str
    images: List[Dict[str, str]] = [] # list of {name: str, data: base64_str}

@app.post("/chat", description="""
Process a chat message and return an AI-generated response.

This endpoint handles student questions about robotics textbook content,
providing context-aware answers based on the current section and conversation history.

Example request:
```
{\n
"session_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",\n
"context": "<body><h1>Introduction to Robotics</h1><p>Robotics is...</p></body",\n
"message": "What is the definition of robotics?",\n
"images": []\n
}
```
""")
@limiter.limit("5/minute") # type: ignore
async def chat_endpoint(request: Request, chat_req: ChatRequest):
    """Process chat messages and return AI responses."""
    # 1. Parse HTML Context directly from request
    try:
        parsed_text = parser.parse_textbook_content(chat_req.context)
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
        "Use simple grammar."
        "Use figures when they help explain the concept. Do not introduce facts, definitions, or terminology "
        "that are not supported by the context or figures.\n\n"
        "If a question is not explicitly answered in the context or figures, respond by giving the most relevant "
        "explanation or insight that can be reasonably inferred from the given material, clearly grounding your "
        "answer in what *is* present. Do not speculate beyond the scope of this section."
    )
    
    # Prepare history
    history_list = SESSIONS.get(str(chat_req.session_id), [])
    history_text = "___CONVERSATION HISTORY___\n"
    for role, msg in history_list:
        history_text += f"{role}: {msg}\n"
    
    full_prompt_text = (
        f"{system_prompt}\n\n"
        f"___SECTION CONTEXT___\n{parsed_text}\n\n"
        f"{history_text}\n"
        f"Student Question: {chat_req.message}"
    )
    
    # Prepare contents list (Text + Images)
    parts = [types.Part(text=full_prompt_text)]
    
    # Add Binary Images
    for img in chat_req.images:
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
    if str(chat_req.session_id) not in SESSIONS: 
        SESSIONS[str(chat_req.session_id)] = []
    
    # Append
    SESSIONS[str(chat_req.session_id)].append(("Student", chat_req.message))
    SESSIONS[str(chat_req.session_id)].append(("Tutor", reply_text))
    
    # Limit History (Optional, keep last 10 turns)
    if len(SESSIONS[str(chat_req.session_id)]) > 20: 
        SESSIONS[str(chat_req.session_id)] = SESSIONS[str(chat_req.session_id)][-20:]
    
    return {"reply": reply_text}

@app.get("/session/{session_id}")
async def get_session(session_id: str) -> Dict[str, Any]:
    if session_id not in SESSIONS:
        raise HTTPException(status_code=404, detail="Session not found")
    history = SESSIONS[session_id]
    history_dicts = [{"role": role, "message": msg} for role, msg in history]
    return {"session_id": session_id, "history": history_dicts}

@app.get("/sessions")
async def list_sessions(offset: int = Query(0, ge=0), limit: int = Query(10, ge=1, le=100)) -> Dict[str, Any]:
    session_ids = list(SESSIONS.keys())
    total = len(session_ids)
    paginated = session_ids[offset:offset + limit]
    return {
        "total": total,
        "sessions": paginated,
        "offset": offset,
        "limit": limit
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8152)
