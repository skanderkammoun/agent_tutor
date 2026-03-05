import asyncio
import json
import re
import os
import requests
from fastapi import FastAPI, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel


from langdetect import detect 

from agent_rag import BrainAgent

app = FastAPI(title="Subul API Web")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

brain = BrainAgent()

@app.on_event("startup")
async def startup_event():
    print("🚀 Démarrage du Serveur FastAPI...")
    await brain.setup()
    
    print(" Lancement du Warm-up réseau (pour éviter les 13s de latence au premier client)...")
    try:
        await brain.search_index_manager.search("warmup test réseau")
        print(" Réseau débouché et prêt (IPv4) !")
    except Exception as e:
        print(f" Warm-up a échoué, mais l'API continue : {e}")

    print(" Index RAG vérifié. API prête à recevoir des requêtes !")

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
            message_securise = request.message + consigne_langue

           
            if not request.is_audio:
                async for chunk in agent.run_stream(message=message_securise, user_id=request.user_id, session_id=request.session_id):
                    payload = {"chunk": chunk, "status": "streaming", "lang": final_lang}
                    yield json.dumps(payload) + "\n"
                
                yield json.dumps({"chunk": "", "status": "completed", "lang": final_lang}) + "\n"

          
            else:
                full_text = ""
                async for chunk in agent.run_stream(message=message_securise, user_id=request.user_id, session_id=request.session_id):
                    full_text += chunk
                
               
                sentences = re.split(r'(?<=[.!?]) +', full_text)
                for sentence in sentences:
                    clean_sentence = sentence.strip()
                    if clean_sentence:
                        payload = {"chunk": clean_sentence, "status": "streaming", "lang": final_lang}
                        yield json.dumps(payload) + "\n"
                        await asyncio.sleep(0.05) # Petit délai naturel
                
                yield json.dumps({"chunk": "", "status": "completed", "lang": final_lang}) + "\n"
                
        except Exception as e:
            print(f"❌ Erreur API : {e}")
            yield json.dumps({"chunk": f"Erreur serveur: {e}", "status": "error"}) + "\n"

    return StreamingResponse(generate_response(), media_type="application/x-ndjson")


@app.get("/api/tts")
def tts_endpoint(text: str, lang: str = "fr"):
    print(f"🔊 Demande TTS ({lang}) : {text}")
    
    model_name = "aura-2-agathe-fr" if lang == "fr" else "aura-2-arcas-en"
    
    DG_API_KEY = os.getenv("DEEPGRAM_API_KEY")
    DEEPGRAM_URL = f"https://api.deepgram.com/v1/speak?model={model_name}&encoding=linear16&container=wav"
    
    headers = {
        "Authorization": f"Token {DG_API_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(DEEPGRAM_URL, headers=headers, json={"text": text})
        
        if response.status_code != 200:
            print(f" Erreur Serveur Deepgram: {response.text}")
            raise HTTPException(status_code=500, detail=f"Erreur Deepgram: {response.text}")

        return Response(content=response.content, media_type="audio/wav")
        
    except Exception as e:
        print(f" Erreur locale TTS : {e}")
        try:
            raise HTTPException(status_code=500, detail=str(e))
        except NameError:
            return {"error": str(e)}
# --- NOUVELLE ROUTE FINOPS : CLÔTURE DE SESSION ---

class EndSessionRequest(BaseModel):
    user_id: str
    session_id: str

@app.post("/api/session/end")
async def end_session(request: EndSessionRequest):
    print(f"🚪 [API] L'étudiant {request.user_id} ferme la session {request.session_id}. Lancement du bilan pédagogique...")
    
    try:
        # On appelle la fonction optimisée de ton MemoryManager
        await brain.memory.trigger_background_summary(request.user_id, request.session_id)
        
        return {"status": "success", "message": "Bilan de session généré et sauvegardé en mémoire longue avec succès."}
    
    except Exception as e:
        print(f"❌ [API] Erreur lors de la clôture de session: {e}")
        raise HTTPException(status_code=500, detail="Erreur lors de la génération du résumé de session.")
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)