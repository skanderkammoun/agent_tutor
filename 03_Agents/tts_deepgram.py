import os
import shutil
import subprocess
import requests

class TextToSpeech:
    def __init__(self):
        self.DG_API_KEY = os.getenv("DEEPGRAM_API_KEY")
        
        # 🧠 ROUTAGE DES VOIX SELON LA LANGUE
        self.VOICE_MODELS = {
            "en": "aura-helios-en",  # Modèle Anglais
            "fr": "aura-luna-fr"     # Remplace par le modèle FR Deepgram que tu utilises
        }

    @staticmethod
    def is_installed(lib_name: str) -> bool:
        return shutil.which(lib_name) is not None

    def speak(self, text: str, lang: str = "fr"):
        if not text.strip(): return
        if not self.is_installed("ffplay"):
            print("⚠️ ffplay non trouvé.")
            return

        # Sélection dynamique de la voix
        model_name = self.VOICE_MODELS.get(lang, self.VOICE_MODELS["en"])
        print(f"🔊 [TTS] Lecture en {lang.upper()} avec {model_name}...")

        DEEPGRAM_URL = f"https://api.deepgram.com/v1/speak?model={model_name}&performance=some&encoding=linear16&sample_rate=24000"
        headers = {
            "Authorization": f"Token {self.DG_API_KEY}",
            "Content-Type": "application/json"
        }

        player_command = ["ffplay", "-autoexit", "-", "-nodisp"]
        player_process = subprocess.Popen(
            player_command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

        try:
            with requests.post(DEEPGRAM_URL, stream=True, headers=headers, json={"text": text}) as r:
                for chunk in r.iter_content(chunk_size=1024):
                    if chunk:
                        player_process.stdin.write(chunk)
                        player_process.stdin.flush()
        except Exception as e:
            print(f"❌ Erreur TTS: {e}")
        finally:
            if player_process.stdin:
                player_process.stdin.close()
            player_process.wait()