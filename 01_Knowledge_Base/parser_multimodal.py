# """
# 01_parser_multimodal.py — Pipeline d'Ingestion (Étape 1 : Extraction & LLM Vision)
# Architecture : Découplée avec Normalisation Markdown
# Modèle utilisé : gpt-4o-mini (Optimisation FinOps)
# """

# import os
# import glob
# import re
# import base64
# from dotenv import load_dotenv
# from openai import AzureOpenAI

# # Unstructured pour l'OCR avancé
# try:
#     from unstructured.partition.pdf import partition_pdf
# except ImportError:
#     print("❌ Erreur : 'unstructured' n'est pas installé. Lancez : pip install \"unstructured[all-docs]\"")
#     exit(1)

# # --- 1. CONFIGURATION & CHEMINS ---
# SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# chemin_env = os.path.join(os.getcwd(), "00_Config", ".env.txt")
# if not os.path.exists(chemin_env):
#     print(f"❌ Erreur : Fichier .env.txt introuvable à {chemin_env}")
#     exit(1)

# load_dotenv(dotenv_path=chemin_env)
# print("🔌 Connexion à Azure OpenAI (Vision & Parsing)...")

# oai_client = AzureOpenAI(
#     azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
#     api_key=os.environ["AZURE_OPENAI_API_KEY"],
#     api_version="2024-02-15-preview"
# )

# # Modèle "mini" pour l'extraction (rapide et pas cher)
# CHAT_MODEL_MINI = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME")

# # --- ARBORESCENCE DES DONNÉES ---
# BASE_DIR = os.path.join(os.getcwd(), "01_Knowledge_Base", "data")
# RAW_DIR = os.path.join(BASE_DIR, "raw")
# PROCESSED_DIR = os.path.join(BASE_DIR, "processed")

# CLOUD_PROVIDERS = ["aws", "azure", "gcp"]

# for cloud in CLOUD_PROVIDERS:
#     os.makedirs(os.path.join(PROCESSED_DIR, cloud), exist_ok=True)


# # --- 2. FONCTIONS IA (GPT-4o-mini) ---

# def summarize_table(html_table: str) -> str:
#     """Transforme un tableau HTML brut en format Markdown clair."""
#     prompt = f"""Tu es un expert technique. Voici un tableau extrait d'un document.
# Convertis-le STRICTEMENT en format Markdown (utilise les '|' pour les colonnes). Garde toutes les données techniques.

# TABLEAU HTML :
# {html_table}
# """
#     try:
#         response = oai_client.chat.completions.create(
#             model=CHAT_MODEL_MINI,
#             messages=[{"role": "user", "content": prompt}],
#             max_tokens=800,
#             temperature=0.0
#         )
#         return response.choices[0].message.content.strip()
#     except Exception as e:
#         print(f"      ⚠️ Erreur LLM Tableau : {e}")
#         return "*(Tableau non converti)*"

# def describe_image(base64_image: str) -> str:
#     """Utilise la Vision pour décrire précisément un schéma d'architecture."""
#     prompt = """Tu es un Architecte Cloud. Décris ce schéma d'architecture en détail.
# Utilise des listes à puces Markdown pour lister les services présents et expliquer leur interaction."""
    
#     try:
#         response = oai_client.chat.completions.create(
#             model=CHAT_MODEL_MINI,
#             messages=[
#                 {
#                     "role": "user",
#                     "content": [
#                         {"type": "text", "text": prompt},
#                         {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
#                     ]
#                 }
#             ],
#             max_tokens=600,
#             temperature=0.2
#         )
#         return response.choices[0].message.content.strip()
#     except Exception as e:
#         print(f"      ⚠️ Erreur LLM Vision : {e}")
#         return "*(Image technique non décrite)*"


# # --- 3. MOTEUR D'EXTRACTION DU PDF ---

# def process_single_pdf_to_md(filepath: str, cloud_provider: str) -> str:
#     """Ouvre le PDF et construit un document Markdown propre."""
#     nom_fichier = os.path.basename(filepath)
#     print(f"\n📄 Parsing Multimodal : {nom_fichier}...")
    
