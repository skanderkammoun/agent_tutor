"""
memory_management.py — Gestion de Mémoire Cloud-Native (Production Ready)

Évolutions Tech Lead :
    1. Stateless 100% : Le ShortMemory lit et écrit directement dans la DB (plus de RAM).
    2. Distinction User / Session : La mémoire longue suit l'étudiant, la courte suit la discussion.
    3. Résilience : Si le serveur redémarre, aucune conversation n'est perdue.
"""

import os
import json
import uuid
import asyncio
from datetime import datetime
from typing import List, Dict, Optional

try:
    import tiktoken as _tiktoken
    _TIKTOKEN_AVAILABLE = True
except ImportError:
    _tiktoken = None
    _TIKTOKEN_AVAILABLE = False

from openai import AsyncAzureOpenAI
from azure.cosmos.aio import CosmosClient
from azure.cosmos import exceptions

# ============================================================
# 0. ABSTRACTION DU STOCKAGE (Adaptateurs Cloud)
# ============================================================
class DatabaseAdapter:
    """Interface abstraite. Sépare clairement le Court Terme du Long Terme."""
    
    # --- Court Terme (Lié à la SESSION) ---
    async def save_message(self, user_id: str, session_id: str, role: str, content: str):
        raise NotImplementedError
        
    async def get_session_messages(self, session_id: str) -> List[Dict]:
        raise NotImplementedError

    # --- Long Terme (Lié à l'UTILISATEUR) ---
    async def save_long_term_memory(self, user_id: str, memory_type: str, content: str, subject: str):
        raise NotImplementedError
        
    async def get_user_memories(self, user_id: str) -> List[Dict]:
        raise NotImplementedError


