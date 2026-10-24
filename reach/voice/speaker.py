"""`say` / `ask_user` backends."""

from __future__ import annotations

from typing import Protocol


class Speaker(Protocol):
    def say(self, message: str) -> None: ...

    def ask_user(self, question: str) -> str | None:
        """Returns the user's answer, or None if they did not respond."""
        ...


class ConsoleSpeaker:
    def say(self, message: str) -> None:
        print(f"[Reach] {message}")

    def ask_user(self, question: str) -> str | None:
        answer = input(f"[Reach] {question} > ").strip()
        return answer or None


class ScriptedSpeaker:
    """Records what Reach says and answers questions from a queue (None = silence)."""

    def __init__(self, answers: list[str | None] | None = None) -> None:
        self.answers = list(answers or [])
        self.said: list[str] = []
        self.asked: list[str] = []

    def say(self, message: str) -> None:
        self.said.append(message)

    def ask_user(self, question: str) -> str | None:
        self.asked.append(question)
        return self.answers.pop(0) if self.answers else None