#     chunks = partition_pdf(
#         filename=filepath,
#         infer_table_structure=True,
#         strategy="hi_res",
#         extract_image_block_types=["Image"],
#         extract_image_block_to_payload=True, 
#         chunking_strategy="by_title",
#         max_characters=4000,
#         combine_text_under_n_chars=1000,
#         languages=["fra", "eng"]
#     )
    
#     # Initialisation du document Markdown
#     markdown_output = f"# Document Source : {nom_fichier} ({cloud_provider.upper()})\n\n"

#     for i, chunk in enumerate(chunks):
#         # 1. Traitement des TABLEAUX
#         if "Table" in str(type(chunk)):
#             print(f"   📊 Tableau détecté -> Conversion Markdown ({CHAT_MODEL_MINI})...")
#             html_content = chunk.metadata.text_as_html if hasattr(chunk.metadata, 'text_as_html') else chunk.text
#             content = summarize_table(html_content)
#             markdown_output += f"### 📊 Données Tabulaires\n{content}\n\n"
            
#         # 2. Traitement des IMAGES / SCHÉMAS
#         elif "CompositeElement" in str(type(chunk)) and hasattr(chunk.metadata, 'orig_elements'):
#             has_image = False
#             for el in chunk.metadata.orig_elements:
#                 if "Image" in str(type(el)) and hasattr(el.metadata, 'image_base64'):
#                     print(f"   🖼️ Schéma détecté -> Envoi à Vision API ({CHAT_MODEL_MINI})...")
#                     content = describe_image(el.metadata.image_base64)
#                     # On le met dans un bloc de citation pour bien le distinguer du texte normal
#                     markdown_output += f"### 🖼️ Description du Schéma\n> {content.replace(chr(10), chr(10)+'> ')}\n\n"
#                     has_image = True
#                     break
            
#             # Fallback si c'est juste du texte aggloméré
#             if not has_image:
#                 markdown_output += f"{chunk.text}\n\n"
                
#         # 3. Traitement du TEXTE CLASSIQUE
#         else:
#             content = chunk.text
#             if content and content.strip():
#                 markdown_output += f"{content}\n\n"
        
#     return markdown_output


# # --- 4. LE SUPERVISEUR DE LOTS ---

# def run_parser_pipeline():
#     print(f"🚀 Lancement de l'usine d'extraction Multimodale (Étape 1)")
    
#     for cloud in CLOUD_PROVIDERS:
#         dossier_source = os.path.join(RAW_DIR, cloud)
#         dossier_destination = os.path.join(PROCESSED_DIR, cloud)
        
#         fichiers_pdf = glob.glob(os.path.join(dossier_source, "*.pdf"))
        
#         for filepath in fichiers_pdf:
#             nom_fichier = os.path.basename(filepath)
#             clean_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', nom_fichier)
#             fichier_md_sortie = os.path.join(dossier_destination, f"{clean_name}_parsed.md")
            
#             if os.path.exists(fichier_md_sortie):
#                 print(f"⏭️  Déjà extrait (Ignoré) : {nom_fichier}")
#                 continue
                
#             try:
#                 markdown_content = process_single_pdf_to_md(filepath, cloud)
                
#                 if markdown_content.strip():
#                     with open(fichier_md_sortie, "w", encoding="utf-8") as f:
#                         f.write(markdown_content)
#                     print(f"   💾 Sauvegarde réussie : {fichier_md_sortie}")
#                 else:
#                     print(f"   ⚠️ Le fichier {nom_fichier} n'a donné aucun contenu.")
                    
#             except Exception as e:
#                 print(f"   ❌ Erreur critique sur {nom_fichier} : {e}")

#     print("\n✅ ÉTAPE 1 TERMINÉE. Tous les PDF sont maintenant de beaux fichiers Markdown dans 'processed/'.")
#     print("➡️ Prochaine étape : Lancer '02_indexer_semantique.py'.")

# if __name__ == "__main__":
#     run_parser_pipeline()
"""
01_parser_multimodal.py — Pipeline d'Ingestion (Étape 1 : Extraction & LLM Vision)
Architecture : Découplée avec Normalisation Markdown + CHUNKING PHYSIQUE ANTI-CRASH
Modèle utilisé : gpt-4o-mini (Optimisation FinOps)
"""

