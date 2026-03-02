# """
# builder_agent.py — Subul : Agent BUILDER (Production Ready)

# Évolutions Cloud / Production :
#   - 100% Asynchrone (AsyncAzureOpenAI, asyncio.to_thread pour I/O disque et réseau).
#   - Multi-Tenant (utilisation du session_id).
#   - Découplage (Injection de la Mémoire globale via l'Orchestrateur).
#   - Azure AI Speech pour la génération de Podcasts (MP3).
#   - JSON Mode (Azure OpenAI) pour la génération robuste de Flashcards.
# """

# import os
# import sys
# import json
# import uuid
# import asyncio
# from datetime import datetime, timedelta, timezone
# from dotenv import load_dotenv

# # ⚡ Imports Asynchrones et Azure SDKs
# from openai import AsyncAzureOpenAI

# # ── Chemin vers le module mémoire ────────────────────────────────────────────
# _BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# _ROOT_DIR = os.path.dirname(_BASE_DIR)
# if _ROOT_DIR not in sys.path:
#     sys.path.insert(0, _ROOT_DIR)
# from memory_management import MemoryManager

# # ── Configuration ─────────────────────────────────────────────────────────────
# load_dotenv(os.path.join(_ROOT_DIR, "00_Config", ".env.txt"))

# # Client OpenAI Asynchrone
# oai_client = AsyncAzureOpenAI(
#     azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
#     api_key=os.environ["AZURE_OPENAI_API_KEY"],
#     api_version=os.environ["AZURE_OPENAI_API_VERSION"],
# )
# CHAT_MODEL = os.environ["AZURE_OPENAI_CHAT_DEPLOYMENT"]

# # --- Configuration Azure Storage ---
# STORAGE_NAME = os.environ.get("AZURE_STORAGE_ACCOUNT_NAME", "")
# STORAGE_KEY  = os.environ.get("AZURE_STORAGE_ACCOUNT_KEY", "")
# CONTAINER    = os.environ.get("AZURE_BLOB_CONTAINER", "agent-tutor-stockage-artifacts")

# if STORAGE_NAME and STORAGE_KEY:
#     AZURE_STORAGE_CONN_STR = f"DefaultEndpointsProtocol=https;AccountName={STORAGE_NAME};AccountKey={STORAGE_KEY};EndpointSuffix=core.windows.net"
#     AZURE_BLOB_CONTAINER = CONTAINER
# else:
#     AZURE_STORAGE_CONN_STR = ""


# # ── Prompt Rédaction ──────────────────────────────────────────────────────────
# # ── Prompt Rédaction ──────────────────────────────────────────────────────────
# SYSTEM_BUILDER = """Tu es l'Agent Builder Subul, un expert en design pédagogique.
# Ta mission : générer des documents de révision magnifiques, clairs et ultra-structurés.
# RÈGLES DE DESIGN OBLIGATOIRES :
# 1. Utilise des emojis pour chaque grand titre.
# 2. Fais des paragraphes très courts.
# 3. Utilise abondamment le gras (**) pour les mots-clés techniques.
# 4. Si tu compares des choses, fais toujours un joli tableau Markdown (| Colonne 1 | Colonne 2 |).
# 5. Ajoute toujours une section "💡 Astuce Pro" à la fin de tes documents.
# 🌍 RÈGLE DE LANGUE (CRITIQUE) : Rédige le document dans la langue utilisée par l'utilisateur, SAUF s'il demande explicitement une autre langue dans son message (auquel cas, respecte sa demande).
# """


# # ── PDF Generator (Asynchrone via Threading) ──────────────────────────────────
# def _sync_generate_pdf(title: str, content: str, output_path: str) -> str:
#     """Fonction synchrone d'origine pour ReportLab."""
#     try:
#         from reportlab.lib.pagesizes import A4
#         from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
#         from reportlab.lib.units import cm
#         from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
#         from reportlab.lib import colors

#         doc    = SimpleDocTemplate(output_path, pagesize=A4,
#                                    leftMargin=2*cm, rightMargin=2*cm,
#                                    topMargin=2*cm, bottomMargin=2*cm)
#         styles = getSampleStyleSheet()

#         title_style = ParagraphStyle(
#             "DoxTitle", parent=styles["Title"],
#             textColor=colors.HexColor("#1A56DB"),
#             fontSize=22, spaceAfter=20,
#         )
#         body_style = ParagraphStyle(
#             "DoxBody", parent=styles["Normal"],
#             fontSize=11, leading=16, spaceAfter=8,
#         )
#         story = [Paragraph(title, title_style), Spacer(1, 0.5*cm)]
        
