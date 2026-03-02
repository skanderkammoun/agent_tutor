import asyncio
import os
import sys
from dotenv import load_dotenv

# Import pour la détection de langue (pip install langdetect)
from langdetect import detect

# 🛠️ GESTION DES CHEMINS & CONFIG
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_CURRENT_DIR)
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

env_path = os.path.join(_ROOT_DIR, "00_Config", ".env.txt")
load_dotenv(dotenv_path=env_path)

# --- IMPORTS DE TES MICROSERVICES LOKAUX ---
# Assure-toi que stt_deepgram.py, tts_deepgram.py et agent_rag.py sont dans le même dossier
from stt_deepgram import SpeechToText
from tts_deepgram import TextToSpeech
from agent_rag import BrainAgent


class Orchestrator:
    def __init__(self):
        self.stt = SpeechToText()
        self.tts = TextToSpeech()
        self.brain = BrainAgent()
        self.audio_queue = asyncio.Queue()

    async def audio_worker(self, detected_lang: str):
        """Worker asynchrone qui lit les phrases envoyées par le LLM."""
        while True:
            text = await self.audio_queue.get()
            if text is None: break  # Signal d'arrêt
            # Lecture audio dans un thread séparé pour ne pas bloquer l'Event Loop
            await asyncio.to_thread(self.tts.speak, text, detected_lang)
            self.audio_queue.task_done()

    async def main_loop(self):
        # 1. Préparation du Cerveau (Vérification de l'index RAG)
        await self.brain.setup()
        
        print("\n✅ Subul est en ligne ! (Mode Hybride & Bilingue)")
        print("-" * 70)

        while True:
            # 2. LE CHOIX DE L'UTILISATEUR (Hybride)
            print("\n" + "="*70)
            user_input = await asyncio.to_thread(input, "⌨️ Tapez votre message (ou appuyez juste sur 'Entrée' pour parler au micro) : ")
            
            is_audio = False
            
            if user_input.strip() == "":
                # Mode VOCAL : L'utilisateur n'a rien tapé, on active les Oreilles (STT)
                is_audio = True
                user_input = await self.stt.listen()
                if not user_input: continue
                print(f"🗣️ Vous (Micro) : {user_input}")
            else:
                # Mode TEXTE : L'utilisateur a utilisé le clavier
                print(f"🗣️ Vous (Clavier) : {user_input}")
            
            # Conditions de sortie
            lower_input = user_input.lower()
            if "au revoir" in lower_input or "goodbye" in lower_input or "quit" in lower_input or "exit" in lower_input:
                print("\n👋 Fermeture de l'assistant.")
                break

            # 3. DÉTECTION DE LA LANGUE
            try:
                lang = detect(user_input)
                lang = "fr" if "fr" in lang else "en" 
            except:
                lang = "fr" # Par défaut en cas de doute

            print(f"🌍 Langue : {lang.upper()} | 🎙️ Mode Audio : {is_audio}")

            # 4. PRÉPARATION DE L'AGENT ET DE LA BOUCHE
            agent = self.brain.get_agent(lang, is_audio)
            
            audio_task = None
            if is_audio:
                # On allume la Bouche uniquement si on est en mode vocal
                audio_task = asyncio.create_task(self.audio_worker(lang))

            # 5. RÉFLEXION ET STREAMING (Le cœur de la basse latence)
            # 5. RÉFLEXION ET LECTURE AUDIO (Adapté RC1)
            try:
                # On utilise run() au lieu de run_stream() pour cette version du framework
                response = await agent.run(user_input)
                full_text = response.text
                
                print(f"🤖 Subul : {full_text}")

                # Si on est en vocal, on découpe le texte en phrases pour fluidifier le TTS
                if is_audio:
                    import re
                    # On découpe intelligemment à chaque point, point d'exclamation ou interrogation
                    sentences = re.split(r'(?<=[.!?]) +', full_text)
                    for sentence in sentences:
                        clean_sentence = sentence.strip()
                        if clean_sentence:
                            await self.audio_queue.put(clean_sentence)

            except Exception as e:
                print(f"\n❌ Erreur LLM/Agent: {e}")

            # 6. ATTENTE ET NETTOYAGE
            if is_audio:
                # Attendre que la dernière phrase soit prononcée
                await self.audio_queue.put(None)
                await audio_task
                self.audio_queue = asyncio.Queue() # Reset pour le prochain tour

if __name__ == "__main__":
    app = Orchestrator()
    asyncio.run(app.main_loop())