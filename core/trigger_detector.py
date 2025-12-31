"""
Trigger detection for co-host responses.
Detects wake phrases and pause patterns.
"""


class TriggerDetector:
    def __init__(self, config: dict):
        triggers = config.get("triggers", {})
        self.wake_phrases = [p.lower() for p in triggers.get("wake_phrases", [])]
        self.silence_threshold_ms = triggers.get("silence_threshold_ms", 3000)
        self.min_words = triggers.get("min_words_before_response", 10)

    def check_wake_phrase(self, transcript: str) -> str | None:
        """
        Check if transcript contains a wake phrase.

        Returns:
            The detected wake phrase or None
        """
        if not transcript:
            return None

        lower = transcript.lower()

        for phrase in self.wake_phrases:
            if phrase in lower:
                return phrase

        return None

    def count_words(self, transcript: str) -> int:
        """Count words in transcript."""
        if not transcript:
            return 0
        return len(transcript.split())

    def should_respond(self, transcript: str, silence_ms: int) -> tuple[bool, str]:
        """
        Determine if the co-host should respond.

        Args:
            transcript: Current transcript text
            silence_ms: Milliseconds of silence detected

        Returns:
            Tuple of (should_respond, trigger_type)
            trigger_type is one of: "wake_phrase:X", "pause", or None
        """
        if not transcript:
            return False, ""

        # Check for wake phrase first (highest priority)
        wake = self.check_wake_phrase(transcript)
        if wake:
            return True, f"wake_phrase:{wake}"

        # Check pause after sufficient speech
        word_count = self.count_words(transcript)
        if word_count >= self.min_words and silence_ms >= self.silence_threshold_ms:
            return True, "pause"

        return False, ""
