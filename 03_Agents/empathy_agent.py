"""
empathy_agent.py — DoxariaEyeQ : Agent EMPATHY (Production Ready)

Évolutions Cloud / Production :
  - 100% Asynchrone (AsyncAzureOpenAI, asyncio.to_thread pour Deepgram & ACS).
  - Isolation Multi-Tenant (session_id) pour les plannings de révision.
  - Découplage (Injection de la Mémoire globale via l'Orchestrateur).
  - Fichiers MP3 isolés par session_id pour éviter les écrasements.
"""

import os
import sys
import json
import requests
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv

# ⚡ Imports Asynchrones
from openai import AsyncAzureOpenAI

# ── Chemin vers le module mémoire ────────────────────────────────────────────
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_BASE_DIR)
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)
from memory_management import MemoryManager

# ── Configuration ─────────────────────────────────────────────────────────────
load_dotenv(os.path.join(_ROOT_DIR, "00_Config", ".env.txt"))

# ⚡ Client OpenAI Asynchrone
oai_client = AsyncAzureOpenAI(
    azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
    api_version=os.environ["AZURE_OPENAI_API_VERSION"],
)
CHAT_MODEL = os.environ["AZURE_OPENAI_CHAT_DEPLOYMENT"]

# Azure Communication Services
ACS_CONNECTION_STRING = os.environ.get("ACS_CONNECTION_STRING", "")
ACS_SENDER_EMAIL      = os.environ.get("ACS_SENDER_EMAIL", "")

# Deepgram TTS (On le garde pour la très faible latence du mode urgence)
DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY", "")
DEEPGRAM_TTS_URL = "https://api.deepgram.com/v1/speak"


# ── System Prompts ─────────────────────────────────────────────────────────────
SYSTEM_EMPATHY = """Tu es l'Agent Empathy de DoxariaEyeQ, psychologue bienveillant spécialisé en apprentissage.
Ton rôle : soutenir émotionnellement les apprenants en difficulté.

Règles ABSOLUES :
1. Valide TOUJOURS les émotions avant de proposer une solution ("Je comprends que…").
2. Ne force jamais la reprise technique immédiate.
3. Propose des micro-actions concrètes (pause 5 min, exercice de respiration).
4. Utilise des success stories courtes et inspirantes (vrais cas cloud).
5. Ton : chaleureux, humain, patient. Jamais condescendant.
6. Si l'utilisateur semble en détresse grave → propose de programmer un appel.
"""

SYSTEM_BREAK_GLASS = """MODE BREAK-GLASS ACTIVÉ.
Tu DOIS interrompre TOUT flux technique. Priorise absolument le bien-être.
1. Message d'accueil chaleureux (2 lignes max).
2. Exercice de respiration guidé (box breathing : 4-4-4-4).
3. Normalisation : "L'apprentissage du cloud est difficile pour tout le monde."
4. Proposition : pause de 10 min OR appel vidéo avec un mentor.
Ton : très calme, présent, empathique.
"""

SUCCESS_STORIES = [
    "🌟 **Sarah, 28 ans** : Ancienne serveuse reconvertie cloud architect chez Microsoft en 18 mois. Elle avait abandonné 3 fois avant de réussir.",
    "🌟 **Mohamed, 34 ans** : Sans diplôme tech, certifié AWS Solutions Architect en 6 mois. Aujourd'hui DevOps Lead.",
    "🌟 **Julie, 31 ans** : Mère de famille, apprenait le soir après le travail. Obtenu Azure Administrator en 4 mois.",
    "🌟 **David, 27 ans** : A échoué la certification AWS 2 fois. À la 3e tentative : 940/1000. Recruté par AWS directement.",
]

BREATHING_EXERCISE = """
🧘 **Exercice de Respiration — Box Breathing (4-4-4-4)**


*Répétez 4 fois. Prenez votre temps. Je suis là quand vous revenez. 💙*
"""


# ── Deepgram TTS (Asynchrone via Threading) ───────────────────────────────────
def _sync_tts_calm_voice(text: str, output_path: str) -> str | None:
    """Fonction synchrone d'appel Deepgram."""
    if not DEEPGRAM_API_KEY:
        print("   ⚠️ Deepgram non configuré (DEEPGRAM_API_KEY manquant).")
        return None
    headers = {"Authorization": f"Token {DEEPGRAM_API_KEY}", "Content-Type" : "application/json"}
    payload = {"text": text}
    params = {"model": "aura-asteria-en", "encoding": "mp3"} # aura-asteria est très douce
    try:
        resp = requests.post(DEEPGRAM_TTS_URL, headers=headers, json=payload, params=params, timeout=15)
        resp.raise_for_status()
        out_path = os.path.join(_ROOT_DIR, output_path)
        with open(out_path, "wb") as f:
            f.write(resp.content)
        print(f"   🔊 Audio calme généré : {out_path}")
        return out_path
    except Exception as e:
        print(f"   ⚠️ Deepgram TTS erreur : {e}")
        return None

