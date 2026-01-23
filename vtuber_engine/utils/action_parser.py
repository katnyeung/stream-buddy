"""
Action Parser - Extracts action tags from LLM output text.

Tag format: [type:name] or [type:name,param:value,param2:value2]
Types: mood, gesture, action, eye, head, body, brow

Example:
    Input:  "[mood:happy] Hello there! [head:nod] How are you? [eye:wink]"
    Output: {
        "clean_text": "Hello there! How are you?",
        "actions": [
            {"type": "mood", "name": "happy", "params": {}, "position": 0},
            {"type": "head", "name": "nod", "params": {}, "position": 14},
            {"type": "eye", "name": "wink", "params": {}, "position": 28}
        ]
    }
"""
import re
from typing import Dict, List, Optional, Any
from dataclasses import dataclass


@dataclass
class ParsedAction:
    """A single parsed action from text."""
    type: str
    name: str
    params: Dict[str, Any]
    position: int
    delay_ms: int = 0  # Delay based on text position


class ActionParser:
    """
    Parser for extracting action tags from LLM output.
    Ported from JavaScript action-parser.js.
    """

    # Match [type:name] or [type:name,key:value,key2:value2]
    TAG_PATTERN = re.compile(r'\[(\w+):(\w+)(?:,([^\]]+))?\]')

    def __init__(self):
        pass

    def parse(self, text: str) -> Dict[str, Any]:
        """
        Parse text and extract action tags.

        Args:
            text: Raw text with embedded tags

        Returns:
            Dict with clean_text and actions list
        """
        if not text or not isinstance(text, str):
            return {"clean_text": text or "", "actions": []}

        actions = []
        offset = 0

        for match in self.TAG_PATTERN.finditer(text):
            full_match = match.group(0)
            action_type = match.group(1).lower()
            name = match.group(2).lower()
            params_str = match.group(3)

            # Parse optional parameters
            params = self._parse_params(params_str)

            actions.append(ParsedAction(
                type=action_type,
                name=name,
                params=params,
                position=match.start() - offset
            ))

            offset += len(full_match)

        # Remove all tags from text
        clean_text = self.TAG_PATTERN.sub('', text).strip()
        # Clean up extra spaces
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()

        return {
            "clean_text": clean_text,
            "actions": [
                {"type": a.type, "name": a.name, "params": a.params, "position": a.position, "delay_ms": a.delay_ms}
                for a in actions
            ]
        }

    def _parse_params(self, params_str: Optional[str]) -> Dict[str, Any]:
        """
        Parse comma-separated key:value pairs.

        Args:
            params_str: e.g., "intensity:0.8,duration:1.2"

        Returns:
            Dict of parameters
        """
        if not params_str:
            return {}

        params = {}
        pairs = params_str.split(',')

        for pair in pairs:
            parts = pair.split(':')
            if len(parts) >= 2:
                key = parts[0].strip().lower()
                value = parts[1].strip()

                # Try to parse as number
                try:
                    params[key] = float(value)
                except ValueError:
                    params[key] = value

        return params

    def has_actions(self, text: str) -> bool:
        """Quick check if text contains any action tags."""
        if not text:
            return False
        return bool(self.TAG_PATTERN.search(text))

    def strip_tags(self, text: str) -> str:
        """Strip all action tags from text."""
        if not text:
            return ""
        result = self.TAG_PATTERN.sub('', text)
        return re.sub(r'\s+', ' ', result).strip()

    def parse_with_timing(self, text: str, ms_per_char: int = 60) -> Dict[str, Any]:
        """
        Parse text and estimate timing based on character count before each tag.

        Args:
            text: Raw text with embedded tags
            ms_per_char: Milliseconds per character (~60ms = 150 wpm)

        Returns:
            Dict with clean_text and actions with delay_ms
        """
        if not text or not isinstance(text, str):
            return {"clean_text": text or "", "actions": []}

        actions = []
        clean_text = ""
        last_index = 0
        char_count = 0

        for match in self.TAG_PATTERN.finditer(text):
            # Count clean text characters before this tag
            text_before = text[last_index:match.start()]
            clean_before = re.sub(r'\s+', ' ', text_before)
            char_count += len(clean_before)
            clean_text += clean_before

            full_match = match.group(0)
            action_type = match.group(1).lower()
            name = match.group(2).lower()
            params_str = match.group(3)

            params = self._parse_params(params_str)

            actions.append(ParsedAction(
                type=action_type,
                name=name,
                params=params,
                position=match.start(),
                delay_ms=int(char_count * ms_per_char)
            ))

            last_index = match.end()

        # Add remaining text
        clean_text += text[last_index:]
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()

        return {
            "clean_text": clean_text,
            "actions": [
                {"type": a.type, "name": a.name, "params": a.params, "position": a.position, "delay_ms": a.delay_ms}
                for a in actions
            ]
        }