#         for line in content.split("\n"):
#             line = line.strip()
#             if not line:
#                 story.append(Spacer(1, 0.3*cm))
#                 continue
#             if line.startswith("### "):
#                 st = ParagraphStyle("H3", parent=styles["Heading3"], fontSize=13)
#                 story.append(Paragraph(line[4:], st))
#             elif line.startswith("## "):
#                 st = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=15, textColor=colors.HexColor("#1A56DB"))
#                 story.append(Paragraph(line[3:], st))
#             elif line.startswith("# "):
#                 story.append(Paragraph(line[2:], title_style))
#             elif line.startswith("- ") or line.startswith("* "):
#                 story.append(Paragraph(f"• {line[2:]}", body_style))
#             else:
#                 html_line = line.replace("**", "<b>", 1).replace("**", "</b>", 1)
#                 story.append(Paragraph(html_line, body_style))

#         footer_style = ParagraphStyle("Footer", parent=styles["Normal"], fontSize=8, textColor=colors.gray)
#         story.append(Spacer(1, 1*cm))
#         story.append(Paragraph(f"📅 Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')} — Subul Platform", footer_style))
        
#         doc.build(story)
#         print(f"   📄 PDF généré : {output_path}")
#         return output_path

#     except ImportError:
#         txt_path = output_path.replace(".pdf", ".txt")
#         with open(txt_path, "w", encoding="utf-8") as f:
#             f.write(f"{title}\n{'='*len(title)}\n\n{content}")
#         print(f"   ⚠️ ReportLab absent — fallback .txt : {txt_path}")
#         return txt_path

# async def generate_pdf_from_markdown(title: str, content: str, output_path: str) -> str:
#     """⚡ Exécute la génération PDF dans un thread séparé pour ne pas bloquer."""
#     return await asyncio.to_thread(_sync_generate_pdf, title, content, output_path)


# # ── Azure AI Speech TTS (Asynchrone via Threading) ────────────────────────────
# def _sync_generate_audio(script: str, output_path: str) -> str | None:
#     """Fonction synchrone d'appel à Azure AI Speech (TTS)."""
#     import azure.cognitiveservices.speech as speechsdk
    
#     speech_key = os.environ.get("AZURE_SPEECH_KEY")
#     speech_region = os.environ.get("AZURE_SPEECH_REGION")
    
#     if not speech_key or not speech_region:
#         print("   ⚠️ Clés Azure Speech manquantes.")
#         return None

#     try:
#         speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=speech_region)
#         # Voix masculine française de haute qualité
#         speech_config.speech_synthesis_voice_name = "fr-FR-HenriNeural" 
        
#         audio_config = speechsdk.audio.AudioOutputConfig(filename=output_path)
#         synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)

#         # Lancement de la synthèse
#         result = synthesizer.speak_text_async(script).get()

#         if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
#             print(f"   🎙️ Podcast Azure généré : {output_path}")
#             return output_path
#         elif result.reason == speechsdk.ResultReason.Canceled:
#             cancellation_details = result.cancellation_details
#             print(f"   ⚠️ Azure TTS Annulé : {cancellation_details.reason}")
#             return None
#     except Exception as e:
#         print(f"   ⚠️ Erreur Azure Speech : {e}")
#         return None

# async def generate_audio_podcast(script: str, output_path: str) -> str | None:
#     """⚡ Exécute la requête Azure TTS de façon non-bloquante."""
#     return await asyncio.to_thread(_sync_generate_audio, script, output_path)


# # ── Azure Blob Upload (Asynchrone via Threading) ──────────────────────────────
# def _sync_upload_to_blob(file_path: str, blob_name: str) -> str | None:
#     """Upload synchrone via le SDK classique Azure."""
#     if not AZURE_STORAGE_CONN_STR:
#         print("   ⚠️ Azure Storage non configuré.")
#         return f"file://{file_path}"
#     try:
#         from azure.storage.blob import BlobServiceClient, BlobSasPermissions, generate_blob_sas
#         service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONN_STR)
#         container_client = service_client.get_container_client(AZURE_BLOB_CONTAINER)

#         try:
#             container_client.create_container()
#         except Exception:
#             pass

#         blob_client = container_client.get_blob_client(blob_name)
#         with open(file_path, "rb") as data:
#             blob_client.upload_blob(data, overwrite=True)

#         account_name = service_client.account_name
#         account_key  = service_client.credential.account_key
#         sas_token = generate_blob_sas(
#             account_name=account_name,
#             container_name=AZURE_BLOB_CONTAINER,
#             blob_name=blob_name,
#             account_key=account_key,
#             permission=BlobSasPermissions(read=True),
#             expiry=datetime.now(timezone.utc) + timedelta(days=7),
#         )
#         sas_url = f"https://{account_name}.blob.core.windows.net/{AZURE_BLOB_CONTAINER}/{blob_name}?{sas_token}"
#         print(f"   ☁️ Fichier uploadé → {sas_url[:80]}…")
#         return sas_url
#     except Exception as e:
#         print(f"   ⚠️ Azure Blob erreur : {e}")
#         return f"file://{file_path}"