class LocalJSONAdapter(DatabaseAdapter):
    """Fallback local parfait pour tes tests en stage sur ton PC."""
    def __init__(self, storage_dir: str = "./data"):
        self.storage_dir = storage_dir
        os.makedirs(self.storage_dir, exist_ok=True)

    # def _read(self, filename: str) -> List[Dict]:
    #     filepath = os.path.join(self.storage_dir, filename)
    #     if os.path.exists(filepath):
    #         with open(filepath, "r", encoding="utf-8") as f:
    #             return json.load(f)
    #     return []
    def _read(self, filename: str) -> List[Dict]:
        filepath = os.path.join(self.storage_dir, filename)
    
    # 🛡️ FIX 1 : On vérifie si le fichier existe ET s'il n'est pas vide (taille > 0)
        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                 return json.load(f)
            except json.JSONDecodeError:
            # 🛡️ FIX 2 : Si le JSON est mal formé, on ne crash pas !
            # On log l'erreur et on renvoie une liste vide pour que l'agent continue
                print(f"⚠️ Erreur : Le fichier {filename} est corrompu. On l'ignore.")
                return []
    
    # Si le fichier n'existe pas ou est vide
        return []
    def _write(self, filename: str, data: List[Dict]):
        filepath = os.path.join(self.storage_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    async def save_message(self, user_id: str, session_id: str, role: str, content: str):
        filename = f"short_term_{session_id}.json"
        data = self._read(filename)
        data.append({"role": role, "content": content, "timestamp": datetime.now().isoformat()})
        await asyncio.to_thread(self._write, filename, data)

    async def get_session_messages(self, session_id: str) -> List[Dict]:
        return self._read(f"short_term_{session_id}.json")

    async def save_long_term_memory(self, user_id: str, memory_type: str, content: str, subject: str):
        filename = f"long_term_{user_id}.json"
        data = self._read(filename)
        data.append({
            "id": str(uuid.uuid4()),
            "type": memory_type,
            "subject": subject,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        await asyncio.to_thread(self._write, filename, data)

    async def get_user_memories(self, user_id: str) -> List[Dict]:
        return self._read(f"long_term_{user_id}.json")


# ============================================================
# 1. SHORT MEMORY — Mémoire à court terme (Stateless)
# ============================================================
class ShortMemory:
    """
    Ne stocke PLUS RIEN en RAM ! 
    Récupère la fenêtre de contexte à la volée depuis la DB.
    """
    def __init__(self, db_adapter: DatabaseAdapter, max_tokens: int = 6000, model_name: str = "cl100k_base"):
        self.db = db_adapter
        self.max_tokens = max_tokens
        self._enc = _tiktoken.get_encoding(model_name) if _TIKTOKEN_AVAILABLE else None

    async def add(self, user_id: str, session_id: str, role: str, content: str):
        # On écrit directement en base de données
        await self.db.save_message(user_id, session_id, role, content)

    async def get_history(self, session_id: str) -> List[Dict[str, str]]:
        # 1. On lit tout l'historique de la session depuis la DB
        raw_messages = await self.db.get_session_messages(session_id)
        
        # 2. On calcule la fenêtre glissante (Pruning dynamique)
        valid_messages = []
        current_tokens = 0
        
        # On lit les messages à l'envers (du plus récent au plus ancien)
        for msg in reversed(raw_messages):
            tokens = len(self._enc.encode(msg["content"])) if self._enc else len(msg["content"]) // 4
            if current_tokens + tokens > self.max_tokens:
                break # On a atteint la limite de mémoire pour ce prompt
            valid_messages.insert(0, {"role": msg["role"], "content": msg["content"]})
            current_tokens += tokens
            
        return valid_messages


# ============================================================
# 2. LONG MEMORY — Mémoire de l'Étudiant
# ============================================================
class LongMemory:
    """Suit l'étudiant (user_id) à travers toutes ses sessions passées."""
    VALID_TYPES = ("summary", "fact", "skill_level")

    def __init__(self, db_adapter: DatabaseAdapter, max_context: int = 5):
        self.db = db_adapter
        self.max_context = max_context

    async def add_summary(self, user_id: str, summary: str, subject: str = ""):
        await self.db.save_long_term_memory(user_id, "summary", summary, subject)

    async def get_context_for_prompt(self, user_id: str) -> str:
        # On récupère les souvenirs de l'étudiant, pas de la session
        entries = await self.db.get_user_memories(user_id)
        if not entries:
            return ""
            
        # On prend les plus récents
        recent = entries[-self.max_context:][::-1]
        lines = []
        for e in recent:
            date = e["timestamp"][:10]
            icon = "📝" if e["type"] == "summary" else "🧠"
            subject = f"[{e['subject']}] " if e.get("subject") else ""
            lines.append(f"{icon} {date} — {subject}{e['content']}")
            
        return "\n".join(lines)


# ============================================================
# 3. MEMORY MANAGER — Le Cerveau Orchestrateur
# ============================================================
class MemoryManager:
    def __init__(self, oai_client: AsyncAzureOpenAI, chat_model: str, db_adapter: Optional[DatabaseAdapter] = None):
        self._client = oai_client
        self._chat_model = chat_model
        self.db_adapter = db_adapter or LocalJSONAdapter()

        self.short = ShortMemory(db_adapter=self.db_adapter)
        self.long = LongMemory(db_adapter=self.db_adapter)

    # 🚀 NOUVEAU : On exige le user_id ET le session_id
    async def add_user_message(self, user_id: str, session_id: str, content: str):
        await self.short.add(user_id, session_id, "user", content)

    async def add_agent_message(self, user_id: str, session_id: str, content: str):
        await self.short.add(user_id, session_id, "assistant", content)

    async def get_full_context(self, user_id: str, session_id: str) -> tuple[str, List[Dict[str, str]]]:
        """Récupère en même temps le passé de l'étudiant et la conversation en cours."""
        # Les appels sont asynchrones, on peut les faire en parallèle pour gagner du temps !
        long_task = self.long.get_context_for_prompt(user_id)
        short_task = self.short.get_history(session_id)
        
        long_ctx, short_hist = await asyncio.gather(long_task, short_task)
        
        formatted_long_ctx = f"📚 PROFIL & HISTORIQUE DE L'ÉTUDIANT :\n{long_ctx}" if long_ctx else ""
        return formatted_long_ctx, short_hist

    async def trigger_background_summary(self, user_id: str, session_id: str):
        """
        À appeler quand l'étudiant quitte la page ou après X minutes d'inactivité.
        Ne détruit pas la session, mais la résume pour le futur.
        """
        history = await self.short.get_history(session_id)
        if len(history) < 4:
            return # Pas assez de matière pour résumer

        print(f"\n💭 [MemoryManager] Génération du résumé pour {user_id} (Session: {session_id})...")
        historique_str = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in history)
        
        prompt = (
            "Tu es l'assistant de mémoire d'une plateforme e-learning Cloud.\n"
            "Résume les compétences acquises ou les difficultés rencontrées par cet étudiant "
            "lors de cette session. Sois précis sur les concepts techniques (ex: EC2, S3).\n\n"
            f"CONVERSATION :\n{historique_str}"
        )
        
        try:
            response = await self._client.chat.completions.create(
                model=self._chat_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.2
            )
            resume = response.choices[0].message.content.strip()
            # On sauvegarde le résumé pour cet étudiant précis
            await self.long.add_summary(user_id, resume, subject=f"Session {session_id[:8]}")
            print(f"✅ Résumé sauvegardé pour l'étudiant {user_id}")
        except Exception as e:
            print(f"⚠️ Erreur résumé Asynchrone: {e}")