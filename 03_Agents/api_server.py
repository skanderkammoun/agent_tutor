import asyncio
import json
import re
import os
import sys 
import requests
from fastapi import FastAPI, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from contextlib import asynccontextmanager

from langdetect import detect 

from agent_rag import BrainAgent

brain = BrainAgent()

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Démarrage du Serveur FastAPI (Subul Tuteur)...")
    await brain.setup()

    print("🔥 Lancement du Warm-up réseau (pour éviter les 13s de latence au premier client)...")
    try:
        await brain.search_index_manager.search("warmup test réseau")
        print("✅ Réseau débouché et prêt (IPv4) !")
    except Exception as e:
        print(f"⚠️ Warm-up a échoué, mais l'API continue : {e}")

    print("✅ Index RAG vérifié. API prête à recevoir des requêtes !")
    yield 
    print("🛑 Extinction du serveur...")

app = FastAPI(title="Subul API Web", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str
    user_id: str = "etudiant_anonyme"
    session_id: str = "session_defaut"
    lang: str = "fr"
    is_audio: bool = False

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    try:
        lang_code = detect(request.message)
        final_lang = "fr" if "fr" in lang_code else "en"
    except:
        final_lang = "fr"

    print(f"📨 Requête de [{request.user_id} - {request.session_id}] : '{request.message}' | Langue : {final_lang} | Audio : {request.is_audio}")

    agent = brain.get_agent(lang=final_lang, is_audio=request.is_audio)
    
    async def generate_response():
        try:
            consigne_langue = "\n\n(Règle stricte: Formule ta réponse IMPÉRATIVEMENT en Français.)" if final_lang == "fr" else "\n\n(Strict rule: Answer entirely in English.)"
            
            # Message sécurisé sans le système de quota
            message_securise = request.message + consigne_langue

            if not request.is_audio:
                # Mode Texte
                async for chunk in agent.run_stream(message=message_securise, user_id=request.user_id, session_id=request.session_id):
                    payload = {"chunk": chunk, "status": "streaming", "lang": final_lang}
                    yield json.dumps(payload) + "\n"
                
                yield json.dumps({"chunk": "", "status": "completed", "lang": final_lang}) + "\n"

            else:
                # Mode Audio : Streaming temps réel optimisé (Latence zéro)
                buffer = ""
                async for chunk in agent.run_stream(message=message_securise, user_id=request.user_id, session_id=request.session_id):
                    buffer += chunk
                    
                    if any(punct in buffer for punct in ['. ', '! ', '? ', '\n']):
                        clean_sentence = buffer.strip()
                        if clean_sentence:
                            payload = {"chunk": clean_sentence, "status": "streaming", "lang": final_lang}
                            yield json.dumps(payload) + "\n"
                            await asyncio.sleep(0.01) 
                        buffer = "" 
                
                # Envoi des derniers mots restants
                if buffer.strip():
                    payload = {"chunk": buffer.strip(), "status": "streaming", "lang": final_lang}
                    yield json.dumps(payload) + "\n"
                
                yield json.dumps({"chunk": "", "status": "completed", "lang": final_lang}) + "\n"
                
        except Exception as e:
            print(f"❌ Erreur API : {e}")
            yield json.dumps({"chunk": f"Erreur serveur: {e}", "status": "error"}) + "\n"

    return StreamingResponse(generate_response(), media_type="application/x-ndjson")

@app.get("/api/tts")
def tts_endpoint(text: str, lang: str = "fr"):
    print(f"🔊 Demande Cartesia TTS ({lang}) : {text}")
    
    voice_id = "6ccbfb76-1fc6-48f7-b71d-91ac6298247b" if lang == "en" else "f786b574-daa5-4673-aa0c-cbe3e8534c02"
    
    CARTESIA_API_KEY = os.getenv("CARTESIA_API_KEY")
    CARTESIA_URL = "https://api.cartesia.ai/tts/bytes"
    
    headers = {
        "X-API-Key": CARTESIA_API_KEY,
        "Cartesia-Version": "2025-04-16",
        "Content-Type": "application/json"
    }

    payload = {
        "model_id": "sonic-3",
        "transcript": text,
        "voice": {
            "mode": "id",
            "id": voice_id
        },
        "output_format": {
            "container": "wav",
            "encoding": "pcm_f32le",
            "sample_rate": 44100
        },
        "language": lang,
        "generation_config": {
            "speed": 1,
            "volume": 1
        }
    }
    
    try:
        response = requests.post(CARTESIA_URL, headers=headers, json=payload)
        
        if response.status_code != 200:
            print(f"❌ Erreur Serveur Cartesia: {response.text}")
            raise HTTPException(status_code=500, detail=f"Erreur Cartesia: {response.text}")

        return Response(content=response.content, media_type="audio/wav")
        
    except Exception as e:
        print(f"❌ Erreur locale TTS : {e}")
        try:
            raise HTTPException(status_code=500, detail=str(e))
        except NameError:
            return {"error": str(e)}

class EndSessionRequest(BaseModel):
    user_id: str
    session_id: str

@app.post("/api/session/end")
async def end_session(request: EndSessionRequest):
    print(f" [API] L'étudiant {request.user_id} ferme la session {request.session_id}. Lancement du bilan pédagogique...")
    
    try:
        await brain.memory.trigger_background_summary(request.user_id, request.session_id)
        return {"status": "success", "message": "Bilan de session généré et sauvegardé en mémoire longue avec succès."}
    
    except Exception as e:
        print(f" [API] Erreur lors de la clôture de session: {e}")
        raise HTTPException(status_code=500, detail="Erreur lors de la génération du résumé de session.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)