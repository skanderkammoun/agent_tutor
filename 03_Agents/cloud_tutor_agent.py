"""
cloud_tutor_agent.py : Agent TUTEUR CLOUD (Streaming & Multilingual V2)
"""

import os
import sys
import asyncio
from dotenv import load_dotenv
from ddgs import DDGS

# ⚡ Imports Asynchrones
from openai import AsyncAzureOpenAI
from azure.core.credentials import AzureKeyCredential
from azure.search.documents.aio import SearchClient 
from azure.search.documents.models import VectorizedQuery, QueryType

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_BASE_DIR)

if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

load_dotenv(os.path.join(_ROOT_DIR, "00_Config", ".env.txt"))

oai_client = AsyncAzureOpenAI(
    azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
    api_version=os.environ["AZURE_OPENAI_API_VERSION"],
)

EMBED_MODEL = os.environ["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"]
CHAT_MODEL  = os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"]

search_client = SearchClient(
    endpoint=os.environ["AZURE_SEARCH_ENDPOINT"],
    index_name=os.environ["AZURE_SEARCH_INDEX_NAME"],
    credential=AzureKeyCredential(os.environ["AZURE_SEARCH_API_KEY"]),
)

# ── PROMPT AMÉLIORÉ (Concision, RAG Strict & Multilingue) ──────────────────────
PROMPT_INSTRUCTEUR = """Tu es CloudTutor, expert pédagogique en cloud computing (AWS, Azure).

🌍 RÈGLE DE LANGUE (CRITIQUE) :
Réponds TOUJOURS dans la même langue que l'utilisateur. 
- S'il te parle en Français, réponds en Français.
- S'il te parle en Anglais, réponds en Anglais.

⚠️ RÈGLES ABSOLUES ANTI-HALLUCINATION :
1. Base-toi EXCLUSIVEMENT sur les documents RAG et les résultats WEB fournis dans le contexte.
2. Si l'info est absente, réponds : "Désolé, je n'ai pas cette information."
3. Ne jamais inventer de commandes techniques ou de prix.

🎙️ RÈGLES DE CONVERSATION VOCALE (TRÈS IMPORTANT) :
1. SOIS HYPER CONCIS : Tes réponses sont lues à l'oral. Fais un résumé de 2 à 3 phrases courtes MAXIMUM.
2. INTERDIT AUX LONGUES LISTES : Évite au maximum les longues listes à puces. Résume l'idée générale.
3. LE PING-PONG : Termine TOUJOURS ton intervention par une question courte pour relancer l'apprenant (ex: "Est-ce clair pour toi ?", "Veux-tu un exemple concret ?", "As-tu déjà utilisé ça ?").

🎯 STYLE PÉDAGOGIQUE :
- Adapte ton explication au niveau de l'apprenant.
- Cite la source [Nom du fichier] à la fin de ta réponse.
"""

PROMPT_ROLEPLAY = """Tu es CloudTutor en mode SIMULATION D'INCIDENT.
Maintiens une pression professionnelle, valide les actions et guide vers la résolution.
RÈGLE VOCALE : Parle comme un vrai collègue au téléphone. Fais des phrases très courtes (1 ou 2 phrases) et pose une question d'action rapide (ex: "Que fais-tu maintenant ?").
Réponds dans la langue de l'utilisateur.
"""

# ── Outils (Identiques) ────────────────────────────────────────────────────────
async def rag_search(query: str, cloud_filter: str | None, top_k: int = 3) -> list[dict]:
    try:
        embed_resp = await oai_client.embeddings.create(input=query, model=EMBED_MODEL)
        vec = embed_resp.data[0].embedding
        vq  = VectorizedQuery(vector=vec, k=top_k*2, fields="vecteur")
        filtre = f"cloud_provider eq '{cloud_filter.upper()}'" if cloud_filter else None

        results = await search_client.search(
            search_text=query,
            vector_queries=[vq],
            filter=filtre,
            select=["id", "cloud_provider", "source_file", "texte"],
            query_type=QueryType.SEMANTIC,
            semantic_configuration_name="my-semantic-config",
            top=top_k,
        )
        
        formatted_results = []
        async for r in results: 
            formatted_results.append({
                "cloud": r.get("cloud_provider"), 
                "source": r.get("source_file"), 
                "texte": r.get("texte")
            })
        return formatted_results
    except Exception as e:
        print(f"⚠️ [RAG] Erreur : {e}")
        return []