import os
import glob
import re
import tempfile
import gc # Pour forcer le nettoyage de la mémoire vive (RAM)
from dotenv import load_dotenv
from openai import AzureOpenAI

# Unstructured pour l'OCR avancé
try:
    from unstructured.partition.pdf import partition_pdf
except ImportError:
    print("❌ Erreur : 'unstructured' n'est pas installé. Lancez : pip install \"unstructured[all-docs]\"")
    exit(1)

# PyPDF pour découper les gros fichiers avant de saturer la RAM
try:
    from pypdf import PdfReader, PdfWriter
except ImportError:
    print("❌ Erreur : 'pypdf' n'est pas installé. Lancez : pip install pypdf")
    exit(1)

# --- 1. CONFIGURATION & CHEMINS ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
chemin_env = os.path.join(os.getcwd(), "00_Config", ".env.txt")
if not os.path.exists(chemin_env):
    print(f"❌ Erreur : Fichier .env.txt introuvable à {chemin_env}")
    exit(1)

load_dotenv(dotenv_path=chemin_env)
print("🔌 Connexion à Azure OpenAI (Vision & Parsing)...")

oai_client = AzureOpenAI(
    azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
    api_version="2024-02-15-preview"
)

CHAT_MODEL_MINI = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME")

# --- ARBORESCENCE DES DONNÉES ---
BASE_DIR = os.path.join(os.getcwd(), "01_Knowledge_Base", "data")
RAW_DIR = os.path.join(BASE_DIR, "raw")
PROCESSED_DIR = os.path.join(BASE_DIR, "processed")

CLOUD_PROVIDERS = ["aws", "azure", "gcp"]

for cloud in CLOUD_PROVIDERS:
    os.makedirs(os.path.join(PROCESSED_DIR, cloud), exist_ok=True)


# --- 2. FONCTIONS IA (GPT-4o-mini) ---
# (Tes fonctions IA restent intactes, elles sont parfaites)

def summarize_table(html_table: str) -> str:
    prompt = f"""Tu es un expert technique. Voici un tableau extrait d'un document.
Convertis-le STRICTEMENT en format Markdown (utilise les '|' pour les colonnes). Garde toutes les données techniques.

TABLEAU HTML :
{html_table}
"""
    try:
        response = oai_client.chat.completions.create(
            model=CHAT_MODEL_MINI,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,
            temperature=0.0
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"      ⚠️ Erreur LLM Tableau : {e}")
        return "*(Tableau non converti)*"

def describe_image(base64_image: str) -> str:
    prompt = """Tu es un Architecte Cloud. Décris ce schéma d'architecture en détail.
Utilise des listes à puces Markdown pour lister les services présents et expliquer leur interaction."""
    
    try:
        response = oai_client.chat.completions.create(
            model=CHAT_MODEL_MINI,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]
                }
            ],
            max_tokens=600,
            temperature=0.2
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"      ⚠️ Erreur LLM Vision : {e}")
        return "*(Image technique non décrite)*"


# --- 3. MOTEUR D'EXTRACTION SUR UN PETIT CHUNK (Morceau de PDF) ---

def process_pdf_chunk(filepath: str) -> str:
    """Analyse un petit PDF (ex: 50 pages) et renvoie le Markdown."""
    chunks = partition_pdf(
        filename=filepath,
        infer_table_structure=True,
        strategy="hi_res",
        extract_image_block_types=["Image"],
        extract_image_block_to_payload=True, 
        chunking_strategy="by_title",
        max_characters=4000,
        combine_text_under_n_chars=1000,
        languages=["fra", "eng"]
    )
    
    markdown_output = ""
    for chunk in chunks:
        if "Table" in str(type(chunk)):
            html_content = chunk.metadata.text_as_html if hasattr(chunk.metadata, 'text_as_html') else chunk.text
            content = summarize_table(html_content)
            markdown_output += f"### 📊 Données Tabulaires\n{content}\n\n"
            
        elif "CompositeElement" in str(type(chunk)) and hasattr(chunk.metadata, 'orig_elements'):
            has_image = False
            for el in chunk.metadata.orig_elements:
                if "Image" in str(type(el)) and hasattr(el.metadata, 'image_base64'):
                    content = describe_image(el.metadata.image_base64)
                    markdown_output += f"### 🖼️ Description du Schéma\n> {content.replace(chr(10), chr(10)+'> ')}\n\n"
                    has_image = True
                    break
            if not has_image:
                markdown_output += f"{chunk.text}\n\n"
                
        else:
            content = chunk.text
            if content and content.strip():
                markdown_output += f"{content}\n\n"
        
    return markdown_output


