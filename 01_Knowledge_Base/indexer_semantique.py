# """
# 02_indexer_semantique.py — Pipeline d'Indexation (Étape 2 : Vectorisation & Semantic Ranker)
# Architecture : Chunking Sémantique, gestion robuste des encodages et reprise sur erreur.
# """

# import os
# import glob
# import json
# import time
# import re
# import tiktoken
# from dotenv import load_dotenv
# from openai import AzureOpenAI
# from azure.core.credentials import AzureKeyCredential
# from azure.search.documents import SearchClient
# from azure.search.documents.indexes import SearchIndexClient
# from azure.search.documents.indexes.models import (
#     SearchIndex, SimpleField, SearchField, SearchFieldDataType, 
#     VectorSearch, HnswAlgorithmConfiguration, VectorSearchProfile,
#     SemanticSearch, SemanticConfiguration, SemanticPrioritizedFields, SemanticField
# )

# # --- 1. CONFIGURATION ---
# SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# chemin_env = os.path.join(os.getcwd(), "00_Config", ".env.txt")
# load_dotenv(dotenv_path=chemin_env)

# print("🔌 Connexion à Azure OpenAI et Azure AI Search...")

# oai_client = AzureOpenAI(
#     azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
#     api_key=os.environ["AZURE_OPENAI_API_KEY"],
#     api_version="2024-02-15-preview"
# )
# search_endpoint = os.environ["AZURE_SEARCH_ENDPOINT"]
# search_key = AzureKeyCredential(os.environ["AZURE_SEARCH_API_KEY"])
# index_name = os.environ["AZURE_SEARCH_INDEX_NAME"]
# embedding_model = os.environ["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"]

# enc = tiktoken.get_encoding("cl100k_base")

# # --- DOSSIERS ---
# BASE_DIR = os.path.join(os.getcwd(), "01_Knowledge_Base", "data")
# PROCESSED_DIR = os.path.join(BASE_DIR, "processed")
# VECTOR_STORE_DIR = os.path.join(BASE_DIR, "vector_store")

# MAX_TOKENS = 800
# BATCH_SIZE = 100


# # --- 2. CRÉATION DE L'INDEX AVEC SEMANTIC RANKER ---
# def creer_index_semantique():
#     print(f"🏗️ Vérification de l'index avancé '{index_name}' avec Semantic Ranker...")
#     index_client = SearchIndexClient(endpoint=search_endpoint, credential=search_key)
    
#     fields = [
#         SimpleField(name="id", type=SearchFieldDataType.String, key=True),
#         SearchField(name="cloud_provider", type=SearchFieldDataType.String, filterable=True),
#         SearchField(name="source_file", type=SearchFieldDataType.String, filterable=True),
#         SearchField(name="texte", type=SearchFieldDataType.String, searchable=True),
#         SearchField(
#             name="vecteur", 
#             type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
#             searchable=True, 
#             vector_search_dimensions=1536,
#             vector_search_profile_name="my-vector-profile"
#         )
#     ]
    
#     vector_search = VectorSearch(
#         algorithms=[HnswAlgorithmConfiguration(name="my-hnsw-algo")],
#         profiles=[VectorSearchProfile(name="my-vector-profile", algorithm_configuration_name="my-hnsw-algo")]
#     )
    
#     semantic_config = SemanticConfiguration(
#         name="my-semantic-config",
#         prioritized_fields=SemanticPrioritizedFields(
#             title_field=SemanticField(field_name="source_file"),
#             content_fields=[SemanticField(field_name="texte")]
#         )
#     )
#     semantic_search = SemanticSearch(configurations=[semantic_config])
    
#     index = SearchIndex(
#         name=index_name, 
#         fields=fields, 
#         vector_search=vector_search,
#         semantic_search=semantic_search
#     )
    
#     try:
#         index_client.create_or_update_index(index)
#         print("✅ Index Sémantique prêt !")
#     except Exception as e:
#         print(f"⚠️ Erreur Index : {e}")


# # --- 3. LE CHUNKING SÉMANTIQUE ---
# def decouper_texte_semantique(markdown_text, max_tokens=MAX_TOKENS):
#     blocs_logiques = re.split(r'\n\n+', markdown_text)
    
#     chunks = []
#     chunk_actuel = ""
#     tokens_actuels = 0
    
#     for bloc in blocs_logiques:
#         bloc = bloc.strip()
#         if not bloc:
#             continue
            
#         bloc_tokens = len(enc.encode(bloc))
        
#         if bloc_tokens > max_tokens:
#             if chunk_actuel:
#                 chunks.append(chunk_actuel.strip())
#                 chunk_actuel = ""
#                 tokens_actuels = 0
#             chunks.append(bloc[:max_tokens*3])
#             continue