# async def upload_to_blob(file_path: str, blob_name: str) -> str | None:
#     """⚡ Upload de façon asynchrone (Non-bloquant)."""
#     return await asyncio.to_thread(_sync_upload_to_blob, file_path, blob_name)


# # ══════════════════════════════════════════════════════════════════════════════
# class BuilderAgent:
#     """Agent Builder Asynchrone : génère PDF, flashcards, podcasts audio."""

#     # 💉 1. Injection de la mémoire partagée
#     def __init__(self, memory):
#         self.memory = memory
#         self._output_dir = os.path.join(_ROOT_DIR, "artifacts")
#         os.makedirs(self._output_dir, exist_ok=True)
#         print("🔧 Builder Asynchrone initialisé — Générateur d'artefacts Subul")

#     # ⚡ LLM : génération de contenu Asynchrone
#     async def _generate_content(self, prompt: str, max_tokens: int = 1500) -> str:
#         try:
#             resp = await oai_client.chat.completions.create(
#                 model=CHAT_MODEL,
#                 messages=[
#                     {"role": "system", "content": SYSTEM_BUILDER},
#                     {"role": "user",   "content": prompt},
#                 ],
#                 max_tokens=max_tokens,
#                 temperature=0.3,
#             )
#             return resp.choices[0].message.content.strip()
#         except Exception as e:
#             print(f"⚠️ [Builder LLM] Erreur : {e}")
#             return "Une erreur s'est produite lors de la rédaction du contenu."

#     # ── Artefact PDF (F11) ─────────────────────────────────────────────────
#     async def generate_pdf(self, session_id: str, topic: str) -> dict:
#         """⚡ Génère un PDF de révision de manière asynchrone."""
#         print(f"   📋 Génération PDF : {topic}")

#         session_history = self.memory.get_short_history(session_id)
#         ctx = ""
#         if session_history:
#             ctx = "\n".join(f"{m['role'].upper()} : {m['content']}" for m in session_history[-10:])
#             ctx = f"\nContexte de session :\n{ctx}\n"

#         prompt = f"""Génère un document de révision cloud complet sur : "{topic}"
# {ctx}
# Structure attendue :
# ## 📖 Introduction
# ## 🔑 Concepts Clés
# ## 💡 Exemples Pratiques
# ## 🔄 Comparaison Multi-Cloud (si applicable)
# ## ✅ Points à Retenir
# ## 📚 Ressources Officielles
# """
#         content = await self._generate_content(prompt, max_tokens=2000)
#         title   = f"Révision Cloud — {topic}"
#         uid     = uuid.uuid4().hex[:8]
#         filename = f"revision_{topic.replace(' ', '_')}_{uid}.pdf"
#         filepath = os.path.join(self._output_dir, filename)

#         await generate_pdf_from_markdown(title, content, filepath)
#         url = await upload_to_blob(filepath, filename)
        
#         return {"path": filepath, "url": url, "title": title, "content_preview": content[:300]}

#     # ── Flashcard (F6 / JSON Mode) ─────────────────────────────────────
#     async def generate_flashcard(self, session_id: str, concept: str, error_count: int = 1) -> dict:
#         """⚡ Génère une flashcard de révision via le JSON Mode d'Azure OpenAI."""
#         print(f"   🃏 Génération Flashcard (JSON) : {concept} (erreurs: {error_count})")
        
#         prompt = f"""Crée une flashcard de révision intensive sur : "{concept}".
# Tu DOIS répondre UNIQUEMENT avec un objet JSON valide ayant exactement cette structure :
# {{
#     "front": "La question précise et directe sur le concept.",
#     "back": "La réponse complète (définition + exemple + analogie).",
#     "piege": "L'erreur classique que les apprenants font sur ce concept."
# }}
# """
#         try:
#             resp = await oai_client.chat.completions.create(
#                 model=CHAT_MODEL,
#                 messages=[
#                     {"role": "system", "content": SYSTEM_BUILDER},
#                     {"role": "user",   "content": prompt},
#                 ],
#                 max_tokens=600,
#                 temperature=0.2,
#                 response_format={"type": "json_object"} # 👈 JSON Mode forcé
#             )
            
#             content_str = resp.choices[0].message.content.strip()
#             data = json.loads(content_str)
            
#             front = data.get("front", "Question ?")
#             back  = data.get("back", "Réponse.")
#             piege = data.get("piege", "")
            
