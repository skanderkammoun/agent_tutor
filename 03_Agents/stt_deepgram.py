import os
import asyncio
from deepgram import (
    DeepgramClient,
    DeepgramClientOptions,
    LiveTranscriptionEvents,
    LiveOptions,
    Microphone,
)

class SpeechToText:
    def __init__(self):
        config = DeepgramClientOptions(options={"keepalive": "true"})
        self.deepgram = DeepgramClient(os.getenv("DEEPGRAM_API_KEY"), config)

    async def listen(self) -> str:
        """Écoute le micro et retourne la phrase finale."""
        transcription_complete = asyncio.Event()
        final_sentence = ""
        transcript_parts = []

        try:
            dg_connection = self.deepgram.listen.asynclive.v("1")

            async def on_message(self, result, **kwargs):
                nonlocal final_sentence
                sentence = result.channel.alternatives[0].transcript
                
                if not result.speech_final:
                    transcript_parts.append(sentence)
                else:
                    transcript_parts.append(sentence)
                    full = ' '.join(transcript_parts).strip()
                    if len(full) > 0:
                        final_sentence = full
                        transcript_parts.clear()
                        transcription_complete.set()

            dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)

            options = LiveOptions(
                model="nova-2", 
                punctuate=True, 
                language="multi", # 'multi' permet d'écouter plusieurs langues sans forcer
                encoding="linear16", 
                channels=1, 
                sample_rate=16000, 
                endpointing=300
            )

            await dg_connection.start(options)
            microphone = Microphone(dg_connection.send)
            microphone.start()
            
            print("\n🎤 [STT] Je vous écoute...")
            await transcription_complete.wait()

            microphone.finish()
            await dg_connection.finish()
            
            return final_sentence

        except Exception as e:
            print(f"❌ Erreur STT : {e}")
            return ""