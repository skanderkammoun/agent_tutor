import os
import sys
import asyncio
import json
import time 
import httpx 

from typing import Annotated
from pydantic import Field
from dotenv import load_dotenv

from memory_management import MemoryManager, CosmosDBAdapter

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_CURRENT_DIR)

if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

env_path = os.path.join(_ROOT_DIR, "00_Config", ".env.txt")
if os.path.exists(env_path):
    print(f" Configuration chargée depuis : {env_path}")
    load_dotenv(dotenv_path=env_path)
else:
    print(f" Erreur : Fichier config introuvable à {env_path}")

from search_index_manager import SearchIndexManager
from azure.core.credentials import AzureKeyCredential
from openai import AsyncAzureOpenAI


class MemoryAgentProxy:
    def __init__(self, memory_manager: MemoryManager, search_manager: SearchIndexManager, oai_client: AsyncAzureOpenAI, chat_model: str, instructions: str):
        self.memory = memory_manager
        self.search_manager = search_manager
        self.oai_client = oai_client       
        self.chat_model = chat_model       
        self.instructions = instructions   

    async def run_stream(self, message: str, user_id: str, session_id: str):
        print("\n --- DÉBUT DU CHRONO (ULTRA-RÉSILIENT) ---")
        t0 = time.time()

    
        task_history = asyncio.create_task(self.memory.get_full_context(user_id, session_id))
        task_search = asyncio.create_task(self.search_manager.search(message))
        

        asyncio.create_task(self.memory.add_user_message(user_id, session_id, message))

        try:
            
            res_history, res_search = await asyncio.wait_for(
                asyncio.gather(task_history, task_search, return_exceptions=True),
                timeout=3.0
            )
            
    
            if isinstance(res_history, Exception):
                print(f" Erreur Mémoire ignorée: {res_history}")
                long_ctx, short_hist = "", []
            else:
                long_ctx, short_hist = res_history

            if isinstance(res_search, Exception):
                print(f" Erreur Search ignorée: {res_search}")
                context_docs = "Documentation momentanément indisponible."
            else:
                context_docs = res_search

        except Exception as e:
            print(f" Erreur critique parallèle ou Timeout: {e}")
            long_ctx, short_hist, context_docs = "", [], ""

        t1 = time.time()
        print(f"⏱ [1+2a] Préparation terminée en {t1 - t0:.2f}s")

        
        history_str = "\n".join([f"{msg['role'].upper()}: {msg['content']}" for msg in short_hist[-4:]])
        augmented_message = f"{long_ctx}\n[DOCS]: {context_docs}\n[QUESTION]: {message}"

        
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
                yield text_chunk 

        t2 = time.time()
        print(f" [2b] Fin du Streaming : {t2 - t1:.2f} secondes")

       
        asyncio.create_task(self.memory.add_agent_message(user_id, session_id, full_response))


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

      
        self.COSMOS_ENDPOINT = os.getenv("AZURE_COSMOS_ENDPOINT")
        self.COSMOS_KEY = os.getenv("AZURE_COSMOS_KEY")
        self.COSMOS_DB_NAME = os.getenv("AZURE_COSMOS_DATABASE_NAME", "EduTech_AI_Production")
        self.COSMOS_CONTAINER_NAME = os.getenv("AZURE_COSMOS_CONTAINER_NAME", "AgentTutor")

        print(" Connexion réseau optimisée (IPv4 Force)...")
        
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

        
        cosmos_adapter = CosmosDBAdapter(
            endpoint=self.COSMOS_ENDPOINT,
            key=self.COSMOS_KEY,
            db_name=self.COSMOS_DB_NAME, 
            container_name=self.COSMOS_CONTAINER_NAME
        )

        self.memory = MemoryManager(
            oai_client=self.async_client,
            chat_model=self.AZURE_OPENAI_DEPLOYMENT,
            db_adapter=cosmos_adapter
        )

    async def setup(self):
        
        print("⚙️ Configuration de la base de données Cosmos DB...")
        await self.memory.db_adapter.setup()

        print("⚙️ Configuration de l'Index Azure Search...")
        await self.search_index_manager.ensure_index_created(vector_index_dimensions=self.embed_dimensions)

    def get_agent(self, lang: str, is_audio: bool):
        
        base_instruction = (
            f"Tu es Subul, un Tuteur Cloud expert, pédagogue et bienveillant.\n"
            f"L'utilisateur interagit avec toi en '{lang}', tu DOIS impérativement lui répondre en '{lang}'.\n\n"
            f"RÈGLE D'OR (ANTI-HALLUCINATION) : Base tes réponses STRICTEMENT sur les [DOCUMENTS RETROUVÉS] fournis dans le contexte. "
            f"Si la réponse à la question ne se trouve pas dans les documents, dis honnêtement que tu n'as pas l'information dans tes cours actuels, plutôt que d'inventer.\n"
        )
        
       
        if is_audio:
            instructions = base_instruction + (
                "\n\n[MODE VOCAL ACTIVÉ]\n"
                "- RÈGLE 1 : Sois extrêmement concis, chaleureux et naturel.\n"
                "- RÈGLE 2 : Réponds en 2 ou 3 phrases courtes MAXIMUM.\n"
                "- RÈGLE 3 : N'utilise STRICTEMENT AUCUN formatage Markdown (pas d'astérisques, de gras ou de tirets) car ton texte sera lu par une voix de synthèse."
            )
            
        
        else:
            instructions = base_instruction + (
               "\n[MODE TEXTE ACTIVÉ]\n"
                "Agis comme un professeur d'excellence, passionnant et inspirant.\n\n"
                "Ta réponse doit IMPÉRATIVEMENT tenir en UN SEUL PARAGRAPHE, mais il doit être magnifiquement structuré, fluide et très agréable à lire. Ne fais AUCUN saut de ligne.\n\n"
                "Rédige ta réponse comme une explication naturelle en respectant ce flux :\n"
                
                "1. L'EXPLICATION : Donne une définition claire, précise et digeste du concept.\n"
                "2. LA MÉTAPHORE : Enchaîne de manière fluide avec une analogie frappante de la vie quotidienne pour créer le déclic visuel.\n\n"
                "RÈGLES DE STYLE : Le texte ne doit absolument pas être lourd ou étouffant. Varie la longueur de tes phrases pour donner un rythme agréable (des phrases courtes pour percuter, des phrases un peu plus longues pour expliquer). Utilise le **gras** uniquement sur 2 ou 3 mots-clés stratégiques pour guider l'œil de l'étudiant à l'intérieur de ce paragraphe."
            )
            
        
        return MemoryAgentProxy(
            memory_manager=self.memory,
            search_manager=self.search_index_manager,
            oai_client=self.async_client,
            chat_model=self.AZURE_OPENAI_DEPLOYMENT,
            instructions=instructions
        )