#             markdown_content = f"**RECTO** : {front}\n\n---\n\n**VERSO** : {back}"
#             if piege:
#                 markdown_content += f"\n\n🚨 **Piège Courant** : {piege}"

#         except Exception as e:
#             print(f"⚠️ Erreur LLM ou Parsing JSON : {e}")
#             return {"front": "Erreur", "back": "Impossible de générer la carte.", "url": None}

#         uid      = uuid.uuid4().hex[:8]
#         filename = f"flashcard_{concept.replace(' ', '_')}_{uid}.md"
#         filepath = os.path.join(self._output_dir, filename)
        
#         def _write_file():
#             with open(filepath, "w", encoding="utf-8") as f:
#                 f.write(f"# 🃏 Flashcard — {concept}\n\n{markdown_content}")
#         await asyncio.to_thread(_write_file)

#         url = await upload_to_blob(filepath, filename)
#         return {"front": front, "back": back, "path": filepath, "url": url, "full_content": markdown_content}

#     # ── Podcast Audio (F8 / Azure TTS) ────────────────────────────────────
#     async def generate_podcast(self, session_id: str) -> dict:
#         """⚡ Génère un résumé audio de la session avec Azure Speech."""
#         print("   🎙️ Génération Podcast audio (Azure TTS)…")

#         hist = self.memory.get_short_history(session_id)
#         session_summary = "\n".join(f"{m['role'].upper()} : {m['content']}" for m in hist[-8:])

#         prompt = f"""Rédige un script radio/podcast de 1-2 minutes sur les points clés de cette session cloud.
# Ton : dynamique, professionnel, comme une émission tech. Utilise des transitions orales ("Voilà", "Ensuite", "Pour conclure").
# Pas de Markdown, texte brut uniquement (sera lu par TTS).

# Session à résumer :
# {session_summary}
# """
#         script = await self._generate_content(prompt, max_tokens=500)

#         uid      = uuid.uuid4().hex[:8]
#         mp3_name = f"podcast_{uid}.mp3"
#         mp3_path = os.path.join(self._output_dir, mp3_name)

#         audio_path = await generate_audio_podcast(script, mp3_path)
#         url = await upload_to_blob(audio_path, mp3_name) if audio_path else None

#         return {"script": script, "audio_path": audio_path, "url": url}

#     # ── Export JSON de session ─────────────────────────────────────────────
#     async def export_session_json(self, session_id: str, session_meta: dict) -> dict:
#         """⚡ Export de la session complète en JSON de manière asynchrone."""
#         uid      = uuid.uuid4().hex[:8]
#         filename = f"session_{uid}.json"
#         filepath = os.path.join(self._output_dir, filename)

#         payload = {
#             "session_id"  : uid,
#             "user_session": session_id,
#             "timestamp"   : datetime.now().isoformat(),
#             "platform"    : "Subul",
#             "history"     : self.memory.get_short_history(session_id),
#             **session_meta,
#         }
        
#         def _write_json():
#             with open(filepath, "w", encoding="utf-8") as f:
#                 json.dump(payload, f, ensure_ascii=False, indent=2)
#         await asyncio.to_thread(_write_json)

#         url = await upload_to_blob(filepath, filename)
#         return {"path": filepath, "url": url, "session_id": uid}


# # ══════════════════════════════════════════════════════════════════════════════
# # TEST STANDALONE
# # ══════════════════════════════════════════════════════════════════════════════
# async def _test():
#     # ⚠️ Pour tester en local, on crée une mémoire factice
#     from memory_management import MemoryManager, LocalJSONAdapter
#     test_memory = MemoryManager(oai_client=oai_client, chat_model=CHAT_MODEL, db_adapter=LocalJSONAdapter())
    
#     builder = BuilderAgent(memory=test_memory)
#     session_test = "builder-test-999"

#     test_memory.add_user_message(session_test, "C'est quoi Kubernetes ?")
#     test_memory.add_agent_message(session_test, "K8s est un orchestrateur de conteneurs très puissant.")

#     print("=== Test PDF ===")
#     r_pdf = await builder.generate_pdf(session_test, "Kubernetes vs Docker Swarm")
#     print(f"URL : {r_pdf['url']}\nAperçu : {r_pdf['content_preview'][:100]}...")

#     print("\n=== Test Flashcard (JSON Mode) ===")
#     r_fc = await builder.generate_flashcard(session_test, "Azure Functions vs AWS Lambda", error_count=3)
#     print(r_fc["full_content"][:300])

#     print("\n=== Test Podcast (Azure TTS) ===")
#     r_pod = await builder.generate_podcast(session_test)
#     print(f"Audio URL : {r_pod['url']}")

