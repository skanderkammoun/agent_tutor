import os
import sys
import asyncio
import json
import time 
import httpx 

from typing import Annotated
from pydantic import Field
from dotenv import load_dotenv

from memory_management import MemoryManager, LocalJSONAdapter

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_CURRENT_DIR)

if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

env_path = os.path.join(_ROOT_DIR, "00_Config", ".env.txt")
if os.path.exists(env_path):
    print(f"📂 Configuration chargée depuis : {env_path}")
    load_dotenv(dotenv_path=env_path)
else:
    print(f"❌ Erreur : Fichier config introuvable à {env_path}")

from search_index_manager import SearchIndexManager
from azure.core.credentials import AzureKeyCredential
from openai import AsyncAzureOpenAI

# ============================================================
# 🛡️ LE DESIGN PATTERN PROXY : Bypass Agent pour le Streaming
# ============================================================
class MemoryAgentProxy:
    def __init__(self, memory_manager: MemoryManager, search_manager: SearchIndexManager, oai_client: AsyncAzureOpenAI, chat_model: str, instructions: str):
        self.memory = memory_manager
        self.search_manager = search_manager
        self.oai_client = oai_client       
        self.chat_model = chat_model       
        self.instructions = instructions   

    async def run_stream(self, message: str, user_id: str, session_id: str):
        print("\n⏱️ --- DÉBUT DU CHRONO (ULTRA-RÉSILIENT) ---")
        t0 = time.time()

        # 🚀 Lancement des tâches SANS BLOQUER
        task_history = asyncio.create_task(self.memory.get_full_context(user_id, session_id))
        task_search = asyncio.create_task(self.search_manager.search(message))
        
        # On ne bloque pas sur la sauvegarde du message utilisateur, on le fait en fond
        asyncio.create_task(self.memory.add_user_message(user_id, session_id, message))

        # 🛡️ RÉCUPÉRATION SÉCURISÉE (On ne déballe plus directement)
        try:
            # On attend les résultats avec un timeout global de 3s pour ne jamais figer
            res_history, res_search = await asyncio.wait_for(
                asyncio.gather(task_history, task_search, return_exceptions=True),
                timeout=3.0
            )
            
            # On vérifie l'historique : si c'est une erreur, on prend du vide
            if isinstance(res_history, Exception):
                print(f"⚠️ Erreur Mémoire ignorée: {res_history}")
                long_ctx, short_hist = "", []
            else:
                long_ctx, short_hist = res_history

            # On vérifie la recherche : si c'est une erreur, on prend du vide
            if isinstance(res_search, Exception):
                print(f"⚠️ Erreur Search ignorée: {res_search}")
                context_docs = "Documentation momentanément indisponible."
            else:
                context_docs = res_search

        except Exception as e:
            print(f"🚨 Erreur critique parallèle ou Timeout: {e}")
            long_ctx, short_hist, context_docs = "", [], ""

        t1 = time.time()
        print(f"⏱️ [1+2a] Préparation terminée en {t1 - t0:.2f}s")

        # Construction du prompt
        history_str = "\n".join([f"{msg['role'].upper()}: {msg['content']}" for msg in short_hist[-4:]])
        augmented_message = f"{long_ctx}\n[DOCS]: {context_docs}\n[QUESTION]: {message}"

        # 🤖 3. STREAMING DIRECT (Dès cet instant, l'UI reçoit du texte)
        full_response = ""
        stream = await self.oai_client.chat.completions.create(
            model=self.chat_model,
            messages=[{"role": "system", "content": self.instructions}, {"role": "user", "content": augmented_message}],
            stream=True,
            temperature=0.0
        )
        
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                text_chunk = chunk.choices[0].delta.content
                full_response += text_chunk
                yield text_chunk # 👈 Envoi immédiat au front-end

        t2 = time.time()
        print(f"⏱️ [2b] Fin du Streaming : {t2 - t1:.2f} secondes")

        # 4. Sauvegarde finale en arrière-plan
        asyncio.create_task(self.memory.add_agent_message(user_id, session_id, full_response))
        asyncio.create_task(self.memory.trigger_background_summary(user_id, session_id))


