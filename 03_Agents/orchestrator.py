"""
orchestrator.py — : Workflow Multi-Agent (Version Asynchrone, Multi-Tenant & STREAMING 🌊)
"""

import os
import sys
import uuid
import json  # 👈 Nouvel import crucial pour le streaming JSON
from dotenv import load_dotenv

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))  
_ROOT_DIR = os.path.dirname(_BASE_DIR)                    
load_dotenv(os.path.join(_ROOT_DIR, "00_Config", ".env.txt"))

if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

try:
    from supervisor_agent  import SupervisorAgent
    from cloud_tutor_agent import CloudTutorAgent
    from architecte_agent  import ArchitecteAgent
    from empathy_agent     import EmpathyAgent
    from builder_agent     import BuilderAgent
    
    # ⚡ Imports pour la Mémoire Cloud
    from memory_management import MemoryManager, CosmosDBAdapter, LocalJSONAdapter
    from openai import AsyncAzureOpenAI
    
    print("✅ Tous les agents ont été importés avec succès.")
except ImportError as e:
    print(f"❌ Erreur d'importation : {e}")
    sys.path.append(_ROOT_DIR)


# ══════════════════════════════════════════════════════════════════════════════
class SubulOrchestrator:
    def __init__(self, learner_profile: dict | None = None):
        self.profile = learner_profile or {
            "name": "Apprenant", "level": "intermédiaire",
            "background": None, "email": None,
        }
        
        # 🔑 1. Gestion de l'état de session (MULTI-TENANT)
        self._session_id     = uuid.uuid4().hex[:12]
        self._message_count  = 0
        self._concept_errors : dict[str, int] = {}
        self._in_roleplay    = False
        self._roleplay_scenario: str | None = None

        print("\n" + "═"*60)
        print("  🚀 Subul — Plateforme Multi-Agent Cloud (Mode Streaming)")
        print(f"  🆔 Session ID : {self._session_id}")
        print("═"*60 + "\n")

        # ☁️ 2. Configuration de l'Adaptateur de Base de données
        env_mode = os.environ.get("ENVIRONMENT", "development").lower()
        
        if env_mode == "production":
            print("🌍 [Orchestrator] Mode Production : Connexion à Azure Cosmos DB...")
            db_adapter = CosmosDBAdapter(
                endpoint=os.environ["AZURE_COSMOS_ENDPOINT"],
                key=os.environ["AZURE_COSMOS_KEY"],
                db_name=os.environ["AZURE_COSMOS_DATABASE_NAME"],
                container_name=os.environ["AZURE_COSMOS_CONTAINER_NAME"]
            )
        else:
            print("💻 [Orchestrator] Mode Local : Utilisation du Fallback JSON...")
            db_adapter = LocalJSONAdapter()

        # 🧠 3. Création de la MÉMOIRE GLOBALE UNIQUE
        oai_client = AsyncAzureOpenAI(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
            api_version=os.environ["AZURE_OPENAI_API_VERSION"]
        )
        self.global_memory = MemoryManager(
            oai_client=oai_client,
            chat_model=os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o-mini"),
            db_adapter=db_adapter
        )

        # 💉 4. INJECTION DE DÉPENDANCE (Même mémoire pour tous)
        self.supervisor  = SupervisorAgent(memory=self.global_memory)
        self.cloud_tutor = CloudTutorAgent(memory=self.global_memory, user_background=self.profile.get("background"))
        self.architecte  = ArchitecteAgent(memory=self.global_memory)
        self.empathy     = EmpathyAgent(memory=self.global_memory)
        self.builder     = BuilderAgent(memory=self.global_memory)

    # 🌊 5. PROCESSUS EN STREAMING (Génère des blocs JSON ligne par ligne)
    async def process_stream(self, user_message: str):
        self._message_count += 1
        msg_id = f"{self._session_id}-{self._message_count:04d}"

        print(f"\n{'─'*60}")
        print(f"📨 [{msg_id}] Message reçu : {user_message[:80]}...")

        # ── Commandes spéciales
        cmd = await self._handle_special_commands(user_message.strip().lower())
        if cmd:
            yield json.dumps({"agent_used": "System", "chunk": cmd["response"]}) + "\n"
            return

        # ── Mode Roleplay en cours d'annulation
        if self._in_roleplay and self._roleplay_scenario:
            # Pour simplifier, on vérifie d'abord si on sort du roleplay
            if any(k in user_message.lower() for k in ["bilan", "fin du scénario", "exercice terminé"]):
                self._in_roleplay = False
                self._roleplay_scenario = None
                print("   🎭 Fin du mode Roleplay")
                yield json.dumps({"agent_used": "CloudTutor (Roleplay)", "chunk": "Fin de l'exercice. Je génère le bilan..."}) + "\n"
                return
            
            # Sinon on stream le roleplay
            async for chunk in self.cloud_tutor.repondre_stream(
                session_id=self._session_id, user_message=user_message, mode="roleplay", scenario=self._roleplay_scenario
            ):
                yield json.dumps({"agent_used": "CloudTutor (Roleplay)", "chunk": chunk}) + "\n"
            return

        # ── Supervisor : routing sémantique (F2)
        routing = await self.supervisor.route(session_id=self._session_id, message=user_message)
        agent   = routing["agent"]
        intent  = routing["intent"]
        mode    = routing["mode"]
        sentiment = routing["sentiment"]
        volatile  = routing["volatile"]
        has_code  = routing["has_code"]
        cloud     = routing["cloud_target"]

        # ══ CASE : BREAK-GLASS (F7)
        if sentiment["score"] >= 8.0:
            bg_result = await self.empathy.break_glass(session_id=self._session_id, message=user_message, generate_audio=False)
            yield json.dumps({"agent_used": "Empathy [BREAK-GLASS]", "chunk": bg_result["text"]}) + "\n"
            return

        # ══ CASE : EMOTIONNEL / EMPATHY
        if agent == "Empathy":
            response = await self.empathy.repondre(session_id=self._session_id, message=user_message, sentiment_score=sentiment["score"])
            yield json.dumps({"agent_used": "Empathy Agent", "chunk": response}) + "\n"
            return

        # ══ CASE : BUILDER / FICHIER
        elif agent == "Builder":
            response, arts = await self._handle_builder(session_id=self._session_id, message=user_message)
            yield json.dumps({"agent_used": "Builder", "chunk": response, "artifacts": arts}) + "\n"
            return

        # ══ CASE : ARCHITECTE / COMPARAISON
        elif agent == "Architecte":
            response = await self.architecte.repondre(session_id=self._session_id, user_message=user_message, fetch_live=volatile or True)
            yield json.dumps({"agent_used": "Architecte", "chunk": response}) + "\n"
            return

        # ══ CASE : CLOUD TUTOR (TECHNIQUE + ROLEPLAY) STREAMING 🌊
        else:  
            if mode == "roleplay":
                scenario = await self.supervisor.trigger_roleplay(cloud or "azure")
                self._in_roleplay = True
                self._roleplay_scenario = scenario
                async for chunk in self.cloud_tutor.repondre_stream(
                    session_id=self._session_id, user_message=user_message, mode="roleplay",
                    cloud_target=cloud, volatile=volatile, scenario=scenario
                ):
                    yield json.dumps({"agent_used": "CloudTutor (Roleplay)", "chunk": chunk}) + "\n"
            else:
                async for chunk in self.cloud_tutor.repondre_stream(
                    session_id=self._session_id, user_message=user_message, mode="instructeur",
                    cloud_target=cloud, volatile=volatile
                ):
                    yield json.dumps({"agent_used": "CloudTutor", "chunk": chunk}) + "\n"

    # ── Helpers
    async def _handle_special_commands(self, cmd: str) -> dict | None:
        if cmd in ("quit", "exit", "quitter"):
            await self.end_session()
            return {"agent_used": "System", "response": "👋 Session sauvegardée. À bientôt !"}
        return None

    async def end_session(self) -> None:
        """Clôture propre. L'Orchestrateur est le SEUL à appeler la mémoire."""
        print("\n📦 Clôture de la session…")
        resume = await self.global_memory.end_session(self._session_id)
        if resume:
            print(f"✅ Session sauvegardée dans Cosmos DB avec succès. Résumé généré : {len(resume)} caractères.")

    async def _handle_builder(self, session_id: str, message: str) -> tuple[str, list]:
        """Déclenche la génération d'artefacts proprement."""
        
        # 🧹 On supprime l'instruction système pour que le titre du PDF soit propre
        clean_msg = message.split("\n\n[Instruction stricte:")[0].split("\n\n[Strict Instruction:")[0]
        
        # On extrait le sujet sans les préfixes
        topic = clean_msg.replace("Génère un PDF sur", "").replace("Generate a PDF about", "").strip()
        
        if "pdf" in clean_msg.lower():
            res = await self.builder.generate_pdf(session_id, topic, clean_msg)
            return res["message"], [{"type": "PDF", "url": res["url"]}]
        
        elif "flashcard" in clean_msg.lower():
            res = await self.builder.generate_flashcard(session_id, topic, clean_msg)
            return res["message"], [{"type": "MD", "url": res["url"]}]
            
        return "Je peux générer des PDF ou des Flashcards. Que souhaitez-vous ?", []
        