# if __name__ == "__main__":
#     asyncio.run(_test())


"""
builder_agent.py — Subul : Agent BUILDER (Production Ready)

Évolutions Cloud / Production :
  - 100% Asynchrone (AsyncAzureOpenAI, asyncio.to_thread pour I/O disque et réseau).
  - Multi-Tenant (utilisation du session_id).
  - Découplage (Injection de la Mémoire globale via l'Orchestrateur).
  - Azure AI Speech pour la génération de Podcasts (MP3).
  - JSON Mode (Azure OpenAI) pour la génération robuste de Flashcards.
  - 🌍 i18n & Markdown : Les messages sont localisés dynamiquement et formatés pour React.
"""

import os
import sys
import json
import uuid
import asyncio
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

# ⚡ Imports Asynchrones, Détection de langue et Azure SDKs
from openai import AsyncAzureOpenAI
from langdetect import detect

# ── Chemin vers le module mémoire ────────────────────────────────────────────
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_BASE_DIR)
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)
from memory_management import MemoryManager

# ── Configuration ─────────────────────────────────────────────────────────────
load_dotenv(os.path.join(_ROOT_DIR, "00_Config", ".env.txt"))

# Client OpenAI Asynchrone
oai_client = AsyncAzureOpenAI(
    azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
    api_version=os.environ["AZURE_OPENAI_API_VERSION"],
)
CHAT_MODEL = os.environ["AZURE_OPENAI_CHAT_DEPLOYMENT"]

# --- Configuration Azure Storage ---
STORAGE_NAME = os.environ.get("AZURE_STORAGE_ACCOUNT_NAME", "")
STORAGE_KEY  = os.environ.get("AZURE_STORAGE_ACCOUNT_KEY", "")
CONTAINER    = os.environ.get("AZURE_BLOB_CONTAINER", "agent-tutor-stockage-artifacts")

if STORAGE_NAME and STORAGE_KEY:
    AZURE_STORAGE_CONN_STR = f"DefaultEndpointsProtocol=https;AccountName={STORAGE_NAME};AccountKey={STORAGE_KEY};EndpointSuffix=core.windows.net"
    AZURE_BLOB_CONTAINER = CONTAINER
else:
    AZURE_STORAGE_CONN_STR = ""


# ── Prompt Rédaction ──────────────────────────────────────────────────────────
SYSTEM_BUILDER = """Tu es l'Agent Builder Subul, un expert en design pédagogique.
Ta mission : générer des documents de révision magnifiques, clairs et ultra-structurés.
RÈGLES DE DESIGN OBLIGATOIRES :
1. Utilise des emojis pour chaque grand titre.
2. Fais des paragraphes très courts.
3. Utilise abondamment le gras (**) pour les mots-clés techniques.
4. Si tu compares des choses, fais toujours un joli tableau Markdown (| Colonne 1 | Colonne 2 |).
5. Ajoute toujours une section "💡 Astuce Pro" à la fin de tes documents.
🌍 RÈGLE DE LANGUE (CRITIQUE) : Rédige le document dans la langue utilisée par l'utilisateur, SAUF s'il demande explicitement une autre langue dans son message (auquel cas, respecte sa demande).
"""

# ── Helper de Localisation (i18n) ─────────────────────────────────────────────
def _get_localized_message(user_message: str, topic: str, url: str, artifact_type: str, markdown_content: str = "") -> str:
    """Détecte la langue de l'utilisateur et renvoie le message Markdown adapté (0ms de latence)."""
    try:
        lang = detect(user_message)
    except:
        lang = "fr" # Fallback par défaut

    if lang == "en":
        if artifact_type == "pdf":
            return f"✅ Document ready! I've generated your revision guide on **{topic}**.\n\n👉 **[Download PDF]({url})**"
        elif artifact_type == "flashcard":
            return f"✅ Here is your flashcard:\n\n{markdown_content}\n\n👉 **[Save Flashcard (.md)]({url})**"
        elif artifact_type == "podcast":
            return f"🎙️ The podcast summary of our session is ready!\n\n🎧 **[Listen to the Podcast (.mp3)]({url})**"
    else:
        if artifact_type == "pdf":
            return f"✅ C'est prêt ! J'ai généré ton document de révision sur **{topic}**.\n\n👉 **[Télécharger le PDF]({url})**"
        elif artifact_type == "flashcard":
            return f"✅ Voici ta flashcard :\n\n{markdown_content}\n\n👉 **[Sauvegarder la Flashcard (.md)]({url})**"
        elif artifact_type == "podcast":
            return f"🎙️ Le podcast résumé de notre session est prêt !\n\n🎧 **[Écouter le Podcast (.mp3)]({url})**"

    return "Document généré."

