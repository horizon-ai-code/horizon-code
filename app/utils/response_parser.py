import re
import json
from typing import Type, TypeVar, Optional, Any
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

class ResponseParser:
    @staticmethod
    def extract_xml(text: Optional[str], tag: str) -> Optional[str]:
        """Extracts content between XML-style tags and performs basic syntax validation for Java."""
        if text is None:
            return None
        # Strip thinking blocks first
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
        
        # Strip preamble before first <code> tag (for model that talks before generating)
        if tag == "code":
            first = text.find(f"<{tag}")
            if first > 0:
                text = text[first:]
        
        pattern = rf"<{tag}\b[^>]*>(.*?)</{tag}>"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        
        if match:
            content = match.group(1).strip()
            # Basic Java syntax validation if it's a 'code' tag
            if tag == "code":
                if len(content) < 5 or ("{" not in content and ";" not in content):
                    return None
            return content
        return None

    @staticmethod
    def extract_json(text: Optional[str], model: Type[T]) -> T:
        """Extracts and validates JSON from text, even if wrapped in markdown blocks."""
        if text is None:
            raise ValueError("Cannot extract JSON from None")
            
        # Strip thinking blocks
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
        
        # Look for json code blocks
        json_block_pattern = r"```json\s*(.*?)\s*```"
        match = re.search(json_block_pattern, text, re.DOTALL | re.IGNORECASE)
        
        json_str = ""
        if match:
            json_str = match.group(1).strip()
        else:
            # Try to find the first '{' and last '}'
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1:
                json_str = text[start:end+1].strip()
            else:
                raise ValueError("No JSON found in response")

        # Strip single-line comments (//...) that break JSON parsing
        json_str = re.sub(r'//.*$', '', json_str, flags=re.MULTILINE)

        # Fix Python-isms (None -> null, True -> true, False -> false)
        # We use word boundaries to avoid replacing parts of strings
        json_str = re.sub(r'\bNone\b', 'null', json_str)
        json_str = re.sub(r'\bTrue\b', 'true', json_str)
        json_str = re.sub(r'\bFalse\b', 'false', json_str)

        # Proactively remove trailing commas before closing braces/brackets
        cleaned_json = re.sub(r",\s*([\]}])", r"\1", json_str)
        return model.model_validate_json(cleaned_json)

    @staticmethod
    def parse_guaranteed(text: Optional[str], tag: str, model: Optional[Type[T]] = None) -> Any:
        """
        Tries to extract XML first, then JSON if model is provided.
        Falls back to raw text (minus thinking) if nothing else works.
        """
        if text is None:
            return ""
            
        # 1. Try XML
        xml_content = ResponseParser.extract_xml(text, tag)
        if xml_content:
            if model:
                try:
                    return ResponseParser.extract_json(xml_content, model)
                except:
                    return xml_content # Return raw XML content if JSON parse fails
            return xml_content

        # 2. Try JSON directly in the text if model provided
        if model:
            try:
                return ResponseParser.extract_json(text, model)
            except:
                pass

        # 3. Fallback: Return text without thoughts
        return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE).strip()
