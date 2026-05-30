"""Pure comparison logic for the questionnaire."""

from __future__ import annotations

from typing import Iterable, Mapping, Sequence

ANSWER_LABELS: dict[str, str] = {
    "skip": "Предпочитаю не отвечать",
    "no": "Не интересно",
    "talk": "Только обсудить или оставить фантазией",
    "maybe": "Возможно попробовать при подходящих условиях",
    "yes": "Есть интерес попробовать",
}

ANSWER_LEVELS: dict[str, int] = {
    "skip": -1,
    "no": 0,
    "talk": 1,
    "maybe": 2,
    "yes": 3,
}


def common_interest_label(level: int) -> str:
    """Return a deliberately non-specific shared-interest summary."""
    if level == 1:
        return "Совпало как тема для разговора или фантазия"
    if level == 2:
        return "Можно осторожно обсудить возможный эксперимент"
    return "Есть взаимный интерес попробовать"


def compare_answers(
    questions: Sequence[Mapping[str, str]],
    question_order: Iterable[str],
    first: Mapping[str, str],
    second: Mapping[str, str],
) -> list[dict[str, str]]:
    """
    Return only mutual matches.

    A skipped answer or a negative answer from either partner suppresses the
    question entirely. Results include the lower shared level and never expose
    either person's individual answer.
    """
    questions_by_id = {question["id"]: question for question in questions}
    matches: list[dict[str, str]] = []

    for question_id in question_order:
        first_level = ANSWER_LEVELS.get(first.get(question_id, "skip"), -1)
        second_level = ANSWER_LEVELS.get(second.get(question_id, "skip"), -1)

        if first_level <= 0 or second_level <= 0:
            continue

        question = questions_by_id[question_id]
        matches.append(
            {
                "category": question["category"],
                "text": question["text"],
                "summary": common_interest_label(min(first_level, second_level)),
            }
        )

    return matches
