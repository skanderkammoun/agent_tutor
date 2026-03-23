# 🎓 Subul Agent Tuteur IA

Un tuteur pédagogique intelligent et interactif, conçu pour accompagner les étudiants (ex: certifications AZ-900) avec une expérience vocale et textuelle en temps réel. 

Propulsé par une architecture RAG avancée et des flux audio basse latence, l'Agent Tuteur offre des conversations fluides, naturelles et bilingues.

---

## ✨ Fonctionnalités Clés

* 🗣️ **Vocal Temps Réel (Latence < 1s)** : 
    * **Oreilles (STT)** : Transcription instantanée via **Deepgram** (modèle `nova-3`) avec détection automatique de la langue.
    * **Voix (TTS)** : Synthèse vocale ultra-réaliste via **Cartesia** (modèle `sonic-3` en 44100Hz).
* ⚡ **Streaming Hybride Optimisé** : Le backend FastAPI n'attend pas la fin de la phrase de l'IA. Dès qu'une ponctuation est générée, le flux audio est envoyé au frontend, garantissant une latence quasi nulle.
* 🧠 **Intelligence RAG (Retrieval-Augmented Generation)** : L'agent s'appuie sur une base documentaire indexée pour fournir des explications précises sur les cours et les labs.
* 🌍 **Bilingue Dynamique** : Détection de la langue de l'utilisateur (FR/EN) et adaptation instantanée de la voix de l'IA et de ses réponses.
* 💾 **Mémoire & Bilan Pédagogique** : À la fin de chaque session, un résumé asynchrone est généré et stocké en mémoire longue.
* 📎 **Support Multimodal** : Capacité d'analyser des images/captures d'écran envoyées par l'étudiant.

---

## 🏗️ Stack Technique

### Frontend (Client)
* **Framework** : React / Next.js
* **Styling** : Tailwind CSS, Framer Motion
* **Audio** : WebSockets natifs, `AudioContext` (44100Hz), `MediaRecorder`
* **Rendu texte** : `react-markdown`

### Backend (Serveur)
* **Framework** : FastAPI (Python) avec `asyncio`
* **Agent IA** : LangChain / Architecture RAG personnalisée (`BrainAgent`)
* **Détection de langue** : `langdetect`
* **Base de données / FinOps** : Azure Cosmos DB (historique, mémoire longue, gestion des quotas).

---

## 🛠️ Prérequis

Avant de lancer le projet, assurez-vous d'avoir :
* **Node.js** (v18+)
* **Python** (v3.8+)
* Des clés API valides pour :
    * [Deepgram](https://deepgram.com/) (Speech-to-Text)
    * [Cartesia](https://cartesia.ai/) (Text-to-Speech)
    * Votre fournisseur LLM (OpenAI, Azure OpenAI, etc., configuré dans le `BrainAgent`)

---

## ⚙️ Configuration (.env)

Créez un fichier `.env` à la racine du **Frontend** :
```env
VITE_DEEPGRAM_API_KEY=votre_cle_deepgram
VITE_CARTESIA_API_KEY=votre_cle_cartesia
# Si Next.js :
# NEXT_PUBLIC_DEEPGRAM_API_KEY=votre_cle_deepgram
# NEXT_PUBLIC_CARTESIA_API_KEY=votre_cle_cartesia