async def live_web_search(query: str, top: int = 3) -> str:
    try:
        results = await asyncio.to_thread(DDGS().text, query, max_results=top)
        if not results: return "Aucun résultat web."
        snippets = [f"**[{r.get('title')}]({r.get('href')})**\n{r.get('body')}" for r in results]
        return "\n\n".join(snippets)
    except Exception as e: return f"⚠️ Erreur Web : {e}"

def format_context(chunks: list[dict]) -> tuple[str, list[dict]]:
    if not chunks: return "Aucun document pertinent.", []
    ctx_blocks = [f"[Source {i} — {c['cloud']} | {c['source']}]\n{c['texte']}" for i, c in enumerate(chunks, 1)]
    return "\n\n---\n\n".join(ctx_blocks), []

def detect_cloud(text: str) -> str | None:
    t = text.lower()
    if any(k in t for k in ["azure", "microsoft"]): return "AZURE"
    if any(k in t for k in ["aws", "amazon"]): return "AWS"
    return None

def cross_analogy(cloud_target: str, user_background: str | None) -> str:
    if not user_background or not cloud_target or user_background == cloud_target: return ""
    analogies = {
        ("AZURE", "AWS") : "💡 Analogie : Azure Blob Storage ≈ AWS S3.",
        ("AWS", "AZURE"): "💡 Analogie : AWS S3 ≈ Azure Blob Storage.",
    }
    return analogies.get((cloud_target, user_background), "")

# ══════════════════════════════════════════════════════════════════════════════
class CloudTutorAgent:
    def __init__(self, memory, user_background: str | None = None):
        self.user_background = user_background
        self.memory = memory 

    # 🌊 VERSION STREAMING (Pour une interface fluide)
    async def repondre_stream(
        self,
        session_id: str,
        user_message: str,
        mode: str = "instructeur",
        cloud_target: str | None = None,
        volatile: bool = False,
        scenario: str | None = None,
    ):
        if not cloud_target: cloud_target = detect_cloud(user_message)
        
        # 1. RAG & Contexte
        chunks = await rag_search(user_message, cloud_filter=cloud_target, top_k=4)
        ctx_text, images_llm = format_context(chunks)
        ctx_live = await live_web_search(user_message) if volatile else ""
        hint_analogy = cross_analogy(cloud_target, self.user_background)
        ctx_long = await self.memory.get_memory_context_for_prompt(session_id)

        messages = self._build_messages(
            session_id, user_message, mode, ctx_text, images_llm, ctx_live, hint_analogy, scenario, ctx_long
        )

        # 2. Appel OpenAI avec STREAMING
        full_response = ""
        try:
            response = await oai_client.chat.completions.create(
                model=CHAT_MODEL,
                messages=messages,
                max_tokens=1500,
                temperature=0.3,
                stream=True # 👈 On active le stream
            )

            async for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    full_response += content
                    yield content # On envoie chaque mot au fur et à mesure

        except Exception as e:
            yield f"⚠️ Erreur Streaming : {e}"

        # 3. Sauvegarde en mémoire à la fin du flux
        self.memory.add_user_message(session_id, user_message)
        self.memory.add_agent_message(session_id, full_response)

    # Version Standard (gardée pour compatibilité)
    async def repondre(self, session_id, user_message, **kwargs) -> str:
        full_text = ""
        async for chunk in self.repondre_stream(session_id, user_message, **kwargs):
            full_text += chunk
        return full_text

    def _build_messages(self, session_id, user_message, mode, ctx_text, images_llm, ctx_live, hint_analogy, scenario, ctx_long):
        msgs = []
        sys_prompt = PROMPT_ROLEPLAY if mode == "roleplay" else PROMPT_INSTRUCTEUR
        msgs.append({"role": "system", "content": sys_prompt})
        if scenario: msgs.append({"role": "system", "content": f"🎭 SCÉNARIO :\n{scenario}"})
        if ctx_long: msgs.append({"role": "system", "content": ctx_long})
        
        rag_block = f"📄 RÉFÉRENCES :\n{ctx_text}"
        if ctx_live: rag_block += f"\n🌐 WEB :\n{ctx_live}"
        if hint_analogy: rag_block += f"\n{hint_analogy}"
        msgs.append({"role": "system", "content": rag_block})

        msgs.extend(self.memory.get_short_history(session_id))
        msgs.append({"role": "user", "content": user_message})
        return msgs