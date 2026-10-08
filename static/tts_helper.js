
// EDGE TTS AUDIO PLAYER
async function playEdgeTTS(text) {
    try {
        const cleanText = text.replace(/[*_#✨💖🌸☕️💡👤]/g, '').trim();
        if (!cleanText) return;

        const response = await fetch('/api/voice/tts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: cleanText, voice: 'ru-RU-SvetlanaNeural' })
        });

        if (!response.ok) {
            console.warn('TTS request failed:', response.status);
            return;
        }

        const blob = await response.blob();
        const audioUrl = URL.createObjectURL(blob);
        const audio = new Audio(audioUrl);
        audio.play().catch(e => console.warn('Audio play blocked:', e));
    } catch (e) {
        console.warn('Edge TTS error:', e);
    }
}
