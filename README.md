# ☁️ Subul Tuteur IA (Agent Tutor)

Un tuteur interactif intelligent, vocal et textuel, conçu pour accompagner les étudiants dans leurs parcours d'apprentissage Cloud. 

Grâce à une architecture de streaming bidirectionnel, ce tuteur offre une expérience de conversation naturelle, ultra-rapide (zéro latence) et bilingue (Français / Anglais).

---

## ✨ Fonctionnalités Principales

* 🗣️ **Mode Vocal Temps Réel** : 
    * **Oreilles (STT)** : Transcription instantanée via **Deepgram** (modèle `nova-3`).
    * **Voix (TTS)** : Synthèse vocale ultra-réaliste via **Cartesia** (modèle `sonic-3` en 44100Hz).
* ⚡ **Streaming Hybride Optimisé** : Le frontend (React) n'attend pas la fin de la réponse. Les mots générés par le backend (FastAPI) sont expédiés au moteur vocal dès qu'une ponctuation est détectée.
* 🧠 **Intelligence RAG** : Le tuteur interroge une base vectorielle (Azure Search) pour fournir un contexte précis sur les cours et les labs.
* 🌍 **Bilingue Intelligent** : Détection automatique de la langue (FR/EN) et bascule instantanée vers la voix appropriée.
* 📝 **Mémoire & Bilan** : Génération asynchrone d'un résumé pédagogique à la clôture de la session.

---

## 🎙️ Identifiants Vocaux (Cartesia)

Pour garantir la meilleure prononciation et le meilleur accent, ce projet utilise des voix spécifiques configurées en dur dans le frontend (WebSockets) et le backend (Fallback API) :

* 🇬🇧 **Voix Anglaise** (Tessa / English) : `6ccbfb76-1fc6-48f7-b71d-91ac6298247b`
* 🇫🇷 **Voix Française** (Léa / Parisian) : `65b25c5d-ff07-4687-a04c-da2f43ef6fa9`

---

## 🏗️ Stack Technique

### Frontend (Client React)
* **Framework** : React avec Tailwind CSS pour le style.
* **Audio** : WebSockets, `AudioContext` pour la lecture en flux binaire brut (`pcm_f32le`), `MediaRecorder` pour la capture.
* **Rendu** : `react-markdown` pour afficher la structure des réponses.

### Backend (Serveur Python)
* **Framework** : FastAPI avec `asyncio` pour des réponses `application/x-ndjson`.
* **Agent IA** : `AccompanyingAgent` (Architecture RAG).
* **Détection de langue** : Librairie `langdetect`.

---

## ⚙️ Configuration (.env)

**1. Côté Frontend (Vite/React) :**
Créez un fichier `.env` à la racine de votre interface React :
```env
VITE_DEEPGRAM_API_KEY=votre_cle_deepgram
VITE_CARTESIA_API_KEY=votre_cle_cartesia
