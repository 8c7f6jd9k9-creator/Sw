"""Anonymous mutual-match questionnaire for two consenting adult partners."""

from __future__ import annotations

import random
from collections import defaultdict
from typing import Dict

import streamlit as st

from logic import ANSWER_LABELS, compare_answers
from questions import QUESTIONS

st.set_page_config(page_title="Совпадения пары", page_icon="💬", layout="centered")

QUESTION_BY_ID = {question["id"]: question for question in QUESTIONS}


def rerun() -> None:
    """Support both current and older Streamlit versions."""
    if hasattr(st, "rerun"):
        st.rerun()
    else:  # pragma: no cover - compatibility fallback
        st.experimental_rerun()


def clear_widget_values(prefix: str) -> None:
    """Remove hidden form values from Streamlit session state."""
    for key in list(st.session_state.keys()):
        if key.startswith(prefix):
            del st.session_state[key]


def reset_app() -> None:
    """Delete all temporary values from this browser session."""
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    rerun()


def initialize_state() -> None:
    if "phase" in st.session_state:
        return

    order = [question["id"] for question in QUESTIONS]
    random.SystemRandom().shuffle(order)
    st.session_state.phase = "intro"
    st.session_state.question_order = order
    st.session_state.partner1_answers = {}
    st.session_state.matches = []


def render_reset_button() -> None:
    with st.sidebar:
        st.markdown("### Управление")
        st.caption("Сброс удаляет временные ответы и результаты этой сессии.")
        if st.button("Удалить всё и начать заново", use_container_width=True):
            reset_app()


def render_questionnaire(partner_number: int) -> Dict[str, str] | None:
    prefix = f"partner_{partner_number}_"
    st.title(f"Партнер {partner_number}")
    st.write(
        "Отвечайте только за себя. Любой пункт можно пропустить. "
        "Ответы другого человека не будут показаны."
    )

    with st.form(key=f"form_partner_{partner_number}"):
        answers: Dict[str, str] = {}
        for index, question_id in enumerate(st.session_state.question_order, start=1):
            question = QUESTION_BY_ID[question_id]
            st.caption(f"{index} из {len(QUESTIONS)} · {question['category']}")
            answers[question_id] = st.radio(
                question["text"],
                options=list(ANSWER_LABELS.keys()),
                format_func=lambda value: ANSWER_LABELS[value],
                index=0,
                key=f"{prefix}{question_id}",
            )
            st.markdown("---")

        voluntary = st.checkbox(
            "Я отвечаю добровольно и понимаю, что совпадение — только повод для разговора, а не автоматическое согласие.",
            key=f"{prefix}voluntary",
        )
        submitted = st.form_submit_button("Скрыть ответы и продолжить", use_container_width=True)

    if not submitted:
        return None
    if not voluntary:
        st.error("Подтвердите добровольность ответов перед продолжением.")
        return None
    return answers


def show_intro() -> None:
    st.title("💬 Совпадения пары")
    st.write(
        "Два партнера проходят опрос по очереди на одном устройстве. "
        "В финале показываются только темы, по которым есть взаимный интерес."
    )
    st.info(
        "Опрос предназначен только для совершеннолетних людей, которые могут свободно "
        "согласиться или отказаться. Результат не заменяет отдельного разговора о границах."
    )
    st.caption(
        "Ответы не записываются в файл или базу данных. При размещении в интернете "
        "временные данные текущей сессии обрабатываются сервером приложения."
    )
    adults = st.checkbox(
        "Оба партнера совершеннолетние и проходят опрос добровольно.",
        key="adult_confirmation",
    )
    if st.button("Начать: партнер 1", disabled=not adults, use_container_width=True):
        st.session_state.phase = "partner1"
        rerun()


def show_partner1() -> None:
    answers = render_questionnaire(partner_number=1)
    if answers is None:
        return
    st.session_state.partner1_answers = answers
    st.session_state.phase = "handover"
    rerun()


def show_handover() -> None:
    clear_widget_values("partner_1_")
    st.title("🔒 Ответы первого партнера скрыты")
    st.write(
        "Передайте устройство второму партнеру. Индивидуальные ответы первого партнера "
        "не отображаются и будут удалены после сравнения."
    )
    if st.button("Я второй партнер: начать опрос", use_container_width=True):
        st.session_state.phase = "partner2"
        rerun()


def show_partner2() -> None:
    answers = render_questionnaire(partner_number=2)
    if answers is None:
        return
    st.session_state.matches = compare_answers(
        questions=QUESTIONS,
        question_order=st.session_state.question_order,
        first=st.session_state.partner1_answers,
        second=answers,
    )
    st.session_state.partner1_answers = {}
    st.session_state.phase = "results"
    rerun()


def show_results() -> None:
    clear_widget_values("partner_2_")
    st.title("✨ Только взаимные совпадения")
    matches = st.session_state.matches

    if not matches:
        st.write(
            "Совпадений не найдено. Это нормально: приложение намеренно не показывает, "
            "какие пункты выбрал каждый человек."
        )
    else:
        grouped: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
        for match in matches:
            grouped[match["category"]].append(match)
        for category, items in grouped.items():
            st.subheader(category)
            for item in items:
                st.markdown(f"**{item['text']}**")
                st.caption(item["summary"])
                st.markdown("---")

    st.warning(
        "Перед любым экспериментом отдельно обсудите границы, стоп-сигнал, здоровье, "
        "конфиденциальность и право отказаться в любой момент. Для форматов с другими "
        "людьми требуется явное согласие всех совершеннолетних участников."
    )
    if st.button("Полностью удалить результаты и начать заново", use_container_width=True):
        reset_app()


initialize_state()
render_reset_button()

phase = st.session_state.phase
if phase == "intro":
    show_intro()
elif phase == "partner1":
    show_partner1()
elif phase == "handover":
    show_handover()
elif phase == "partner2":
    show_partner2()
elif phase == "results":
    show_results()
else:  # pragma: no cover - defensive reset
    reset_app()