class BrainAgent:
    def __init__(self):
        self.AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
        self.AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
        self.AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini")
        self.AZURE_OPENAI_EMBED_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")
        
        self.AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
        self.AZURE_SEARCH_API_KEY = os.getenv("AZURE_SEARCH_API_KEY")
        self.AZURE_SEARCH_INDEX = os.getenv("AZURE_SEARCH_INDEX_NAME")
        self.embed_dimensions = int(os.getenv("AZURE_AI_EMBED_DIMENSIONS", 1536))

        print("🔌 Connexion réseau optimisée (IPv4 Force)...")
        
        custom_http_client = httpx.AsyncClient(
            transport=httpx.AsyncHTTPTransport(local_address="0.0.0.0")
        )

        self.async_client = AsyncAzureOpenAI(
            azure_endpoint=self.AZURE_OPENAI_ENDPOINT,
            api_key=self.AZURE_OPENAI_API_KEY,
            api_version="2024-02-15-preview",
            http_client=custom_http_client
        )

        self.search_index_manager = SearchIndexManager(
            endpoint=self.AZURE_SEARCH_ENDPOINT,
            credential=AzureKeyCredential(self.AZURE_SEARCH_API_KEY),
            index_name=self.AZURE_SEARCH_INDEX,
            dimensions=self.embed_dimensions,
            model=self.AZURE_OPENAI_EMBED_DEPLOYMENT,
            embeddings_client=self.async_client
        )

        self.memory = MemoryManager(
            oai_client=self.async_client,
            chat_model=self.AZURE_OPENAI_DEPLOYMENT,
            db_adapter=LocalJSONAdapter()
        )

    async def setup(self):
        await self.search_index_manager.ensure_index_created(vector_index_dimensions=self.embed_dimensions)

    def get_agent(self, lang: str, is_audio: bool):
        base_instruction = f"Tu es Subul, un tuteur Cloud expert. L'utilisateur te parle en '{lang}'. Tu DOIS lui répondre en '{lang}'. Utilise STRICTEMENT les [DOCUMENTS RETROUVÉS] fournis pour ta réponse."
        
        if is_audio:
            instructions = base_instruction + " MODE VOCAL : RÉPONDS EN UNE SEULE ET UNIQUE PHRASE. Pas de Markdown."
        else:
            instructions = base_instruction + """ MODE TEXTE : 
            RÈGLE ABSOLUE : UN SEUL PARAGRAPHE MAXIMUM.
            Sois direct et chirurgical. Zéro politesse, zéro introduction.
            Utilise le contexte fourni ci-dessous."""
            
        # 🎯 On renvoie directement le Proxy qui gère tout le flux proprement
        return MemoryAgentProxy(
            memory_manager=self.memory,
            search_manager=self.search_index_manager,
            oai_client=self.async_client,
            chat_model=self.AZURE_OPENAI_DEPLOYMENT,
            instructions=instructions
        )
        
import os
import sys
import asyncio
import json
import time 
import httpx 

from typing import Annotated
from pydantic import Field
from dotenv import load_dotenv

from memory_management import MemoryManager, LocalJSONAdapter

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_CURRENT_DIR)

if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

env_path = os.path.join(_ROOT_DIR, "00_Config", ".env.txt")
if os.path.exists(env_path):
    print(f"📂 Configuration chargée depuis : {env_path}")
    load_dotenv(dotenv_path=env_path)
else:
    print(f"❌ Erreur : Fichier config introuvable à {env_path}")

from search_index_manager import SearchIndexManager
from azure.core.credentials import AzureKeyCredential
from openai import AsyncAzureOpenAI

