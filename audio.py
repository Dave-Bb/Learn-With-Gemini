"""
Audio capture (microphone) and playback (speaker) for Learn With Gemini.
Uses pyaudio with async queues for integration with the Gemini session.
"""

import asyncio
import pyaudio

FORMAT = pyaudio.paInt16
CHANNELS = 1
MIC_RATE = 16000
SPEAKER_RATE = 24000
CHUNK_SIZE = 1024


class AudioManager:
    def __init__(self):
        self.pya = pyaudio.PyAudio()
        self.mic_queue = asyncio.Queue(maxsize=50)
        self.speaker_queue = asyncio.Queue()
        self._mic_stream = None
        self._speaker_stream = None
        self._running = False

    def start(self):
        """Open mic and speaker streams. Safe to call multiple times."""
        if self._running:
            return
        mic_info = self.pya.get_default_input_device_info()
        self._mic_stream = self.pya.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=MIC_RATE,
            input=True,
            input_device_index=mic_info["index"],
            frames_per_buffer=CHUNK_SIZE,
        )
        self._speaker_stream = self.pya.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=SPEAKER_RATE,
            output=True,
        )
        self._running = True

    def stop(self):
        """Close audio streams and terminate pyaudio."""
        self._running = False
        try:
            if self._mic_stream:
                self._mic_stream.stop_stream()
                self._mic_stream.close()
                self._mic_stream = None
            if self._speaker_stream:
                self._speaker_stream.stop_stream()
                self._speaker_stream.close()
                self._speaker_stream = None
            self.pya.terminate()
        except Exception:
            pass

    async def capture_mic(self):
        """Continuously read mic data into the queue."""
        while self._running:
            data = await asyncio.to_thread(
                self._mic_stream.read, CHUNK_SIZE, exception_on_overflow=False
            )
            # Drop oldest if queue is full (avoid blocking)
            if self.mic_queue.full():
                try:
                    self.mic_queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            await self.mic_queue.put(data)

    async def play_speaker(self):
        """Continuously play audio chunks from the speaker queue."""
        while self._running:
            chunk = await self.speaker_queue.get()
            await asyncio.to_thread(self._speaker_stream.write, chunk)

    def queue_audio(self, data: bytes):
        """Add audio data to the speaker playback queue."""
        self.speaker_queue.put_nowait(data)

    def clear_playback(self):
        """Clear the speaker queue (e.g. on interruption)."""
        while not self.speaker_queue.empty():
            try:
                self.speaker_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