#         if tokens_actuels + bloc_tokens > max_tokens:
#             chunks.append(chunk_actuel.strip())
#             chunk_actuel = bloc + "\n\n"
#             tokens_actuels = bloc_tokens
#         else:
#             chunk_actuel += bloc + "\n\n"
#             tokens_actuels += bloc_tokens
            
#     if chunk_actuel:
#         chunks.append(chunk_actuel.strip())
        
#     return chunks


# # --- 4. EMBEDDINGS & BATCHING ---
# def get_embedding_avec_retry(texte, model, retries=3):
#     for tentative in range(retries):
#         try:
#             response = oai_client.embeddings.create(input=texte, model=model)
#             return response.data[0].embedding
#         except Exception as e:
#             attente = 2 ** tentative
#             time.sleep(attente)
#     raise RuntimeError(f"❌ Embedding impossible pour le texte : {texte[:50]}...")

# def upload_en_batches(search_client, documents, batch_size=BATCH_SIZE):
#     for i in range(0, len(documents), batch_size):
#         batch = documents[i:i + batch_size]
#         search_client.upload_documents(documents=batch)
#         print(f"   ☁️ Batch envoyé ({len(batch)} documents)")


# # --- 5. LE PIPELINE D'INDEXATION ---
# def executer_indexation():
#     creer_index_semantique()
#     search_client = SearchClient(endpoint=search_endpoint, index_name=index_name, credential=search_key)
    
#     print(f"\n🔄 Recherche des fichiers .md structurés dans : {PROCESSED_DIR}")
#     fichiers_trouves = glob.glob(f"{PROCESSED_DIR}/**/*.md", recursive=True)
    
#     if not fichiers_trouves:
#         print("⚠️ Aucun fichier markdown (.md) trouvé. Lancez l'Étape 1 d'abord !")
#         return

#     for filepath in fichiers_trouves:
#         cloud_provider = os.path.basename(os.path.dirname(filepath)).upper()
#         nom_fichier = os.path.basename(filepath)
        
#         # Dossier de sauvegarde local (Vector Store) : C'EST ICI QUE LA MAGIE ANTI-RÉPÉTITION OPÈRE !
#         dossier_destination_local = os.path.join(VECTOR_STORE_DIR, cloud_provider.lower())
#         os.makedirs(dossier_destination_local, exist_ok=True)
#         fichier_backup = os.path.join(dossier_destination_local, f"{nom_fichier}_embeddings.json")
        
#         if os.path.exists(fichier_backup):
#             print(f"⏭️ Déjà indexé (Ignoré) : {nom_fichier}")
#             continue

#         print(f"\n📄 Indexation Sémantique : {nom_fichier} ({cloud_provider})")
        
#         # --- LECTURE ROBUSTE MULTI-ENCODAGE (Le correctif du crash !) ---
#         texte_complet = None
#         try:
#             with open(filepath, "r", encoding="utf-8") as f:
#                 texte_complet = f.read()
#         except UnicodeDecodeError:
#             try:
#                 # Fallback UTF-16 si le BOM Windows est présent
#                 with open(filepath, "r", encoding="utf-16") as f:
#                     texte_complet = f.read()
#             except Exception:
#                 # Dernier recours
#                 with open(filepath, "r", encoding="latin-1", errors="ignore") as f:
#                     texte_complet = f.read()
                    
#         if not texte_complet or not texte_complet.strip():
#             print(f"   ⚠️ Fichier vide ou illisible, ignoré : {nom_fichier}")
#             continue
#         # ------------------------------------------------------------------

#         # Application du Chunking Sémantique
#         chunks = decouper_texte_semantique(texte_complet)
#         print(f"   ✂️ {len(chunks)} Chunks Sémantiques générés.")

#         documents_azure_search = []
#         local_embeddings_backup = []
#         clean_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', nom_fichier)

#         for i, chunk in enumerate(chunks):
#             try:
#                 vecteur = get_embedding_avec_retry(chunk, embedding_model)
#             except RuntimeError as e:
#                 print(e)
#                 continue

#             doc_id = f"{cloud_provider}_{clean_name}_chunk_{i}"
            
#             documents_azure_search.append({
#                 "id": doc_id,
#                 "cloud_provider": cloud_provider,
#                 "source_file": nom_fichier,
#                 "texte": chunk,
#                 "vecteur": vecteur
#             })
#             local_embeddings_backup.append({
#                 "id": doc_id,
#                 "chunk_index": i,
#                 "texte": chunk,
#                 "vecteur": vecteur
#             })

#         if documents_azure_search:
#             # On sauvegarde localement pour que le prochain lancement l'ignore !
#             with open(fichier_backup, "w", encoding="utf-8") as f:
#                 json.dump(local_embeddings_backup, f, ensure_ascii=False, indent=2)