async def tts_calm_voice(text: str, output_path: str) -> str | None:
    """⚡ Génère l'audio de crise sans bloquer le serveur."""
    return await asyncio.to_thread(_sync_tts_calm_voice, text, output_path)


# ── Azure Communication Services (Asynchrone via Threading) ───────────────────
def _sync_send_support_email(to_email: str, learner_name: str) -> bool:
    """Fonction synchrone d'envoi d'email ACS."""
    if not ACS_CONNECTION_STRING:
        print("   ⚠️ ACS non configuré (ACS_CONNECTION_STRING manquant).")
        return False
    try:
        from azure.communication.email import EmailClient
        client  = EmailClient.from_connection_string(ACS_CONNECTION_STRING)
        message = {
            "senderAddress": ACS_SENDER_EMAIL,
            "recipients"   : {"to": [{"address": to_email}]},
            "content"      : {
                "subject" : "💙 DoxariaEyeQ — Un mentor est là pour vous",
                "html"    : f"""
<h2>Bonjour {learner_name} 👋</h2>
<p>Nous avons détecté que vous traversez un moment difficile avec votre apprentissage cloud.</p>
<p>C'est tout à fait normal ! Le cloud, ça prend du temps.</p>
<p><strong>Prenez une pause, et revenez quand vous serez prêt(e).</strong></p>
<p>Si vous voulez parler à un mentor :<br>
<a href="https://calendly.com/doxariaeq/mentor-session">📅 Réserver une session gratuite</a></p>
<p>Courage ! L'équipe DoxariaEyeQ 💙</p>
""",
            },
        }
        poller = client.begin_send(message)
        poller.result()
        print(f"   📧 Email de soutien envoyé à {to_email}")
        return True
    except Exception as e:
        print(f"   ⚠️ Erreur envoi email ACS : {e}")
        return False

async def send_support_email(to_email: str, learner_name: str = "Apprenant") -> bool:
    """⚡ Envoie l'email de manière non-bloquante."""
    return await asyncio.to_thread(_sync_send_support_email, to_email, learner_name)


