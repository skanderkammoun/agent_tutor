"""
supervisor_agent.py — : Agent SUPERVISOR (Production Ready)

Évolutions Cloud / Production :
  - 100% Asynchrone (AsyncAzureOpenAI, aio TextAnalyticsClient).
  - Multi-Tenant (session_id) pour l'Adaptative Scoring et le Feedback RLHF.
  - Découplage (Injection de la Mémoire globale via l'Orchestrateur).
  - JSON Mode robuste pour l'intention.
"""

import os
import sys
import json
import asyncio
from dotenv import load_dotenv

# ⚡ Imports Asynchrones
from openai import AsyncAzureOpenAI
from azure.ai.textanalytics.aio import TextAnalyticsClient # ⚡ SDK Asynchrone
from azure.core.credentials import AzureKeyCredential

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
CHAT_MODEL = os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"]

# ⚡ Client Sentiment Analysis Asynchrone
lang_client = TextAnalyticsClient(
    endpoint=os.environ["AZURE_LANGUAGE_ENDPOINT"],
    credential=AzureKeyCredential(os.environ["AZURE_LANGUAGE_API_KEY"]),
)

# ── Constantes ────────────────────────────────────────────────────────────────
ROUTING_TABLE = {
    "TECHNIQUE"   : "CloudTutor",
    "COMPARAISON" : "Architecte",
    "FICHIER"     : "Builder",
    "EMOTIONNEL"  : "Empathy",
    "ROLEPLAY"    : "CloudTutor",
}

SYSTEM_CLASSIFY = """Tu es le module NLU (Intelligence de Routage) du Supervisor Subul.
Analyse le message et retourne UNIQUEMENT un JSON.

RÈGLES DE ROUTAGE :
1. TECHNIQUE : Toute question demandant une explication, une définition (ex: "C'est quoi EC2 ?"), de l'aide sur du code ou un concept Cloud. -> Agent: CloudTutor.
2. COMPARAISON : Demande de différences entre services ou fournisseurs (AWS vs Azure). -> Agent: Architecte.
3. FICHIER : Uniquement si l'utilisateur demande EXPLICITEMENT de CRÉER, GÉNÉRER ou TÉLÉCHARGER un PDF, un document, une flashcard ou un podcast audio. -> Agent: Builder.
4. EMOTIONNEL : Signes de frustration, colère, fatigue ou besoin de motivation. -> Agent: Empathy.
5. ROLEPLAY : Demande de mise en situation, simulation de panne ou exercice d'incident. -> Agent: CloudTutor.

JSON attendu :
{
  "intent": "<TECHNIQUE|COMPARAISON|FICHIER|EMOTIONNEL|ROLEPLAY>",
  "cloud_target": "<AWS|AZURE|GCP|MULTI|null>",
  "has_code_block": <true|false>,
  "volatile_entity": <true|false>,
  "reason": "explication courte"
}
"""

SCENARIO_TEMPLATES = {
    "aws"  : "⚠️ INCIDENT ROLEPLAY AWS : Votre application e-commerce sur EC2 est DOWN. Le load balancer retourne des 503.",
    "azure": "⚠️ INCIDENT ROLEPLAY Azure : Votre Function App Azure est en état d'erreur (Timeout Cosmos DB).",
    "gcp"  : "⚠️ INCIDENT ROLEPLAY GCP : Votre cluster GKE ne répond plus (CrashLoopBackOff).",
}


