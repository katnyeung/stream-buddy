"""
Co-host brain using Google Gemini for response generation.
"""
import os
from google import genai
from google.genai import types

client = None


def get_client():
    global client
    if client is None:
        client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
    return client


class CohostBrain:
    def __init__(self, config: dict):
        self.persona = config.get("persona", {})
        self.name = self.persona.get("name", "Buddy")
        self.system_prompt = self.persona.get(
            "system_prompt",
            "You are a friendly AI co-host. Be supportive and brief."
        )
        self.conversation_history: list[str] = []

    def add_to_history(self, speaker: str, text: str) -> None:
        """Add an exchange to conversation history."""
        self.conversation_history.append(f"{speaker}: {text}")
        # Keep last 10 exchanges
        if len(self.conversation_history) > 10:
            self.conversation_history = self.conversation_history[-10:]

    async def generate_response(self, context: str, trigger_type: str) -> str:
        """
        Generate a co-host response using Gemini.

        Args:
            context: Recent transcript from streamer
            trigger_type: How the response was triggered (pause, wake_phrase:X)

        Returns:
            Generated response text
        """
        if not context or not context.strip():
            return ""

        client = get_client()

        # Build prompt with context
        history_text = "\n".join(self.conversation_history[-5:]) if self.conversation_history else ""

        prompt = f"""{self.system_prompt}

Recent conversation:
{history_text}

The streamer just said: "{context}"

Trigger: {trigger_type}

Respond as {self.name}, the co-host. Keep it brief (1-2 sentences max). Be natural and conversational. Add value to what they said or ask a relevant follow-up."""

        try:
            response = client.models.generate_content(
                model="gemini-2.0-flash-exp",
                contents=prompt,
                config=types.GenerateContentConfig(
                    max_output_tokens=100,
                    temperature=0.7,
                )
            )

            result = response.text.strip()

            # Add to history
            self.add_to_history("Streamer", context)
            self.add_to_history(self.name, result)

            return result

        except Exception as e:
            print(f"Gemini error: {e}")
            return ""

    def clear_history(self) -> None:
        """Clear conversation history."""
        self.conversation_history = []
