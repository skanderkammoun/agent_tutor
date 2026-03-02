//le code le plus juste 

import React, { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export default function App() {
  const [messages, setMessages] = useState([
    { role: 'assistant', content: 'Bonjour ! Je suis Subul. Mode Ultra-Latence WebSocket ET Bilingue activés !', agent: 'Subul' }
  ]);
  const [inputMessage, setInputMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  
  // Audio states (STT)
  const [liveTranscript, setLiveTranscript] = useState("");
  const [isRecording, setIsRecording] = useState(false);
  const mediaRecorderRef = useRef(null);
  const sttSocketRef = useRef(null); 

  // Moteur Audio Temps Réel (TTS)
  const ttsSocketRef = useRef(null);
  const audioContextRef = useRef(null);
  const nextPlayTimeRef = useRef(0);
  const messagesEndRef = useRef(null);
  
  // 🛡️ MODIFICATION 1 : Contrôleur pour tuer la requête serveur
  const abortControllerRef = useRef(null);

  // 🛡️ NOUVEAU : Identifiants uniques pour la mémoire Cloud (User et Session)
  const [userId] = useState(() => {
    let savedId = localStorage.getItem('subul_user_id');
    if (!savedId) {
      savedId = 'user_' + Math.random().toString(36).substr(2, 9);
      localStorage.setItem('subul_user_id', savedId);
    }
    return savedId;
  });

  const [sessionId] = useState(() => {
    return 'session_' + Math.random().toString(36).substr(2, 9);
  });

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, liveTranscript]);

  const cleanTextForTTS = (text) => {
    if (!text) return "";
    return text.replace(/[*#_~>|`\-]/g, '').trim();
  };

  // ⚙️ INITIALISATION DU MOTEUR AUDIO (Web Audio API)
  const initAudioContext = () => {
    if (!audioContextRef.current) {
      audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 24000 });
    }
    if (audioContextRef.current.state === 'suspended') {
      audioContextRef.current.resume();
    }
  };

  // 🛑 MODIFICATION 2 : FONCTION POUR COUPER L'IA INSTANTANÉMENT
  const interruptAssistant = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort(); // Tue la requête HTTP
      abortControllerRef.current = null;
    }
    if (ttsSocketRef.current) {
      ttsSocketRef.current.close(); // Ferme le flux audio Deepgram
      ttsSocketRef.current = null;
    }
    if (audioContextRef.current) {
      audioContextRef.current.close(); // Vide la carte son du navigateur
      audioContextRef.current = null;
    }
    setIsLoading(false);
  };

  // 🔊 LECTURE DU FLUX BINAIRE (Linear16 PCM) EN TEMPS RÉEL
  const playAudioChunk = (arrayBuffer) => {
    const audioContext = audioContextRef.current;
    if (!audioContext) return;

    const int16Array = new Int16Array(arrayBuffer);
    const float32Array = new Float32Array(int16Array.length);
    for (let i = 0; i < int16Array.length; i++) {
      float32Array[i] = int16Array[i] / 32768.0; 
    }

    const audioBuffer = audioContext.createBuffer(1, float32Array.length, 24000);
    audioBuffer.getChannelData(0).set(float32Array);

    const source = audioContext.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(audioContext.destination);

    const currentTime = audioContext.currentTime;
    if (nextPlayTimeRef.current < currentTime) {
      nextPlayTimeRef.current = currentTime;
    }

    source.start(nextPlayTimeRef.current);
    nextPlayTimeRef.current += audioBuffer.duration;
  };


  // --- 🧠 ENVOI MESSAGE & STREAMING HYBRIDE ---
  const sendMessage = async (rawMessage, isAudio = false) => {
    if (!rawMessage || !rawMessage.trim()) return;

    // 🛑 MODIFICATION 3A : On coupe l'IA avant de poser une nouvelle question
    interruptAssistant();

    setMessages(prev => [...prev, { role: 'user', content: rawMessage }]);
    setInputMessage('');
    setIsLoading(true);

    initAudioContext();
    nextPlayTimeRef.current = audioContextRef.current.currentTime;
    
    // 🛡️ MODIFICATION 3B : Préparation du signal d'annulation
    abortControllerRef.current = new AbortController();

    try {
      const response = await fetch('http://localhost:8000/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        // 🛡️ NOUVEAU : On envoie l'ID utilisateur et l'ID session au serveur Python
        body: JSON.stringify({ 
          message: rawMessage, 
          is_audio: isAudio,
          user_id: userId,
          session_id: sessionId
        }),
        signal: abortControllerRef.current.signal
      });

      if (!response.ok) throw new Error("Erreur serveur");

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let fullResponse = "";
      let jsonBuffer = "";
      
      setIsLoading(false);
      setMessages(prev => [...prev, { role: 'assistant', content: '', agent: 'Analyse...' }]);

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        
        jsonBuffer += decoder.decode(value, { stream: true });
        let boundary = jsonBuffer.indexOf('\n');
        
        while (boundary !== -1) {
          const line = jsonBuffer.slice(0, boundary);
          jsonBuffer = jsonBuffer.slice(boundary + 1);
          boundary = jsonBuffer.indexOf('\n');
          
          if (line.trim()) {
            try {
              const data = JSON.parse(line);
              const chunk = data.chunk;
              const detectedLang = data.lang || "fr"; 
              fullResponse += chunk;
              
              setMessages(prev => {
                const newMessages = [...prev];
                newMessages[newMessages.length - 1] = { role: 'assistant', content: fullResponse, agent: "Subul" };
                return newMessages;
              });

              if (isAudio && data.status === "streaming") {
                const cleanSentence = cleanTextForTTS(chunk);
                
                if (cleanSentence.trim()) {
                    if (!ttsSocketRef.current) {
                        const apiKey = import.meta.env.VITE_DEEPGRAM_API_KEY;
                        const modelName = detectedLang === "fr" ? "aura-2-agathe-fr" : "aura-2-arcas-en";
                        
                        ttsSocketRef.current = new WebSocket(`wss://api.deepgram.com/v1/speak?model=${modelName}&encoding=linear16&sample_rate=24000`, ['token', apiKey]);
                        ttsSocketRef.current.binaryType = 'arraybuffer';

                        ttsSocketRef.current.onmessage = (event) => {
                          if (typeof event.data !== 'string') {
                            playAudioChunk(event.data);
                          }
                        };
                    }

                    if (ttsSocketRef.current.readyState === WebSocket.OPEN) {
                        ttsSocketRef.current.send(JSON.stringify({ type: 'Speak', text: cleanSentence }));
                    } else if (ttsSocketRef.current.readyState === WebSocket.CONNECTING) {
                        ttsSocketRef.current.addEventListener('open', () => {
                            ttsSocketRef.current.send(JSON.stringify({ type: 'Speak', text: cleanSentence }));
                        }, { once: true });
                    }
                }
              }
            } catch (err) {}
          }
        }
      }

      

      // 🛡️ NOUVEAU : On force le Flush même si le socket met du temps à s'ouvrir
      if (isAudio) {
        const sendFlush = () => {
            if (ttsSocketRef.current && ttsSocketRef.current.readyState === 1) {
                ttsSocketRef.current.send(JSON.stringify({ type: 'Flush' }));
            } else if (ttsSocketRef.current && ttsSocketRef.current.readyState === 0) {
                setTimeout(sendFlush, 50); // On réessaie dans 50ms
            }
        };
        sendFlush();
      }

    } catch (e) {
      if (e.name === 'AbortError') {
        console.log("IA interrompue par l'utilisateur.");
      } else {
        setMessages(prev => [...prev, { role: 'assistant', content: "❌ Impossible de contacter le serveur.", agent: 'Système' }]);
        setIsLoading(false);
      }
    }
  };


  // --- 🎙️ WEBSOCKET DEEPGRAM (STT - Les Oreilles) ---
  const startRecording = async () => {
    interruptAssistant();
    
    setLiveTranscript("");
    if (audioContextRef.current) {
        nextPlayTimeRef.current = audioContextRef.current.currentTime;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const apiKey = import.meta.env.VITE_DEEPGRAM_API_KEY; 
      
      const socket = new WebSocket(
        `wss://api.deepgram.com/v1/listen?model=nova-3&language=multi&smart_format=true&endpointing=100`, 
        ['token', apiKey]
      );
      sttSocketRef.current = socket;

      socket.onopen = () => {
        setIsRecording(true);
        const mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
        mediaRecorderRef.current = mediaRecorder;

        mediaRecorder.ondataavailable = (event) => {
          if (event.data.size > 0 && socket.readyState === 1) {
            socket.send(event.data);
          }
        };
        mediaRecorder.start(250);
      };

      let finalTranscriptAccumulator = "";

      socket.onmessage = (message) => {
        const received = JSON.parse(message.data);
        if (received.type === "Results" && received.channel) {
            const transcript = received.channel.alternatives[0].transcript;
            if (transcript && received.is_final) {
              finalTranscriptAccumulator += transcript + " ";
              setLiveTranscript(finalTranscriptAccumulator);
            } else if (transcript) {
              setLiveTranscript(finalTranscriptAccumulator + transcript);
            }
        }
      };

      socket.onclose = () => {
        setIsRecording(false);
        if (finalTranscriptAccumulator.trim() !== "") {
          sendMessage(finalTranscriptAccumulator, true);
        }
        setLiveTranscript("");
      };

    } catch (err) { 
      console.error(err);
      alert("Micro inaccessible."); 
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      mediaRecorderRef.current.stream.getTracks().forEach(t => t.stop());
      setIsRecording(false);
      if (sttSocketRef.current && sttSocketRef.current.readyState === 1) {
          sttSocketRef.current.send(JSON.stringify({ type: 'CloseStream' }));
      }
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage(inputMessage, false);
    }
  };

  return (
    <div className="bg-[#f6f6f8] text-slate-900 h-screen flex flex-col font-sans">
      <header className="h-16 border-b border-slate-200 flex items-center justify-center px-6 bg-white shrink-0 shadow-sm">
        <h1 className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-600 to-indigo-600">☁️ Subul IA</h1>
      </header>

      <main className="flex-1 overflow-y-auto px-4 py-6 md:px-20 lg:px-40">
        {messages.map((msg, idx) => (
          <div key={idx} className={`flex flex-col gap-1 mb-6 ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
            {msg.role === 'assistant' && <span className="text-xs font-bold text-slate-400 ml-2 uppercase tracking-wide">🤖 {msg.agent}</span>}
            
            <div className={`p-4 rounded-2xl max-w-[85%] ${msg.role === 'user' ? 'bg-blue-600 text-white rounded-br-sm shadow-md' : 'bg-white text-slate-800 border border-slate-200 rounded-bl-sm shadow-sm'}`}>
              {msg.role === 'user' ? (
                <div>{msg.content}</div>
              ) : (
                <div className="prose prose-sm max-w-none text-slate-800">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                </div>
              )}
            </div>
          </div>
        ))}
        
        {isRecording && liveTranscript && (
          <div className="flex flex-col items-end mb-6">
            <div className="p-4 rounded-2xl max-w-[85%] bg-blue-400 text-white rounded-br-sm shadow-md italic opacity-90">
              {liveTranscript} <span className="animate-pulse">...</span>
            </div>
          </div>
        )}
        
        {isLoading && !isRecording && <div className="text-sm text-slate-400 animate-pulse ml-2 font-medium">Subul réfléchit...</div>}
        <div ref={messagesEndRef} />
      </main>

      <footer className="p-4 bg-white border-t border-slate-200 shrink-0">
        <div className="max-w-4xl mx-auto flex items-end gap-3 bg-slate-50 border border-slate-200 rounded-2xl p-2 transition-all focus-within:ring-2 focus-within:ring-blue-100">
          <button
            onMouseDown={startRecording} onMouseUp={stopRecording} onMouseLeave={stopRecording}
            className={`flex items-center justify-center w-12 h-12 rounded-xl transition-all ${isRecording ? 'bg-red-100 text-red-600 animate-pulse' : 'bg-slate-200 text-slate-600 hover:bg-slate-300'}`}
          >
            🎙️
          </button>
          <textarea
            className="flex-1 bg-transparent border-none resize-none py-3 outline-none font-medium text-slate-700"
            placeholder="Maintenez le micro pour parler, ou tapez votre texte..."
            rows="1" value={inputMessage} onChange={(e) => setInputMessage(e.target.value)} onKeyDown={handleKeyPress}
          />
          <button
            onClick={() => sendMessage(inputMessage, false)}
            disabled={!inputMessage.trim() || isLoading || isRecording}
            className="w-12 h-12 rounded-xl bg-blue-600 text-white flex items-center justify-center hover:bg-blue-700 disabled:opacity-50 transition-all"
          >
            ➤
          </button>
        </div>
      </footer>
    </div>
  );
}