#             upload_en_batches(search_client, documents_azure_search)
#             print(f"   ✅ Succès pour {nom_fichier} ({len(documents_azure_search)} chunks uploadés)")

#     print("\n🎉 ÉTAPE 2 TERMINÉE : Base de données Vectorielle et Sémantique prête !")

# if __name__ == "__main__":
#     executer_indexation()

"""
02_indexer_semantique.py — Pipeline d'Indexation (Étape 2 : Vectorisation & Semantic Ranker)
Architecture : Chunking Sémantique, gestion robuste des encodages et reprise sur erreur (Safe-Upload).
"""

import os
import glob
import json
import time
import re
import tiktoken
from dotenv import load_dotenv
from openai import AzureOpenAI
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex, SimpleField, SearchField, SearchFieldDataType, 
    VectorSearch, HnswAlgorithmConfiguration, VectorSearchProfile,
    SemanticSearch, SemanticConfiguration, SemanticPrioritizedFields, SemanticField
)

# --- 1. CONFIGURATION ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
chemin_env = os.path.join(os.getcwd(), "00_Config", ".env.txt")
load_dotenv(dotenv_path=chemin_env)

print("🔌 Connexion à Azure OpenAI et Azure AI Search...")

oai_client = AzureOpenAI(
    azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
    api_version="2024-02-15-preview"
)
search_endpoint = os.environ["AZURE_SEARCH_ENDPOINT"]
search_key = AzureKeyCredential(os.environ["AZURE_SEARCH_API_KEY"])
index_name = os.environ["AZURE_SEARCH_INDEX_NAME"]
embedding_model = os.environ["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"]

enc = tiktoken.get_encoding("cl100k_base")

# --- DOSSIERS ---
BASE_DIR = os.path.join(os.getcwd(), "01_Knowledge_Base", "data")
PROCESSED_DIR = os.path.join(BASE_DIR, "processed")
VECTOR_STORE_DIR = os.path.join(BASE_DIR, "vector_store")

MAX_TOKENS = 800
BATCH_SIZE = 100


# --- 2. CRÉATION DE L'INDEX AVEC SEMANTIC RANKER ---
def creer_index_semantique():
    print(f"🏗️ Vérification de l'index avancé '{index_name}' avec Semantic Ranker...")
    index_client = SearchIndexClient(endpoint=search_endpoint, credential=search_key)
    
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True),
        SearchField(name="cloud_provider", type=SearchFieldDataType.String, filterable=True),
        SearchField(name="source_file", type=SearchFieldDataType.String, filterable=True),
        SearchField(name="texte", type=SearchFieldDataType.String, searchable=True),
        SearchField(
            name="vecteur", 
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True, 
            vector_search_dimensions=1536,
            vector_search_profile_name="my-vector-profile"
        )
    ]
    
    vector_search = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name="my-hnsw-algo")],
        profiles=[VectorSearchProfile(name="my-vector-profile", algorithm_configuration_name="my-hnsw-algo")]
    )
    
    semantic_config = SemanticConfiguration(
        name="my-semantic-config",
        prioritized_fields=SemanticPrioritizedFields(
            title_field=SemanticField(field_name="source_file"),
            content_fields=[SemanticField(field_name="texte")]
        )
    )
    semantic_search = SemanticSearch(configurations=[semantic_config])
    
    index = SearchIndex(
        name=index_name, 
        fields=fields, 
        vector_search=vector_search,
        semantic_search=semantic_search
    )
    
    try:
        index_client.create_or_update_index(index)
        print("✅ Index Sémantique prêt !")
    except Exception as e:
        print(f"⚠️ Erreur Index : {e}")


# --- 3. LE CHUNKING SÉMANTIQUE ---
def decouper_texte_semantique(markdown_text, max_tokens=MAX_TOKENS):
    blocs_logiques = re.split(r'\n\n+', markdown_text)
    
    chunks = []
    chunk_actuel = ""
    tokens_actuels = 0
    
    for bloc in blocs_logiques:
        bloc = bloc.strip()
        if not bloc:
            continue
            
        bloc_tokens = len(enc.encode(bloc))
        
        if bloc_tokens > max_tokens:
            if chunk_actuel:
                chunks.append(chunk_actuel.strip())
                chunk_actuel = ""
                tokens_actuels = 0
            chunks.append(bloc[:max_tokens*3])
            continue

        if tokens_actuels + bloc_tokens > max_tokens:
            chunks.append(chunk_actuel.strip())
            chunk_actuel = bloc + "\n\n"
            tokens_actuels = bloc_tokens
        else:
            chunk_actuel += bloc + "\n\n"
            tokens_actuels += bloc_tokens
            
    if chunk_actuel:
        chunks.append(chunk_actuel.strip())
        
    return chunks