# ── PDF Generator (Asynchrone via Threading) ──────────────────────────────────
def _sync_generate_pdf(title: str, content: str, output_path: str) -> str:
    """Fonction synchrone d'origine pour ReportLab."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib import colors

        doc    = SimpleDocTemplate(output_path, pagesize=A4,
                                   leftMargin=2*cm, rightMargin=2*cm,
                                   topMargin=2*cm, bottomMargin=2*cm)
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            "DoxTitle", parent=styles["Title"],
            textColor=colors.HexColor("#1A56DB"),
            fontSize=22, spaceAfter=20,
        )
        body_style = ParagraphStyle(
            "DoxBody", parent=styles["Normal"],
            fontSize=11, leading=16, spaceAfter=8,
        )
        story = [Paragraph(title, title_style), Spacer(1, 0.5*cm)]
        
        for line in content.split("\n"):
            line = line.strip()
            if not line:
                story.append(Spacer(1, 0.3*cm))
                continue
            if line.startswith("### "):
                st = ParagraphStyle("H3", parent=styles["Heading3"], fontSize=13)
                story.append(Paragraph(line[4:], st))
            elif line.startswith("## "):
                st = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=15, textColor=colors.HexColor("#1A56DB"))
                story.append(Paragraph(line[3:], st))
            elif line.startswith("# "):
                story.append(Paragraph(line[2:], title_style))
            elif line.startswith("- ") or line.startswith("* "):
                story.append(Paragraph(f"• {line[2:]}", body_style))
            else:
                html_line = line.replace("**", "<b>", 1).replace("**", "</b>", 1)
                story.append(Paragraph(html_line, body_style))

        footer_style = ParagraphStyle("Footer", parent=styles["Normal"], fontSize=8, textColor=colors.gray)
        story.append(Spacer(1, 1*cm))
        story.append(Paragraph(f"📅 Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')} — Subul Platform", footer_style))
        
        doc.build(story)
        print(f"   📄 PDF généré : {output_path}")
        return output_path

    except ImportError:
        txt_path = output_path.replace(".pdf", ".txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(f"{title}\n{'='*len(title)}\n\n{content}")
        print(f"   ⚠️ ReportLab absent — fallback .txt : {txt_path}")
        return txt_path

async def generate_pdf_from_markdown(title: str, content: str, output_path: str) -> str:
    """⚡ Exécute la génération PDF dans un thread séparé pour ne pas bloquer."""
    return await asyncio.to_thread(_sync_generate_pdf, title, content, output_path)


# ── Azure AI Speech TTS (Asynchrone via Threading) ────────────────────────────
def _sync_generate_audio(script: str, output_path: str) -> str | None:
    """Fonction synchrone d'appel à Azure AI Speech (TTS)."""
    import azure.cognitiveservices.speech as speechsdk
    
    speech_key = os.environ.get("AZURE_SPEECH_KEY")
    speech_region = os.environ.get("AZURE_SPEECH_REGION")
    
    if not speech_key or not speech_region:
        print("   ⚠️ Clés Azure Speech manquantes.")
        return None

    try:
        speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=speech_region)
        # Voix masculine française de haute qualité
        speech_config.speech_synthesis_voice_name = "fr-FR-HenriNeural" 
        
        audio_config = speechsdk.audio.AudioOutputConfig(filename=output_path)
        synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)

        # Lancement de la synthèse
        result = synthesizer.speak_text_async(script).get()

        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            print(f"   🎙️ Podcast Azure généré : {output_path}")
            return output_path
        elif result.reason == speechsdk.ResultReason.Canceled:
            cancellation_details = result.cancellation_details
            print(f"   ⚠️ Azure TTS Annulé : {cancellation_details.reason}")
            return None
    except Exception as e:
        print(f"   ⚠️ Erreur Azure Speech : {e}")
        return None

async def generate_audio_podcast(script: str, output_path: str) -> str | None:
    """⚡ Exécute la requête Azure TTS de façon non-bloquante."""
    return await asyncio.to_thread(_sync_generate_audio, script, output_path)