# --- 4. LE DÉCOUPEUR DE GROS PDF (Le remède anti-crash) ---

def process_large_pdf(filepath: str, cloud_provider: str, output_md_path: str, pages_per_chunk: int = 50):
    """Découpe un gros PDF, l'analyse morceau par morceau, et l'ajoute au fichier Markdown."""
    nom_fichier = os.path.basename(filepath)
    print(f"\n📄 Analyse de {nom_fichier} ({cloud_provider.upper()})")
    
    reader = PdfReader(filepath)
    total_pages = len(reader.pages)
    print(f"📑 Total pages : {total_pages}. Découpage en lots de {pages_per_chunk} pages...")

    # Initialisation du fichier Markdown (On écrase s'il existe déjà)
    with open(output_md_path, "w", encoding="utf-8") as f:
        f.write(f"# Document Source : {nom_fichier} ({cloud_provider.upper()})\n\n")

    # Boucle de découpage
    for start_page in range(0, total_pages, pages_per_chunk):
        end_page = min(start_page + pages_per_chunk, total_pages)
        print(f"   ✂️ Traitement du lot : Pages {start_page + 1} à {end_page}...")

        writer = PdfWriter()
        for i in range(start_page, end_page):
            writer.add_page(reader.pages[i])

        # Création d'un fichier PDF temporaire pour ce lot
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_pdf:
            temp_path = temp_pdf.name
            writer.write(temp_path)

        try:
            # On extrait le texte/image de ce petit morceau de PDF
            markdown_chunk = process_pdf_chunk(temp_path)
            
            # On l'ajoute directement (append 'a') au fichier final sur le disque dur
            with open(output_md_path, "a", encoding="utf-8") as f:
                f.write(markdown_chunk)
                
        except Exception as e:
            print(f"   ❌ Erreur sur les pages {start_page + 1} à {end_page} : {e}")
        finally:
            # On supprime le fichier temporaire
            os.remove(temp_path)
            # 🧹 MAGIC TRICK : On force le vidage de la RAM pour éviter le crash !
            gc.collect() 


# --- 5. LE SUPERVISEUR ---

def run_parser_pipeline():
    print(f"🚀 Lancement de l'usine d'extraction Multimodale (Anti-Crash)")
    
    for cloud in CLOUD_PROVIDERS:
        dossier_source = os.path.join(RAW_DIR, cloud)
        dossier_destination = os.path.join(PROCESSED_DIR, cloud)
        
        fichiers_pdf = glob.glob(os.path.join(dossier_source, "*.pdf"))
        
        for filepath in fichiers_pdf:
            nom_fichier = os.path.basename(filepath)
            clean_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', nom_fichier)
            fichier_md_sortie = os.path.join(dossier_destination, f"{clean_name}_parsed.md")
            
            if os.path.exists(fichier_md_sortie):
                print(f"⏭️  Déjà extrait (Ignoré) : {nom_fichier}")
                continue
                
            try:
                # Appel de notre nouvelle fonction robuste
                process_large_pdf(filepath, cloud, fichier_md_sortie, pages_per_chunk=50)
                print(f"   💾 Traitement 100% terminé : {fichier_md_sortie}")
                    
            except Exception as e:
                print(f"   ❌ Erreur critique sur {nom_fichier} : {e}")

    print("\n✅ ÉTAPE 1 TERMINÉE. Tous les PDF sont maintenant de beaux fichiers Markdown.")
    print("➡️ Prochaine étape : Lancer '02_indexer_semantique.py'.")

if __name__ == "__main__":
    run_parser_pipeline()