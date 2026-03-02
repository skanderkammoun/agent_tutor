import os
import sys
import asyncio
import json
from typing import Annotated
from pydantic import Field
from dotenv import load_dotenv

# 🛠️ 1. TECH LEAD FIX : Gestion des chemins pour Azure
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_CURRENT_DIR)

if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

# 🛠️ 2. CHARGEMENT PRÉCIS DU .ENV.TXT
env_path = os.path.join(_ROOT_DIR, "00_Config", ".env.txt")
if os.path.exists(env_path):
    print(f"📂 Configuration chargée depuis : {env_path}")
    load_dotenv(dotenv_path=env_path)
else:
    print(f"❌ Erreur : Fichier config introuvable à {env_path}")

# --- Imports après chargement des variables d'environnement ---
from search_index_manager import SearchIndexManager
from azure.core.credentials import AzureKeyCredential
from openai import AsyncAzureOpenAI
from agent_framework.azure import AzureOpenAIChatClient
from agent_framework import tool

# 3. RÉCUPÉRATION DES VARIABLES
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o-mini")
AZURE_OPENAI_EMBED_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")

AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_API_KEY = os.getenv("AZURE_SEARCH_API_KEY")
AZURE_SEARCH_INDEX = os.getenv("AZURE_SEARCH_INDEX_NAME")

embed_dimensions = int(os.getenv("AZURE_AI_EMBED_DIMENSIONS", 1536))

# 4. INITIALISATION DES CLIENTS
print("🔌 Connexion à Azure OpenAI et Azure AI Search...")

embeddings_client = AsyncAzureOpenAI(
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_key=AZURE_OPENAI_API_KEY,
    api_version="2024-02-15-preview"
)

search_index_manager = SearchIndexManager(
    endpoint=AZURE_SEARCH_ENDPOINT,
    credential=AzureKeyCredential(AZURE_SEARCH_API_KEY),
    index_name=AZURE_SEARCH_INDEX,
    dimensions=embed_dimensions,
    model=AZURE_OPENAI_EMBED_DEPLOYMENT,
    embeddings_client=embeddings_client
)

# 5. DÉFINITION DU TOOL (RAG) avec la bonne syntaxe sécurisée
@tool(approval_mode="never_require")
async def search_cloud_kb(
    query: Annotated[str, Field(description="Recherche des informations techniques sur le Cloud (AWS, Azure, GCP) dans la base de connaissances interne.")]
) -> str:
    """Appelé par l'agent pour consulter la documentation."""
    print(f"\n[⚙️ TOOL CALL] Recherche RAG : '{query}'")
    context = await search_index_manager.search(query)
    
    if context:
        print("[⚙️ TOOL CALL] Contexte récupéré avec succès.")
        return context
    return "Aucune information trouvée dans la base de connaissances."

# 6. CONFIGURATION DE L'AGENT via as_agent()
print("🔌 Initialisation du Client Azure OpenAI...")
client = AzureOpenAIChatClient(
    endpoint=AZURE_OPENAI_ENDPOINT,
    api_key=AZURE_OPENAI_API_KEY,
    deployment_name=AZURE_OPENAI_DEPLOYMENT,
)

print("🤖 Création de l'Agent CloudMaster...")
agent = client.as_agent(
    name="CloudMaster",
    instructions="Tu es Subul, un tuteur Cloud expert. Utilise TOUJOURS l'outil 'search_cloud_kb' pour répondre aux questions techniques. Réponds en français de manière concise.",
    tools=[search_cloud_kb]
)

# 7. BOUCLE DE TEST TERMINAL
async def main():
    try:
        # Vérification de l'index
        await search_index_manager.ensure_index_created(vector_index_dimensions=embed_dimensions)
        
        print("\n✅ CloudMaster est en ligne !")
        print("-" * 50)

        while True:
            user_input = input("\n🗣️ Vous : ")
            if user_input.lower() in ['quit', 'exit', 'q']:
                break
                
            print("🤖 Subul réfléchit...")
            result = await agent.run(user_input)
            
            print(f"\n✅ Subul : {result.text}")
            print("-" * 50)

    except Exception as e:
        print(f"\n❌ Erreur fatale : {e}")
    finally:
        print("\n🛑 Fermeture des sessions...")
        await search_index_manager.close()
        await embeddings_client.close()

if __name__ == "__main__":
    asyncio.run(main())