# --- 4. EMBEDDINGS & BATCHING ---
def get_embedding_avec_retry(texte, model, retries=3):
    for tentative in range(retries):
        try:
            response = oai_client.embeddings.create(input=texte, model=model)
            return response.data[0].embedding
        except Exception as e:
            attente = 2 ** tentative
            time.sleep(attente)
    raise RuntimeError(f"❌ Embedding impossible pour le texte : {texte[:50]}...")

def upload_en_batches(search_client, documents, batch_size=BATCH_SIZE):
    for i in range(0, len(documents), batch_size):
        batch = documents[i:i + batch_size]
        search_client.upload_documents(documents=batch)
        print(f"   ☁️ Batch envoyé ({len(batch)} documents)")


# --- 5. LE PIPELINE D'INDEXATION ---
def executer_indexation():
    creer_index_semantique()
    search_client = SearchClient(endpoint=search_endpoint, index_name=index_name, credential=search_key)
    
    print(f"\n🔄 Recherche des fichiers .md structurés dans : {PROCESSED_DIR}")
    fichiers_trouves = glob.glob(f"{PROCESSED_DIR}/**/*.md", recursive=True)
    
    if not fichiers_trouves:
        print("⚠️ Aucun fichier markdown (.md) trouvé. Lancez l'Étape 1 d'abord !")
        return

    for filepath in fichiers_trouves:
        cloud_provider = os.path.basename(os.path.dirname(filepath)).upper()
        nom_fichier = os.path.basename(filepath)
        
        # Dossier de sauvegarde local (Vector Store) : C'EST ICI QUE LA MAGIE ANTI-RÉPÉTITION OPÈRE !
        dossier_destination_local = os.path.join(VECTOR_STORE_DIR, cloud_provider.lower())
        os.makedirs(dossier_destination_local, exist_ok=True)
        fichier_backup = os.path.join(dossier_destination_local, f"{nom_fichier}_embeddings.json")
        
        if os.path.exists(fichier_backup):
            print(f"⏭️ Déjà indexé (Ignoré) : {nom_fichier}")
            continue

        print(f"\n📄 Indexation Sémantique : {nom_fichier} ({cloud_provider})")
        
        # --- LECTURE ROBUSTE MULTI-ENCODAGE ---
        texte_complet = None
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                texte_complet = f.read()
        except UnicodeDecodeError:
            try:
                # Fallback UTF-16 si le BOM Windows est présent
                with open(filepath, "r", encoding="utf-16") as f:
                    texte_complet = f.read()
            except Exception:
                # Dernier recours
                with open(filepath, "r", encoding="latin-1", errors="ignore") as f:
                    texte_complet = f.read()
                    
        if not texte_complet or not texte_complet.strip():
            print(f"   ⚠️ Fichier vide ou illisible, ignoré : {nom_fichier}")
            continue
        # ------------------------------------------------------------------

        # Application du Chunking Sémantique
        chunks = decouper_texte_semantique(texte_complet)
        print(f"   ✂️ {len(chunks)} Chunks Sémantiques générés.")

        documents_azure_search = []
        local_embeddings_backup = []
        clean_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', nom_fichier)

        for i, chunk in enumerate(chunks):
            try:
                vecteur = get_embedding_avec_retry(chunk, embedding_model)
            except RuntimeError as e:
                print(e)
                continue

            doc_id = f"{cloud_provider}_{clean_name}_chunk_{i}"
            
            documents_azure_search.append({
                "id": doc_id,
                "cloud_provider": cloud_provider,
                "source_file": nom_fichier,
                "texte": chunk,
                "vecteur": vecteur
            })
            local_embeddings_backup.append({
                "id": doc_id,
                "chunk_index": i,
                "texte": chunk,
                "vecteur": vecteur
            })

        if documents_azure_search:
            # CORRECTION CRITIQUE ICI : On uploade d'abord vers Azure...
            try:
                upload_en_batches(search_client, documents_azure_search)
                print(f"   ✅ Succès Azure pour {nom_fichier} ({len(documents_azure_search)} chunks uploadés)")
                
                # ... et ENSUITE on sauvegarde le fichier local JSON.
                with open(fichier_backup, "w", encoding="utf-8") as f:
                    json.dump(local_embeddings_backup, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"   ❌ Échec de l'upload vers Azure pour {nom_fichier} : {e}")
                print(f"   ⚠️ Le fichier de backup local n'a pas été créé pour permettre une nouvelle tentative.")

    print("\n🎉 ÉTAPE 2 TERMINÉE : Base de données Vectorielle et Sémantique prête !")

if __name__ == "__main__":
    executer_indexation()