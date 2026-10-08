import edge_tts
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/voice", tags=["Voice"])

class VoiceRequest(BaseModel):
    text: str
    voice: str = "ru-RU-SvetlanaNeural"

@router.post("/tts")
async def text_to_speech(req: VoiceRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    
    try:
        communicate = edge_tts.Communicate(req.text, req.voice)
        
        async def generate():
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    yield chunk["data"]

        return StreamingResponse(generate(), media_type="audio/mpeg")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