# ── Azure Blob Upload (Asynchrone via Threading) ──────────────────────────────
def _sync_upload_to_blob(file_path: str, blob_name: str) -> str | None:
    """Upload synchrone via le SDK classique Azure."""
    if not AZURE_STORAGE_CONN_STR:
        print("   ⚠️ Azure Storage non configuré.")
        return f"file://{file_path}"
    try:
        from azure.storage.blob import BlobServiceClient, BlobSasPermissions, generate_blob_sas
        service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONN_STR)
        container_client = service_client.get_container_client(AZURE_BLOB_CONTAINER)

        try:
            container_client.create_container()
        except Exception:
            pass

        blob_client = container_client.get_blob_client(blob_name)
        with open(file_path, "rb") as data:
            blob_client.upload_blob(data, overwrite=True)

        account_name = service_client.account_name
        account_key  = service_client.credential.account_key
        sas_token = generate_blob_sas(
            account_name=account_name,
            container_name=AZURE_BLOB_CONTAINER,
            blob_name=blob_name,
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.now(timezone.utc) + timedelta(days=7),
        )
        sas_url = f"https://{account_name}.blob.core.windows.net/{AZURE_BLOB_CONTAINER}/{blob_name}?{sas_token}"
        print(f"   ☁️ Fichier uploadé → {sas_url[:80]}…")
        return sas_url
    except Exception as e:
        print(f"   ⚠️ Azure Blob erreur : {e}")
        return f"file://{file_path}"

async def upload_to_blob(file_path: str, blob_name: str) -> str | None:
    """⚡ Upload de façon asynchrone (Non-bloquant)."""
    return await asyncio.to_thread(_sync_upload_to_blob, file_path, blob_name)


# ══════════════════════════════════════════════════════════════════════════════
class BuilderAgent:
    """Agent Builder Asynchrone : génère PDF, flashcards, podcasts audio."""

    # 💉 1. Injection de la mémoire partagée
    def __init__(self, memory):
        self.memory = memory
        self._output_dir = os.path.join(_ROOT_DIR, "artifacts")
        os.makedirs(self._output_dir, exist_ok=True)
        print("🔧 Builder Asynchrone initialisé — Générateur d'artefacts Subul")

    # ⚡ LLM : génération de contenu Asynchrone
    async def _generate_content(self, prompt: str, max_tokens: int = 1500) -> str:
        try:
            resp = await oai_client.chat.completions.create(
                model=CHAT_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_BUILDER},
                    {"role": "user",   "content": prompt},
                ],
                max_tokens=max_tokens,
                temperature=0.3,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            print(f"⚠️ [Builder LLM] Erreur : {e}")
            return "Une erreur s'est produite lors de la rédaction du contenu."

    # ── Artefact PDF (F11) ─────────────────────────────────────────────────
    async def generate_pdf(self, session_id: str, topic: str, user_message: str) -> dict:
        """⚡ Génère un PDF de révision de manière asynchrone."""
        print(f"   📋 Génération PDF : {topic}")

        session_history = self.memory.get_short_history(session_id)
        ctx = ""
        if session_history:
            ctx = "\n".join(f"{m['role'].upper()} : {m['content']}" for m in session_history[-10:])
            ctx = f"\nContexte de session :\n{ctx}\n"

        prompt = f"""Génère un document de révision cloud complet sur : "{topic}"
{ctx}
Structure attendue :
## 📖 Introduction
## 🔑 Concepts Clés
## 💡 Exemples Pratiques
## 🔄 Comparaison Multi-Cloud (si applicable)
## ✅ Points à Retenir
## 📚 Ressources Officielles
"""
        content = await self._generate_content(prompt, max_tokens=2000)
        title   = f"Révision Cloud — {topic}"
        uid     = uuid.uuid4().hex[:8]
        filename = f"revision_{topic.replace(' ', '_')}_{uid}.pdf"
        filepath = os.path.join(self._output_dir, filename)

        await generate_pdf_from_markdown(title, content, filepath)
        url = await upload_to_blob(filepath, filename)
        
        # 🟢 Message Markdown cliquable localisé
        message = _get_localized_message(user_message, topic, url, "pdf")
        
        return {"message": message, "url": url}

    # ── Flashcard (F6 / JSON Mode) ─────────────────────────────────────
    async def generate_flashcard(self, session_id: str, concept: str, user_message: str, error_count: int = 1) -> dict:
        """⚡ Génère une flashcard de révision via le JSON Mode d'Azure OpenAI."""
        print(f"   🃏 Génération Flashcard (JSON) : {concept} (erreurs: {error_count})")
        
        prompt = f"""Crée une flashcard de révision intensive sur : "{concept}".
Tu DOIS répondre UNIQUEMENT avec un objet JSON valide ayant exactement cette structure :
{{
    "front": "La question précise et directe sur le concept.",
    "back": "La réponse complète (définition + exemple + analogie).",
    "piege": "L'erreur classique que les apprenants font sur ce concept."
}}
"""
        try:
            resp = await oai_client.chat.completions.create(
                model=CHAT_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_BUILDER},
                    {"role": "user",   "content": prompt},
                ],
                max_tokens=600,
                temperature=0.2,
                response_format={"type": "json_object"} # 👈 JSON Mode forcé
            )
            
            content_str = resp.choices[0].message.content.strip()
            data = json.loads(content_str)
            
            front = data.get("front", "Question ?")
            back  = data.get("back", "Réponse.")
            piege = data.get("piege", "")
            
            markdown_content = f"**RECTO** : {front}\n\n---\n\n**VERSO** : {back}"
            if piege:
                markdown_content += f"\n\n🚨 **Piège Courant** : {piege}"

        except Exception as e:
            print(f"⚠️ Erreur LLM ou Parsing JSON : {e}")
            return {"message": "Erreur lors de la génération de la carte.", "url": None}

        uid      = uuid.uuid4().hex[:8]
        filename = f"flashcard_{concept.replace(' ', '_')}_{uid}.md"
        filepath = os.path.join(self._output_dir, filename)
        
        def _write_file():
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"# 🃏 Flashcard — {concept}\n\n{markdown_content}")
        await asyncio.to_thread(_write_file)

        url = await upload_to_blob(filepath, filename)
        
        # 🟢 Message Markdown cliquable localisé
        message = _get_localized_message(user_message, concept, url, "flashcard", markdown_content)
        
        return {"message": message, "url": url}

    # ── Podcast Audio (F8 / Azure TTS) ────────────────────────────────────
    async def generate_podcast(self, session_id: str, user_message: str) -> dict:
        """⚡ Génère un résumé audio de la session avec Azure Speech."""
        print("   🎙️ Génération Podcast audio (Azure TTS)…")

        hist = self.memory.get_short_history(session_id)
        session_summary = "\n".join(f"{m['role'].upper()} : {m['content']}" for m in hist[-8:])

        prompt = f"""Rédige un script radio/podcast de 1-2 minutes sur les points clés de cette session cloud.
Ton : dynamique, professionnel, comme une émission tech. Utilise des transitions orales ("Voilà", "Ensuite", "Pour conclure").
Pas de Markdown, texte brut uniquement (sera lu par TTS).

Session à résumer :
{session_summary}
"""
        script = await self._generate_content(prompt, max_tokens=500)

        uid      = uuid.uuid4().hex[:8]
        mp3_name = f"podcast_{uid}.mp3"
        mp3_path = os.path.join(self._output_dir, mp3_name)

        audio_path = await generate_audio_podcast(script, mp3_path)
        url = await upload_to_blob(audio_path, mp3_name) if audio_path else None

        # 🟢 Message Markdown cliquable localisé
        message = _get_localized_message(user_message, "Podcast", url, "podcast")

        return {"message": message, "url": url}

    # ── Export JSON de session ─────────────────────────────────────────────
    async def export_session_json(self, session_id: str, session_meta: dict) -> dict:
        """⚡ Export de la session complète en JSON de manière asynchrone."""
        uid      = uuid.uuid4().hex[:8]
        filename = f"session_{uid}.json"
        filepath = os.path.join(self._output_dir, filename)

        payload = {
            "session_id"  : uid,
            "user_session": session_id,
            "timestamp"   : datetime.now().isoformat(),
            "platform"    : "Subul",
            "history"     : self.memory.get_short_history(session_id),
            **session_meta,
        }
        
        def _write_json():
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        await asyncio.to_thread(_write_json)

        url = await upload_to_blob(filepath, filename)
        return {"path": filepath, "url": url, "session_id": uid}