# ============================================================
# 🛡️ LE DESIGN PATTERN PROXY : Bypass Agent pour le Streaming
# ============================================================
class MemoryAgentProxy:
    def __init__(self, memory_manager: MemoryManager, search_manager: SearchIndexManager, oai_client: AsyncAzureOpenAI, chat_model: str, instructions: str):
        self.memory = memory_manager
        self.search_manager = search_manager
        self.oai_client = oai_client       
        self.chat_model = chat_model       
        self.instructions = instructions   

    async def run_stream(self, message: str, user_id: str, session_id: str):
        print("\n⏱️ --- DÉBUT DU CHRONO (ULTRA-RÉSILIENT) ---")
        t0 = time.time()

        # 🚀 Lancement des tâches SANS BLOQUER
        task_history = asyncio.create_task(self.memory.get_full_context(user_id, session_id))
        task_search = asyncio.create_task(self.search_manager.search(message))
        
        # On ne bloque pas sur la sauvegarde du message utilisateur, on le fait en fond
        asyncio.create_task(self.memory.add_user_message(user_id, session_id, message))

        # 🛡️ RÉCUPÉRATION SÉCURISÉE (On ne déballe plus directement)
        try:
            # On attend les résultats avec un timeout global de 3s pour ne jamais figer
            res_history, res_search = await asyncio.wait_for(
                asyncio.gather(task_history, task_search, return_exceptions=True),
                timeout=3.0
            )
            
            # On vérifie l'historique : si c'est une erreur, on prend du vide
            if isinstance(res_history, Exception):
                print(f"⚠️ Erreur Mémoire ignorée: {res_history}")
                long_ctx, short_hist = "", []
            else:
                long_ctx, short_hist = res_history

            # On vérifie la recherche : si c'est une erreur, on prend du vide
            if isinstance(res_search, Exception):
                print(f"⚠️ Erreur Search ignorée: {res_search}")
                context_docs = "Documentation momentanément indisponible."
            else:
                context_docs = res_search

        except Exception as e:
            print(f"🚨 Erreur critique parallèle ou Timeout: {e}")
            long_ctx, short_hist, context_docs = "", [], ""

        t1 = time.time()
        print(f"⏱️ [1+2a] Préparation terminée en {t1 - t0:.2f}s")

        # Construction du prompt
        history_str = "\n".join([f"{msg['role'].upper()}: {msg['content']}" for msg in short_hist[-4:]])
        augmented_message = f"{long_ctx}\n[DOCS]: {context_docs}\n[QUESTION]: {message}"

        # 🤖 3. STREAMING DIRECT (Dès cet instant, l'UI reçoit du texte)
        full_response = ""
        stream = await self.oai_client.chat.completions.create(
            model=self.chat_model,
            messages=[{"role": "system", "content": self.instructions}, {"role": "user", "content": augmented_message}],
            stream=True,
            temperature=0.0
        )
        
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                text_chunk = chunk.choices[0].delta.content
                full_response += text_chunk
                yield text_chunk # 👈 Envoi immédiat au front-end

        t2 = time.time()
        print(f"⏱️ [2b] Fin du Streaming : {t2 - t1:.2f} secondes")

        # 4. Sauvegarde finale en arrière-plan
        asyncio.create_task(self.memory.add_agent_message(user_id, session_id, full_response))
        asyncio.create_task(self.memory.trigger_background_summary(user_id, session_id))


class BrainAgent:
    def __init__(self):
        self.AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
        self.AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
        self.AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini")
        self.AZURE_OPENAI_EMBED_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")
        
        self.AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
        self.AZURE_SEARCH_API_KEY = os.getenv("AZURE_SEARCH_API_KEY")
        self.AZURE_SEARCH_INDEX = os.getenv("AZURE_SEARCH_INDEX_NAME")
        self.embed_dimensions = int(os.getenv("AZURE_AI_EMBED_DIMENSIONS", 1536))

        print("🔌 Connexion réseau optimisée (IPv4 Force)...")
        
        custom_http_client = httpx.AsyncClient(
            transport=httpx.AsyncHTTPTransport(local_address="0.0.0.0")
        )

        self.async_client = AsyncAzureOpenAI(
            azure_endpoint=self.AZURE_OPENAI_ENDPOINT,
            api_key=self.AZURE_OPENAI_API_KEY,
            api_version="2024-02-15-preview",
            http_client=custom_http_client
        )

        self.search_index_manager = SearchIndexManager(
            endpoint=self.AZURE_SEARCH_ENDPOINT,
            credential=AzureKeyCredential(self.AZURE_SEARCH_API_KEY),
            index_name=self.AZURE_SEARCH_INDEX,
            dimensions=self.embed_dimensions,
            model=self.AZURE_OPENAI_EMBED_DEPLOYMENT,
            embeddings_client=self.async_client
        )

        self.memory = MemoryManager(
            oai_client=self.async_client,
            chat_model=self.AZURE_OPENAI_DEPLOYMENT,
            db_adapter=LocalJSONAdapter()
        )

    async def setup(self):
        await self.search_index_manager.ensure_index_created(vector_index_dimensions=self.embed_dimensions)

    def get_agent(self, lang: str, is_audio: bool):
        base_instruction = f"Tu es Subul, un tuteur Cloud expert. L'utilisateur te parle en '{lang}'. Tu DOIS lui répondre en '{lang}'. Utilise STRICTEMENT les [DOCUMENTS RETROUVÉS] fournis pour ta réponse."
        
        if is_audio:
            instructions = base_instruction + " MODE VOCAL : RÉPONDS EN UNE SEULE ET UNIQUE PHRASE. Pas de Markdown."
        else:
            instructions = base_instruction + """ MODE TEXTE : 
            RÈGLE ABSOLUE : UN SEUL PARAGRAPHE MAXIMUM.
            Sois direct et chirurgical. Zéro politesse, zéro introduction.
            Utilise le contexte fourni ci-dessous."""
            
        # 🎯 On renvoie directement le Proxy qui gère tout le flux proprement
        return MemoryAgentProxy(
            memory_manager=self.memory,
            search_manager=self.search_index_manager,
            oai_client=self.async_client,
            chat_model=self.AZURE_OPENAI_DEPLOYMENT,
            instructions=instructions
        )