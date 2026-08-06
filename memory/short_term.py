"""
memory/short_term.py

Wraps the existing rolling message buffer (mcp_server.py: store_message /
get_chat_history) and adds a scratchpad that survives buffer pruning.

The scratchpad is DELIBERATELY kept separate from the message buffer:
pruning the transcript (handled by the server) must never wipe out
what the agent is actively working on.
"""

import sys
import os

# Let this file import directly from mcp_server/, since memory/ and
# mcp_server/ are siblings inside the same repo.
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "mcp_server"))

from server import store_message, get_chat_history

class Scratchpad:
    """
    Holds the agent's current working state for one session:
    who the student is, what they're asking about, what to do next.

    This is intentionally NOT part of the message buffer, so trimming
    old messages never erases it.
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._state = {
            "student_id": None,
            "current_topic": None,
            "next_step": None,
        }

    def update(self, **kwargs) -> None:
        """Update one or more fields, e.g. update(current_topic='drop request')"""
        for key, value in kwargs.items():
            if key not in self._state:
                raise ValueError(f"Unknown scratchpad field: {key}")
            self._state[key] = value

    def get(self) -> dict:
        return dict(self._state)  # return a copy, not the live dict

    def clear(self) -> None:
        """Reset the scratchpad — e.g. when a topic is fully resolved."""
        self._state = {
            "student_id": None,
            "current_topic": None,
            "next_step": None,
        }

class ShortTermMemory:
    """
    Combines the existing server-side rolling buffer (messages table)
    with a scratchpad for the agent's current working state.

    One instance = one session. The buffer and scratchpad share the
    same session_id, but are stored and pruned completely independently.
    """

    def __init__(self, session_id: str, student_id: int = None):
        self.session_id = session_id
        self.student_id = student_id
        self.scratchpad = Scratchpad(session_id)

    def add_message(self, role: str, content: str) -> dict:
        """
        Adds a message to the rolling buffer via the existing server tool.
        This buffer can be pruned at any time (server handles that) —
        the scratchpad is untouched either way.
        """
        return store_message(
            session_id=self.session_id,
            role=role,
            content=content,
            student_id=self.student_id,
        )

    def get_recent_messages(self, limit: int = 20) -> list:
        """Fetches the current (possibly pruned) buffer from the server."""
        result = get_chat_history(session_id=self.session_id, limit=limit)
        if result["status"] != "success":
            return []
        return result["messages"]

    def update_scratchpad(self, **kwargs) -> None:
        self.scratchpad.update(**kwargs)

    def get_scratchpad(self) -> dict:
        return self.scratchpad.get()

    def get_full_state(self) -> dict:
        """
        Convenience method: what does the agent 'currently know' —
        both the recent transcript AND its working state.
        Useful for debugging / feeding into router or consolidation later.
        """
        return {
            "session_id": self.session_id,
            "recent_messages": self.get_recent_messages(),
            "scratchpad": self.get_scratchpad(),
        }

if __name__ == "__main__":
    stm = ShortTermMemory(session_id="test_session_1", student_id=7)

    stm.update_scratchpad(
        student_id=7,
        current_topic="drop request CS101",
        next_step="check re-enrollment eligibility"
    )

    
    for i in range(25):
        stm.add_message(role="user", content=f"filler message number {i}")

    print("Scratchpad after buffer overflow:", stm.get_scratchpad())
    print("Recent messages count:", len(stm.get_recent_messages()))