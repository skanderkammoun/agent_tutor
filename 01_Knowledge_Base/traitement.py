import os
import asyncio
import json
import re
from openai import AsyncAzureOpenAI
from dotenv import load_dotenv

# Chemins
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data")
RAW_DIR = os.path.join(DATA_DIR, "raw")
PROCESSED_DIR = os.path.join(DATA_DIR, "processed")

# Charger le .env depuis le bon chemin
ENV_PATH = os.path.expanduser(
    "~/cloudfiles/code/Users/Skander.Kammoun/Agent_Tuteur_Subul/00_Config/.env"
)
load_dotenv(ENV_PATH)

AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")

client = AsyncAzureOpenAI(
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_key=AZURE_OPENAI_API_KEY,
    api_version="2024-02-01",
)

STRUCTURE_PROMPT = """Tu es un expert en documentation technique cloud.
Tu reçois le contenu brut d'un fichier technique (transcript, notes, documentation, etc.).
Transforme ce contenu en un fichier Markdown structuré, propre et éducatif.
NE PAS INVENTER d'informations absentes du texte.
Écrire en FRANÇAIS.
Format : titre, résumé, points clés, explications détaillées, étapes pratiques, conseils, concepts mentionnés.
"""

async def file_to_markdown(text: str, filename: str, provider: str) -> str:
    user_message = f"Fichier : {filename}\nProvider : {provider}\n\n--- CONTENU ---\n\n{text}"
    response = await client.chat.completions.create(
        model=AZURE_OPENAI_DEPLOYMENT,
        messages=[
            {"role": "system", "content": STRUCTURE_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=0.1,
        max_tokens=4096,
    )
    return response.choices[0].message.content

async def process_provider(provider):
    raw_path = os.path.join(RAW_DIR, provider)
    processed_path = os.path.join(PROCESSED_DIR, provider)
    os.makedirs(processed_path, exist_ok=True)

    files = [f for f in os.listdir(raw_path) if f.endswith(".json") and os.path.isfile(os.path.join(raw_path, f))]
    for fname in files:
        fpath = os.path.join(raw_path, fname)
        with open(fpath, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                text = data.get("transcript", {}).get("text") or data.get("text") or json.dumps(data, ensure_ascii=False)
            except Exception:
                print(f"❌ Erreur lecture JSON : {fname}")
                continue
        print(f"⏳ Traitement {fname} ({provider}) ...")
        try:
            md = await file_to_markdown(text, fname, provider)
        except Exception as e:
            print(f"❌ Erreur LLM sur {fname}: {e}")
            continue
        safe_name = re.sub(r'[^\w\s-]', '', fname)[:60].strip().replace(' ', '_').lower()
        md_name = f"{os.path.splitext(safe_name)[0]}.md"
        md_path = os.path.join(processed_path, md_name)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"✅ {md_name} généré")
    print(f"📦 Tous les fichiers JSON traités pour {provider}")

async def main():
    for provider in ["azure", "aws", "gcp"]:
        await process_provider(provider)
    await client.close()

if __name__ == "__main__":
    asyncio.run(main())