# ══════════════════════════════════════════════════════════════════════════════
class SupervisorAgent:
    """Agent orchestrateur central Asynchrone & Multi-Tenant."""

    # 💉 1. Injection de la mémoire partagée
    def __init__(self, memory):
        self.memory = memory
        
        # ⚡ 2. Isolation Multi-Tenant (Données en RAM isolées par session)
        self._feedback_logs: dict[str, list[dict]] = {} # session_id -> list
        self._adaptive_scores: dict[str, float] = {}    # session_id -> score
        
        print("🧠 Supervisor Asynchrone initialisé — Subul Orchestrateur")

    # ── Intent Classification (Asynchrone + JSON Mode) ──────────────────────
    async def classify_intent(self, message: str) -> dict:
        """⚡ Classification NLU non-bloquante."""
        try:
            resp = await oai_client.chat.completions.create(
                model=CHAT_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_CLASSIFY},
                    {"role": "user",   "content": message},
                ],
                max_tokens=200,
                temperature=0.0,
                response_format={"type": "json_object"}, # 👈 JSON Mode Azure OpenAI
            )
            return json.loads(resp.choices[0].message.content.strip())
        except Exception as e:
            print(f"⚠️ [Supervisor NLU] Erreur: {e}")
            return {"intent": "TECHNIQUE", "cloud_target": None, "reason": "fallback"}

    # ── Sentiment Analysis (Asynchrone via SDK aio) ─────────────────────────
    async def analyze_sentiment(self, message: str) -> dict:
        """⚡ Appel asynchrone au service Azure Language."""
        try:
            # Note: on utilise 'async with' si on veut fermer le client, 
            # mais ici on utilise le client global lang_client.
            results = await lang_client.analyze_sentiment(documents=[message])
            result = results[0]
            
            if result.is_error:
                return {"score": 5.0, "label": "neutral"}

            # On transforme le score de confiance négatif en échelle 0-10
            score = round(result.confidence_scores.negative * 10, 1)
            return {"score": score, "label": result.sentiment}
        except Exception as e:
            print(f"⚠️ [Supervisor Sentiment] Erreur: {e}")
            return {"score": 5.0, "label": "neutral"}

    # ── Routing Principal (Asynchrone + Multi-Tenant) ───────────────────────
    async def route(self, session_id: str, message: str) -> dict:
        """⚡ Point d'entrée asynchrone utilisé par l'orchestrateur."""
        
        # ⚡ Lancement des analyses en PARALLÈLE pour gagner du temps
        intent_task = self.classify_intent(message)
        sentiment_task = self.analyze_sentiment(message)
        
        intent_data, sentiment = await asyncio.gather(intent_task, sentiment_task)

        intent = intent_data.get("intent", "TECHNIQUE")
        cloud = intent_data.get("cloud_target")

        # Règle de sécurité : Détresse détectée -> Override vers Empathy
        if sentiment["score"] >= 8:
            intent = "EMOTIONNEL"

        agent = ROUTING_TABLE.get(intent, "CloudTutor")
        mode = "roleplay" if intent == "ROLEPLAY" else "instructeur"

        # Mise à jour du score adaptatif spécifique à cet utilisateur
        self._update_adaptive_score(session_id, sentiment["score"])

        decision = {
            "agent": agent,
            "intent": intent,
            "cloud_target": cloud,
            "mode": mode,
            "volatile": intent_data.get("volatile_entity", False),
            "has_code": intent_data.get("has_code_block", False),
            "sentiment": sentiment,
            "reason": intent_data.get("reason", ""),
        }

        # Persistance des décisions de routage pour analyse ultérieure
        self.memory.add_agent_message(session_id, f"[SUPERVISOR] Route: {agent} | Intent: {intent}")
        
        return decision

    # ── RLHF Feedback Loop ──────────────────────────────────────────────────
    def record_feedback(self, session_id: str, message_id: str, rating: str, comment: str = "") -> None:
        """Enregistre le feedback Like/Dislike par session."""
        if session_id not in self._feedback_logs:
            self._feedback_logs[session_id] = []
            
        entry = {"id": message_id, "rating": rating, "comment": comment, "ts": datetime.now().isoformat()}
        self._feedback_logs[session_id].append(entry)
        
        self.memory.add_agent_message(session_id, f"[RLHF] {rating} sur {message_id}")
        print(f"   👍👎 Feedback {rating} reçu pour {session_id}")

    # ── Roleplay Trigger ─────────────────────────────────────────────────────
    async def trigger_roleplay(self, cloud: str = "azure") -> str:
        """Génère le scénario (Synchrone car simple dictionnaire)."""
        key = (cloud or "azure").lower()
        return SCENARIO_TEMPLATES.get(key, SCENARIO_TEMPLATES["azure"])

    # ── Adaptive Logic ───────────────────────────────────────────────────────
    def _update_adaptive_score(self, session_id: str, sentiment_score: float) -> None:
        """Ajuste le niveau par session."""
        current = self._adaptive_scores.get(session_id, 5.0)
        
        if sentiment_score >= 7.0: # Stress -> On baisse la difficulté
            new_score = max(1.0, current - 1.0)
        elif sentiment_score <= 3.0: # Serein -> On augmente
            new_score = min(10.0, current + 0.5)
        else:
            new_score = current
            
        self._adaptive_scores[session_id] = new_score

    def get_session_level(self, session_id: str) -> float:
        return self._adaptive_scores.get(session_id, 5.0)

# # ══════════════════════════════════════════════════════════════════════════════
# # TEST STANDALONE
# # ══════════════════════════════════════════════════════════════════════════════
# async def _test():
#     from memory_management import MemoryManager, LocalJSONAdapter
#     test_memory = MemoryManager(oai_client=oai_client, chat_model=CHAT_MODEL, db_adapter=LocalJSONAdapter())
    
#     sup = SupervisorAgent(memory=test_memory)
#     sess = "debug-session-001"

#     print("\n📨 Test Routing Technique:")
#     d1 = await sup.route(sess, "Comment créer un VPC sur AWS ?")
#     print(f"Agent: {d1['agent']} | Target: {d1['cloud_target']}")

#     print("\n📨 Test Routing Détresse:")
#     d2 = await sup.route(sess, "C'EST TROP DUR J'EN AI MARRE !")
#     print(f"Agent: {d2['agent']} | Score Sentiment: {d2['sentiment']['score']}/10")

# if __name__ == "__main__":
#     asyncio.run(_test())