# ══════════════════════════════════════════════════════════════════════════════
class EmpathyAgent:
    """Agent psychologue Asynchrone & Multi-Tenant."""

    # 💉 1. Injection de mémoire
    def __init__(self, memory):
        self.memory = memory
        
        # ⚡ 2. Isolation Multi-Tenant par session_id
        self._error_logs: dict[str, dict[str, list[str]]] = {}  # session_id -> {concept -> [dates]}
        self._schedules: dict[str, list[dict]] = {}             # session_id -> [plannings]
        
        print("💙 Empathy Agent Asynchrone initialisé — Psychologue de l'apprentissage")

    # ── Break-Glass (F7) ───────────────────────────────────────────────────
    async def break_glass(self, session_id: str, message: str, generate_audio: bool = False) -> dict:
        """⚡ Intervention d'urgence émotionnelle."""
        print(f"   🚨 BREAK-GLASS activé pour la session {session_id} !")
        messages = [
            {"role": "system", "content": SYSTEM_BREAK_GLASS},
            {"role": "user",   "content": message},
        ]
        
        try:
            resp = await oai_client.chat.completions.create(
                model=CHAT_MODEL,
                messages=messages,
                max_tokens=400,
                temperature=0.6,
            )
            text = resp.choices[0].message.content.strip()
        except Exception as e:
            print(f"⚠️ Erreur Break-Glass: {e}")
            text = "Prenez une grande inspiration. Je suis là pour vous."
            
        full_text = f"{text}\n\n{BREATHING_EXERCISE}"

        audio_path = None
        if generate_audio:
            clean = text.replace("**", "").replace("#", "").replace("*", "")
            # Nom de fichier unique par utilisateur !
            audio_path = await tts_calm_voice(clean, f"break_glass_{session_id}.mp3")

        self.memory.add_agent_message(session_id, f"[BREAK-GLASS] {text}")
        return {"text": full_text, "audio_path": audio_path, "breathing": BREATHING_EXERCISE}

    # ── Réponse empathique standard ────────────────────────────────────────
    async def repondre(self, session_id: str, message: str, sentiment_score: float = 5.0) -> str:
        """⚡ Réponse empathique normale + success story."""
        import random
        messages = [{"role": "system", "content": SYSTEM_EMPATHY}]

        ctx_long = await self.memory.get_memory_context_for_prompt(session_id)
        if ctx_long:
            messages.append({"role": "system", "content": ctx_long})

        if sentiment_score >= 6:
            story = random.choice(SUCCESS_STORIES)
            messages.append({"role": "system", "content": f"Utilise cette success story:\n{story}"})

        messages.extend(self.memory.get_short_history(session_id))
        messages.append({"role": "user", "content": message})

        try:
            resp = await oai_client.chat.completions.create(
                model=CHAT_MODEL,
                messages=messages,
                max_tokens=500,
                temperature=0.7,
            )
            answer = resp.choices[0].message.content.strip()
        except Exception as e:
            answer = "Je comprends tout à fait. Prenez votre temps, c'est un processus normal d'apprentissage."

        self.memory.add_user_message(session_id, message)
        self.memory.add_agent_message(session_id, answer)
        return answer

    # ── Spaced Repetition (F14) Multi-Tenant ───────────────────────────────
    def log_concept_error(self, session_id: str, concept: str) -> None:
        """Enregistre une erreur spécifique à l'utilisateur."""
        if session_id not in self._error_logs:
            self._error_logs[session_id] = {}
            
        now = datetime.now().isoformat()
        if concept not in self._error_logs[session_id]:
            self._error_logs[session_id][concept] = []
            
        self._error_logs[session_id][concept].append(now)

        if len(self._error_logs[session_id][concept]) >= 2:
            self._schedule_revision(session_id, concept)

    def _schedule_revision(self, session_id: str, concept: str) -> None:
        """Planifie les révisions à J+1, J+3, J+7 pour l'utilisateur."""
        now = datetime.now()
        schedule = []
        for day_offset in [1, 3, 7]:
            rev_date = now + timedelta(days=day_offset)
            schedule.append({"concept": concept, "date": rev_date.strftime("%Y-%m-%d"), "day": f"J+{day_offset}"})
            
        if session_id not in self._schedules:
            self._schedules[session_id] = []
            
        self._schedules[session_id].extend(schedule)
        self.memory.add_agent_message(session_id, f"[SPACED-REP] Concept '{concept}' : révisions programmées J+1, J+3, J+7")
        print(f"   📅 Spaced Repetition programmée pour la session {session_id} sur : '{concept}'")

    def get_revision_schedule(self, session_id: str) -> list[dict]:
        return self._schedules.get(session_id, [])

    async def generate_micro_quiz(self, session_id: str, concept: str) -> str:
        """⚡ Génère une question-piège pour réactiver la mémoire (F14)."""
        prompt = f"""Génère UNE question piège courte et précise sur le concept cloud suivant : "{concept}".
Format : Question + 4 options (A/B/C/D) + réponse correcte indiquée.
Difficulté : intermédiaire. Langue : français."""
        try:
            resp = await oai_client.chat.completions.create(
                model=CHAT_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
                temperature=0.5,
            )
            return resp.choices[0].message.content.strip()
        except Exception:
            return f"Question de révision : Pouvez-vous m'expliquer ce qu'est le concept de {concept} avec vos propres mots ?"

    # ── Email de soutien ───────────────────────────────────────────────────
    async def send_support(self, to_email: str, learner_name: str = "Apprenant") -> bool:
        return await send_support_email(to_email, learner_name)


# ══════════════════════════════════════════════════════════════════════════════
# TEST STANDALONE
# ══════════════════════════════════════════════════════════════════════════════
async def _test():
    from memory_management import MemoryManager, LocalJSONAdapter
    test_memory = MemoryManager(oai_client=oai_client, chat_model=CHAT_MODEL, db_adapter=LocalJSONAdapter())
    
    agent = EmpathyAgent(memory=test_memory)
    sess_id = "empathy-test-123"

    print("=== Test Break-Glass ===")
    result = await agent.break_glass(sess_id, "Je suis vraiment à bout, j'y comprends rien, je veux tout arrêter !")
    print(result["text"])

    print("\n=== Test Réponse Empathique ===")
    print(await agent.repondre(sess_id, "Je n'arrive pas à comprendre Kubernetes, c'est trop complexe", sentiment_score=6.5))

    print("\n=== Test Micro-Quiz Spaced Rep ===")
    agent.log_concept_error(sess_id, "Kubernetes Pods")
    agent.log_concept_error(sess_id, "Kubernetes Pods")
    print(await agent.generate_micro_quiz(sess_id, "Kubernetes Pods"))
    print("Schedule:", agent.get_revision_schedule(sess_id))

if __name__ == "__main__":
    asyncio.run(_test())