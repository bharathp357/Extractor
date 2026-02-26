"""
Storage module - Saves conversations as text files.
Each conversation gets its own timestamped text file.
"""
import os
import json
import time
from datetime import datetime
import config


class ConversationStorage:
    """Manages saving and loading conversations as text files."""

    def __init__(self, storage_dir: str = None):
        self.storage_dir = storage_dir or config.CONVERSATIONS_DIR
        os.makedirs(self.storage_dir, exist_ok=True)

    def _generate_filename(self, prompt: str) -> str:
        """Generate a unique filename based on timestamp and prompt snippet."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Clean prompt for filename (first 40 chars)
        clean = "".join(c if c.isalnum() or c == " " else "" for c in prompt[:40])
        clean = clean.strip().replace(" ", "_")[:30]
        return f"{timestamp}_{clean}.txt"

    def save_conversation(self, prompt: str, response: str, metadata: dict = None) -> str:
        """
        Save a single prompt-response pair to a text file.

        Returns:
            Path to the saved file.
        """
        filename = self._generate_filename(prompt)
        filepath = os.path.join(self.storage_dir, filename)

        content = []
        provider = (metadata or {}).get("provider", "unknown")
        content.append("=" * 70)
        content.append(f"  AI COMMAND CENTER — CONVERSATION LOG")
        content.append(f"  Provider: {provider}")
        content.append(f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        content.append("=" * 70)
        content.append("")
        content.append("-" * 70)
        content.append("  PROMPT:")
        content.append("-" * 70)
        content.append(prompt)
        content.append("")
        content.append("-" * 70)
        content.append("  RESPONSE:")
        content.append("-" * 70)
        content.append(response)
        content.append("")

        if metadata:
            content.append("-" * 70)
            content.append("  METADATA:")
            content.append("-" * 70)
            for key, value in metadata.items():
                content.append(f"  {key}: {value}")
            content.append("")

        content.append("=" * 70)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(content))

        print(f"[+] Conversation saved: {filename}")
        self._prune(max_keep=10)
        return filepath

    def save_session(self, conversations: list) -> str:
        """
        Save a full session (multiple prompts/responses) to a single file.

        Args:
            conversations: List of dicts with 'prompt', 'response', 'timestamp'

        Returns:
            Path to the saved file.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"session_{timestamp}.txt"
        filepath = os.path.join(self.storage_dir, filename)

        content = []
        content.append("=" * 70)
        content.append(f"  AI COMMAND CENTER — SESSION LOG")
        content.append(f"  Session Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        content.append(f"  Total Exchanges: {len(conversations)}")
        content.append("=" * 70)
        content.append("")

        for i, conv in enumerate(conversations, 1):
            content.append(f"╔{'═' * 68}╗")
            content.append(f"║  Exchange #{i}  |  {conv.get('timestamp', 'N/A')}")
            content.append(f"╚{'═' * 68}╝")
            content.append("")
            content.append("  >> PROMPT:")
            content.append(conv.get("prompt", ""))
            content.append("")
            content.append("  << RESPONSE:")
            content.append(conv.get("response", ""))
            content.append("")
            content.append("")

        content.append("=" * 70)
        content.append("  END OF SESSION")
        content.append("=" * 70)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(content))

        print(f"[+] Session saved: {filename}")
        return filepath

    def _prune(self, max_keep: int = 10):
        """Keep only the most recent `max_keep` conversation files."""
        files = sorted(
            (f for f in os.listdir(self.storage_dir) if f.endswith(".txt")),
            reverse=True,
        )
        for old in files[max_keep:]:
            try:
                os.remove(os.path.join(self.storage_dir, old))
                print(f"[+] Pruned old conversation: {old}")
            except OSError:
                pass

    def list_conversations(self) -> list:
        """List all saved conversation files."""
        files = []
        for f in sorted(os.listdir(self.storage_dir), reverse=True):
            if f.endswith(".txt"):
                filepath = os.path.join(self.storage_dir, f)
                stat = os.stat(filepath)
                files.append({
                    "filename": f,
                    "filepath": filepath,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                })
        return files

    def read_conversation(self, filename: str) -> str:
        """Read the contents of a saved conversation file."""
        filepath = os.path.join(self.storage_dir, filename)
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                return f.read()
        return ""

    def delete_conversation(self, filename: str) -> bool:
        """Delete a conversation file."""
        filepath = os.path.join(self.storage_dir, filename)
        if os.path.exists(filepath):
            os.remove(filepath)
            print(f"[+] Deleted: {filename}")
            return True
        return False


# Singleton
_storage = None

def get_storage() -> ConversationStorage:
    """Get or create the singleton storage instance."""
    global _storage
    if _storage is None:
        _storage = ConversationStorage()
    return _storage