# ══════════════════════════════════════════════════════════════════════════════
# TEST STANDALONE
# ══════════════════════════════════════════════════════════════════════════════
async def _test():
    # ⚠️ Pour tester en local, on crée une mémoire factice
    from memory_management import MemoryManager, LocalJSONAdapter
    test_memory = MemoryManager(oai_client=oai_client, chat_model=CHAT_MODEL, db_adapter=LocalJSONAdapter())
    
    builder = BuilderAgent(memory=test_memory)
    session_test = "builder-test-999"

    test_memory.add_user_message(session_test, "C'est quoi Kubernetes ?")
    test_memory.add_agent_message(session_test, "K8s est un orchestrateur de conteneurs très puissant.")

    print("=== Test PDF ===")
    r_pdf = await builder.generate_pdf(session_test, "Kubernetes vs Docker Swarm", "Génère un pdf en français")
    print(r_pdf["message"])

    print("\n=== Test Flashcard (JSON Mode) ===")
    r_fc = await builder.generate_flashcard(session_test, "Azure Functions vs AWS Lambda", "Give me a flashcard", error_count=3)
    print(r_fc["message"])

    print("\n=== Test Podcast (Azure TTS) ===")
    r_pod = await builder.generate_podcast(session_test, "Create an audio summary")
    print(r_pod["message"])

if __name__ == "__main__":
    asyncio.run(_test())