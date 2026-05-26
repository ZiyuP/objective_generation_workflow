"""Streamlit web interface for the AutismGPT Lesson Creator."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

from autism_gpt import llm as llm_mod
from autism_gpt.exporters import excel as excel_exporter
from autism_gpt.schemas import LessonPackage
from autism_gpt.steps import (
    lesson_flow as lesson_flow_step,
    prompt_library as prompt_library_step,
    qa_review as qa_step,
    scenarios as scenario_step,
    system_prompt as system_prompt_step,
)

# ── Step registry ──────────────────────────────────────────────────────────

STEP_ORDER = ["idea", "script", "library", "sys_prompt", "scenarios", "qa", "export"]
STEP_LABELS = {
    "idea":       "1 · Enter Topic",
    "script":     "2 · Teaching Approach & Script",
    "library":    "3 · Prompt Library",
    "sys_prompt": "4 · System Prompt",
    "scenarios":  "5 · Practice Scenarios",
    "qa":         "6 · QA Review",
    "export":     "7 · Export & Download",
}

STEP_NEXT = {
    "idea":      "script",
    "script":    "library",
    "library":   "sys_prompt",
    "sys_prompt": "scenarios",
    "scenarios": "qa",
    "qa":        "export",
    "export":    None,
}

# Draft session-state key for each step that has one (used to clear on upstream revise)
STEP_DRAFT_KEY = {
    "script":     "draft_script",
    "sys_prompt": "draft_sys_prompt",
}

# ── Session state ──────────────────────────────────────────────────────────

def _init() -> None:
    defaults: dict = {
        "step": "idea",
        "package": LessonPackage(),
        "history": [],
        "idea_text": "",
        "draft_script": None,
        "library_entries": None,
        "library_is_fallback": False,
        "draft_sys_prompt": None,
        "user_reference_prompt": "",   # pasted by user in Step 3 (one-off, not saved to DB)
        "page": "lesson",              # "lesson" | "library_manager"
        "completed_steps": set(),      # steps approved at least once
        "approved": {},                # {step_name: bool}
        "revision_message": None,      # shown as st.success after revision
        "editing_prompt_id": None,     # which prompt is being edited in manager
        "confirm_delete_id": None,     # which prompt awaits delete confirm
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

# ── Navigation helpers ─────────────────────────────────────────────────────

def _is_completed(step: str) -> bool:
    return step in st.session_state.completed_steps


def _go_to(step: str) -> None:
    st.session_state.step = step
    st.rerun()


def _complete_step(step: str) -> None:
    """Mark step approved and advance to the next step."""
    st.session_state.completed_steps.add(step)
    st.session_state.approved[step] = True
    next_step = STEP_NEXT.get(step)
    if next_step:
        st.session_state.step = next_step
    st.rerun()


def _mark_revised(step: str, message: str) -> None:
    """After revision: mark downstream steps stale, store toast message.
    The current step stays in whatever approved state it had — the stale warning
    checks draft keys, not the approved flag, so self-revision never triggers it.
    """
    idx = STEP_ORDER.index(step)
    for s in STEP_ORDER[idx + 1:]:
        if s in st.session_state.approved:
            st.session_state.approved[s] = False
        # Clear the draft so the downstream page knows it must regenerate
        draft_key = STEP_DRAFT_KEY.get(s)
        if draft_key and st.session_state.get(draft_key) is not None:
            st.session_state[draft_key] = None
    st.session_state.revision_message = message

# ── DB helper ──────────────────────────────────────────────────────────────

def _get_db():
    from autism_gpt.library_db import PromptLibraryDB
    return PromptLibraryDB()

# ── Toast helper ───────────────────────────────────────────────────────────

def _show_revision_toast() -> None:
    if st.session_state.get("revision_message"):
        st.success(st.session_state.revision_message)
        st.session_state.revision_message = None

# ── Back button ────────────────────────────────────────────────────────────

def _back_button(to_step: str) -> None:
    if st.button(f"← Back to {STEP_LABELS[to_step]}", key=f"back_{to_step}"):
        _go_to(to_step)

# ── Shared UI ──────────────────────────────────────────────────────────────

def _feedback_row(key: str):
    reset_count = st.session_state.get(f"_fb_{key}_reset", 0)
    feedback = st.text_area(
        "Feedback for revision (leave blank to approve as-is)",
        key=f"fb_{key}_{reset_count}",
        placeholder="e.g. 'Make the hints shorter' or 'Use a different activity format'",
        height=90,
    )
    c1, c2 = st.columns(2)
    revise  = c1.button("↩ Revise",  key=f"rev_{key}",  disabled=not feedback.strip())
    approve = c2.button("✓ Approve & Continue", key=f"app_{key}", type="primary")
    return feedback, revise, approve


def _clear_feedback(key: str) -> None:
    st.session_state[f"_fb_{key}_reset"] = st.session_state.get(f"_fb_{key}_reset", 0) + 1

# ── Dialog rendering ───────────────────────────────────────────────────────

def _is_child(speaker: str) -> bool:
    return speaker.strip().lower() in ("child", "kid")


def _render_dialog(lines) -> None:
    for line in lines:
        if line.is_action:
            st.success(f"🎁 {line.text}")
        elif _is_child(line.speaker):
            with st.chat_message("user"):
                st.markdown(f"**{line.speaker}:** {line.text}")
        else:
            with st.chat_message("assistant"):
                st.markdown(f"**{line.speaker}:** {line.text}")

# ── Teaching approach + script rendering ───────────────────────────────────

def _render_approach_card(ss) -> None:
    with st.container(border=True):
        c1, c2 = st.columns(2)
        c1.markdown(f"**Skill Type**  \n{ss.skill_type}")
        c2.markdown(f"**Activity Format**  \n`{ss.activity_format}`")
        st.markdown(f"**What the child practices:** {ss.topic_summary}")
        st.info(f"**Why this approach:** {ss.teaching_rationale}")


def _render_script(ss) -> None:
    _render_approach_card(ss)
    st.markdown(f"### Sample Session Script — *{ss.lesson_title}*")

    with st.expander("**Intro**", expanded=True):
        _render_dialog(ss.intro)
    for rnd in ss.rounds:
        with st.expander(f"**Round {rnd.round_number}** — {rnd.round_label}", expanded=True):
            _render_dialog(rnd.dialog)

# ── Scenario rendering ─────────────────────────────────────────────────────

def _render_scenarios(scenarios) -> None:
    diff_icon = {"beginner": "🟢", "intermediate": "🟡", "advanced": "🔴"}
    for sc in scenarios:
        icon = diff_icon.get(sc.difficulty.lower(), "⚪")
        with st.expander(f"{icon} **{sc.scenario_id}** — {sc.title}"):
            st.markdown(f"**Setup:** {sc.setup}")
            st.info(f"**Nessa asks:** _{sc.nessa_prompt}_")
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Small hint** 💡")
                st.markdown(sc.small_hint)
                st.markdown("**Big hint** 💡💡")
                st.markdown(sc.big_hint)
            with c2:
                st.markdown("**Target response**")
                st.markdown(sc.target_response)
                st.markdown("**Example correct response**")
                st.markdown(f"_{sc.example_correct_response}_")
            if sc.tags:
                st.caption("Tags: " + " · ".join(sc.tags))


def _render_images(images) -> None:
    for img in images:
        with st.expander(f"🖼️ {img.scenario_id}"):
            st.markdown(f"**Child description:** _{img.child_description}_")
            st.caption(f"Style: {img.style}  |  Palette: {img.color_palette or '—'}")
            st.text_area("Image Generation Prompt", img.image_prompt,
                         height=90, key=f"img_{img.scenario_id}", disabled=True)
            st.markdown("**Key elements:** " + " · ".join(img.key_elements))


def _render_qa(qa) -> None:
    overall = "🟢 PASS" if qa.overall_pass else "🔴 FAIL"
    st.markdown(f"### Overall: {overall}")
    st.caption(qa.reviewer_notes)
    st.divider()
    all_items = (qa.prompt_quality + qa.scenario_clarity + qa.image_scenario_match
                 + qa.description_length + qa.tool_use_rules)
    by_cat: dict = {}
    for item in all_items:
        by_cat.setdefault(item.category, []).append(item)
    s_icon = {"pass": "✅", "fail": "❌", "warning": "⚠️"}
    for cat, items in by_cat.items():
        counts = {s: sum(1 for i in items if i.status.lower() == s) for s in ["pass", "fail", "warning"]}
        summary = f"✅ {counts['pass']}  ❌ {counts['fail']}  ⚠️ {counts['warning']}"
        with st.expander(f"**{cat}** — {summary}"):
            for item in items:
                st.markdown(f"{s_icon.get(item.status.lower(),'⚪')} **{item.item}**  \n{item.notes}")

# ── Sidebar ────────────────────────────────────────────────────────────────

def _sidebar() -> None:
    with st.sidebar:
        st.markdown("## 🧩 AutismGPT\nLesson Creator")
        st.divider()

        # Page switcher
        page_options = ["📝 Lesson Creator", "📚 Library Manager"]
        current_page_label = "📝 Lesson Creator" if st.session_state.page == "lesson" else "📚 Library Manager"
        selected = st.radio("Navigation", page_options, index=page_options.index(current_page_label),
                            label_visibility="collapsed")
        new_page = "lesson" if selected == "📝 Lesson Creator" else "library_manager"
        if new_page != st.session_state.page:
            st.session_state.page = new_page
            st.rerun()

        st.divider()

        if st.session_state.page == "lesson":
            # API key input
            if not os.environ.get("ANTHROPIC_API_KEY"):
                key = st.text_input("Anthropic API Key", type="password", placeholder="sk-ant-…")
                if key:
                    os.environ["ANTHROPIC_API_KEY"] = key
                    llm_mod._client = None
                else:
                    st.warning("Enter your API key to generate content.")
                st.divider()

            # Step progress
            st.markdown("**Progress**")
            current_step = st.session_state.step
            for step in STEP_ORDER:
                label = STEP_LABELS[step]
                is_comp = _is_completed(step)
                is_approved = st.session_state.approved.get(step, False)
                is_current = step == current_step

                if is_comp:
                    status_icon = "✅" if is_approved else "⚠️"
                    if st.button(f"{status_icon} {label}", key=f"nav_{step}",
                                 use_container_width=True):
                        _go_to(step)
                elif is_current:
                    st.markdown(f"▶️ **{label}**")
                else:
                    st.markdown(f"⬜ {label}")

            # Current lesson info
            ss = st.session_state.package.session_script
            if ss:
                st.divider()
                st.markdown(f"**Lesson:** {ss.lesson_title}")
                st.caption(f"Format: `{ss.activity_format}`")
                st.caption(f"ID: `{ss.lesson_id}`")

# ── Lesson pages ───────────────────────────────────────────────────────────

def _page_idea() -> None:
    st.title("🧩 AutismGPT Lesson Creator")
    st.markdown(
        "Enter any teaching topic. The agent will identify the skill type, "
        "choose the right teaching approach for autism, and draft a sample Nessa-child session script."
    )
    st.divider()
    with st.container(border=True):
        idea = st.text_area(
            "What do you want to teach?",
            height=100,
            placeholder=(
                "e.g.  'Curious Questions'  ·  'Saying goodbye'  ·  "
                "'Recognizing when a friend is upset'  ·  'Vocabulary: shapes and textures'"
            ),
            key="idea_input",
        )
        st.caption(
            "The agent adapts the teaching format to your topic. "
            "Vocabulary games, question practice, emotion scenarios, social roleplay — "
            "it picks the best fit."
        )
        if st.button("Brainstorm Teaching Approach →", type="primary", disabled=not idea.strip()):
            st.session_state.idea_text = idea.strip()
            st.session_state.draft_script = None
            _go_to("script")


def _page_script() -> None:
    _show_revision_toast()
    _back_button("idea")
    st.title("Step 2 — Teaching Approach & Session Script")
    st.caption(f'Topic: "{st.session_state.idea_text}"')

    # Stale content warning
    if _is_completed("script") and not st.session_state.approved.get("script", False):
        st.warning("⚠️ This script has been revised. Downstream steps may be stale.")

    st.divider()

    if st.session_state.draft_script is None:
        with st.spinner("Identifying skill type and brainstorming teaching approach…"):
            try:
                st.session_state.draft_script = lesson_flow_step.draft(
                    st.session_state.idea_text, st.session_state.history
                )
            except Exception as e:
                st.error(f"Generation failed: {e}")
                return

    _render_script(st.session_state.draft_script)
    st.divider()

    feedback, revise, approve = _feedback_row("script")

    if revise:
        with st.spinner("Revising…"):
            try:
                st.session_state.draft_script = lesson_flow_step.revise(
                    st.session_state.draft_script, feedback, st.session_state.history
                )
                _clear_feedback("script")
            except Exception as e:
                st.error(f"Revision failed: {e}")
                return
        _mark_revised("script", "The session script has been revised.")
        st.rerun()

    if approve:
        st.session_state.package.session_script = st.session_state.draft_script
        st.session_state.library_entries = None
        st.session_state.library_is_fallback = False
        _complete_step("script")


def _page_library() -> None:
    _show_revision_toast()
    _back_button("script")
    st.title("Step 3 — Prompt Library")
    st.caption("Retrieving past lessons to use as structural and style references.")
    st.divider()

    if st.session_state.library_entries is None:
        with st.spinner("Searching…"):
            entries, is_fallback = prompt_library_step.retrieve(
                st.session_state.package.session_script
            )
            st.session_state.library_entries = entries
            st.session_state.library_is_fallback = is_fallback

    entries = st.session_state.library_entries
    is_fallback = st.session_state.library_is_fallback

    # Always show usage policy prominently
    st.warning(
        "**Saved prompts may come from different objectives.** "
        "They are used only to reference prompt structure, tool call patterns "
        "(such as `get_scenario()`, `evaluate()`, `show_reward()`), "
        "Nessa's language style, hint and feedback style, safety rules, and formatting. "
        "They are **not** used to copy lesson content, scenario content, target skills, "
        "or any teaching flow that does not fit the current objective.",
        icon="📋",
    )

    if entries and is_fallback:
        st.warning(
            "No saved prompts found. Using sample fallback references — "
            "add your own prompts in Prompt Library Manager."
        )

        with st.expander("What the agent will extract from these references"):
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**✓ Reused (structure & style)**")
                st.markdown(
                    "- Prompt section structure\n"
                    "- Tool call patterns (`get_scenario()`, `evaluate()`, `show_reward()`)\n"
                    "- Nessa's sentence length and tone\n"
                    "- Hint sequencing patterns\n"
                    "- Praise formulas\n"
                    "- Safety and clarification rules\n"
                    "- Formatting conventions"
                )
            with c2:
                st.markdown("**✗ Ignored (objective-specific)**")
                st.markdown(
                    "- Skills or topics from the old lesson\n"
                    "- Scenario content or target words\n"
                    "- Teaching flow that doesn't fit this lesson\n"
                    "- Examples or language tied to the old subject"
                )

        for e in entries:
            with st.expander(f"📦 Sample Fallback *(not your saved prompt)*"):
                st.caption(
                    f"Original skill: {e.get('skill', '—')}  |  "
                    f"Tags: {', '.join(e.get('tags', []))}  |  "
                    f"⚠️ Content from this lesson will NOT be copied."
                )
                preview = e.get("system_prompt", "")
                st.text_area(
                    "Reference prompt (content ignored — structure/style/tools only)",
                    preview[:500] + ("…" if len(preview) > 500 else ""),
                    height=90, disabled=True, key=f"lib_{e.get('id', '')}",
                )

    elif entries and not is_fallback:
        st.success(f"Found {len(entries)} past lesson(s).")

        with st.expander("What the agent will extract from these references"):
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**✓ Reused (structure & style)**")
                st.markdown(
                    "- Prompt section structure\n"
                    "- Tool call patterns (`get_scenario()`, `evaluate()`, `show_reward()`)\n"
                    "- Nessa's sentence length and tone\n"
                    "- Hint sequencing patterns\n"
                    "- Praise formulas\n"
                    "- Safety and clarification rules\n"
                    "- Formatting conventions"
                )
            with c2:
                st.markdown("**✗ Ignored (objective-specific)**")
                st.markdown(
                    "- Skills or topics from the old lesson\n"
                    "- Scenario content or target words\n"
                    "- Teaching flow that doesn't fit this lesson\n"
                    "- Examples or language tied to the old subject"
                )

        for e in entries:
            with st.expander(f"📚 Your Saved Reference *(structure/style/tools only)*"):
                st.caption(
                    f"Skill type: {e.get('skill_type', '—')}  |  "
                    f"Tags: {', '.join(e.get('tags', []))}  |  "
                    f"⚠️ Content from this lesson will NOT be copied."
                )
                preview = e.get("system_prompt", "")
                st.text_area(
                    "Reference prompt (content ignored — structure/style/tools only)",
                    preview[:500] + ("…" if len(preview) > 500 else ""),
                    height=90, disabled=True, key=f"lib_{e.get('id', '')}",
                )

    else:
        st.info(
            "No saved prompts yet. Add prompts in Prompt Library Manager, "
            "or continue without references."
        )

    # ── Manual reference prompt ────────────────────────────────────────────
    st.divider()
    st.markdown("#### Paste a Reference Prompt (optional)")
    st.caption(
        "Paste any past system prompt here to use as an additional style and structure reference. "
        "Like the library entries above, it will be used **only** for prompt structure, "
        "tool call patterns, and Nessa's language style — not to copy lesson content."
    )

    pasted = st.text_area(
        "Past system prompt",
        value=st.session_state.user_reference_prompt,
        height=220,
        placeholder=(
            "Paste a previous Nessa system prompt here…\n\n"
            "e.g. You are Nessa, a friendly AI tutor. When the child starts the session, "
            "call get_scenario() to load the first item…"
        ),
        key="paste_ref_input",
    )

    rc1, rc2 = st.columns([1, 3])
    if rc1.button("💾 Save reference", key="save_ref",
                  disabled=not pasted.strip(),
                  help="Saves this prompt as a style reference for Step 4"):
        st.session_state.user_reference_prompt = pasted.strip()
        st.success("Reference saved. It will be used in Step 4.")

    if st.session_state.user_reference_prompt:
        if rc2.button("🗑 Clear reference", key="clear_ref"):
            st.session_state.user_reference_prompt = ""
            st.rerun()

    st.divider()
    if st.button("Continue to System Prompt →", type="primary"):
        st.session_state.draft_sys_prompt = None
        st.session_state.completed_steps.add("library")
        _go_to("sys_prompt")


def _page_sys_prompt() -> None:
    _show_revision_toast()
    _back_button("library")
    ss = st.session_state.package.session_script
    st.title("Step 4 — System Prompt")
    st.caption(
        f"Writing a fresh prompt for Nessa — **{ss.activity_format}** ({ss.skill_type}). "
        "Structure and style are borrowed from the library; all content comes from your lesson."
    )

    # Stale warning: only when upstream revised and cleared our draft
    if _is_completed("sys_prompt") and st.session_state.draft_sys_prompt is None:
        st.warning("⚠️ An earlier step was revised — regenerating a fresh system prompt.")

    st.divider()

    if st.session_state.draft_sys_prompt is None:
        # Merge user-pasted reference (if any) with library entries
        all_refs = list(st.session_state.library_entries or [])
        if st.session_state.user_reference_prompt:
            all_refs = [
                {
                    "id": "user_paste",
                    "title": "Your Pasted Reference",
                    "skill": "user-provided",
                    "tags": [],
                    "system_prompt": st.session_state.user_reference_prompt,
                }
            ] + all_refs

        with st.spinner("Creating system prompt…"):
            try:
                st.session_state.draft_sys_prompt = system_prompt_step.draft(
                    ss,
                    all_refs,
                    st.session_state.history,
                )
            except Exception as e:
                st.error(f"Generation failed: {e}")
                return

    if st.session_state.user_reference_prompt:
        with st.expander("📎 Your pasted reference *(structure/style/tools only)*"):
            st.caption("This prompt is used only to extract structural patterns and Nessa's style. Content is not copied.")
            st.code(st.session_state.user_reference_prompt, language="text")

    sp_edit_reset = st.session_state.get("_sp_edit_reset", 0)
    sp_edit_key = f"sp_edit_{sp_edit_reset}"
    st.text_area(
        "Nessa System Prompt *(editable — your changes are saved on Approve)*",
        value=st.session_state.draft_sys_prompt,
        height=420,
        key=sp_edit_key,
    )
    st.divider()

    feedback, revise, approve = _feedback_row("sys_prompt")

    if revise:
        with st.spinner("Revising…"):
            try:
                st.session_state.draft_sys_prompt = system_prompt_step.revise(
                    st.session_state.draft_sys_prompt, feedback, st.session_state.history
                )
                _clear_feedback("sys_prompt")
                # Reset the edit area so it shows the new LLM output
                st.session_state["_sp_edit_reset"] = sp_edit_reset + 1
            except Exception as e:
                st.error(f"Revision failed: {e}")
                return
        _mark_revised("sys_prompt", "The system prompt has been revised.")
        st.rerun()

    if approve:
        # Prefer the user's direct edits; fall back to the LLM draft
        final = st.session_state.get(sp_edit_key) or st.session_state.draft_sys_prompt
        st.session_state.draft_sys_prompt = final
        st.session_state.package.system_prompt = final
        _complete_step("sys_prompt")


def _page_scenarios() -> None:
    _show_revision_toast()
    _back_button("sys_prompt")
    ss  = st.session_state.package.session_script
    pkg = st.session_state.package
    st.title("Step 5 — Practice Scenarios")
    st.caption(
        f"Generating **{ss.activity_format}** scenarios for: _{ss.topic_summary}_"
    )
    st.divider()

    if not pkg.scenarios:
        with st.container(border=True):
            count = st.slider("Number of practice scenarios", 3, 12, 6)
            if st.button("Generate Practice Scenarios ✨", type="primary"):
                with st.spinner(f"Generating {count} scenarios for {ss.activity_format}…"):
                    try:
                        scens = scenario_step.create_scenarios(
                            ss, st.session_state.history, count
                        )
                        pkg.scenarios = scens
                    except Exception as e:
                        st.error(f"Scenario generation failed: {e}")
                        return
                with st.spinner("Generating image prompts…"):
                    try:
                        images = scenario_step.create_scenario_images(
                            pkg.scenarios, ss, st.session_state.history
                        )
                        pkg.scenario_images = images
                    except Exception as e:
                        st.error(f"Image generation failed: {e}")
                        return
                st.session_state.revision_message = "The lesson content package has been created."
                st.rerun()
        return

    st.success(f"✓ {len(pkg.scenarios)} scenarios and {len(pkg.scenario_images)} image prompts generated.")
    tab1, tab2 = st.tabs(["📝 Practice Scenarios", "🖼️ Image Prompts"])
    with tab1:
        _render_scenarios(pkg.scenarios)
    with tab2:
        _render_images(pkg.scenario_images)

    st.divider()
    c1, c2 = st.columns([3, 1])
    if c2.button("↩ Regenerate"):
        pkg.scenarios = []
        pkg.scenario_images = []
        st.session_state.revision_message = "The scenarios have been regenerated."
        st.rerun()
    if c1.button("Continue to QA Review →", type="primary"):
        _complete_step("scenarios")


def _page_qa() -> None:
    _show_revision_toast()
    _back_button("scenarios")
    st.title("Step 6 — QA Review")
    st.caption("Automated quality check across all lesson components.")
    st.divider()

    pkg = st.session_state.package
    if pkg.qa_review is None:
        with st.spinner("Running QA checklist…"):
            try:
                pkg.qa_review = qa_step.run(pkg, st.session_state.history)
            except Exception as e:
                st.error(f"QA failed: {e}")
                return

    _render_qa(pkg.qa_review)
    st.divider()

    c1, c2 = st.columns(2)
    if c1.button("↩ Re-run QA"):
        pkg.qa_review = None
        st.rerun()
    if c2.button("✓ Approve & Export →", type="primary"):
        _complete_step("qa")


def _page_export() -> None:
    _back_button("qa")
    st.title("Step 7 — Export & Download")
    st.success("🎉 Lesson package complete!")
    st.divider()

    pkg = st.session_state.package
    ss  = pkg.session_script

    if ss:
        c1, c2, c3, c4 = st.columns(4)
        short_title = ss.lesson_title[:22] + "…" if len(ss.lesson_title) > 22 else ss.lesson_title
        c1.metric("Lesson", short_title)
        c2.metric("Format", ss.activity_format)
        c3.metric("Scenarios", len(pkg.scenarios))
        c4.metric("QA", "PASS" if (pkg.qa_review and pkg.qa_review.overall_pass) else "FAIL")

    st.divider()

    lesson_id  = ss.lesson_id if ss else "lesson"
    excel_bytes = excel_exporter.export_bytes(pkg)

    md_lines = [
        "# Nessa System Prompt",
        "",
        f"**Lesson:** {ss.lesson_title if ss else 'Unknown'}",
        f"**Lesson ID:** {ss.lesson_id if ss else 'Unknown'}",
        f"**Skill Type:** {ss.skill_type if ss else '—'}",
        f"**Activity Format:** {ss.activity_format if ss else '—'}",
        "",
        "---",
        "",
        pkg.system_prompt or "",
    ]
    md_bytes = "\n".join(md_lines).encode("utf-8")

    c1, c2 = st.columns(2)
    with c1:
        with st.container(border=True):
            st.markdown("**📊 Excel Workbook**")
            st.caption("4 sheets: Session Script · Practice Scenarios · Scenario Image · QA Review")
            st.download_button(
                "📥 Download Excel",
                data=excel_bytes,
                file_name=f"{lesson_id}_package.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
    with c2:
        with st.container(border=True):
            st.markdown("**📄 System Prompt**")
            st.caption("Nessa's approved system prompt as Markdown")
            st.download_button(
                "📥 Download system_prompt.md",
                data=md_bytes,
                file_name="system_prompt.md",
                mime="text/markdown",
                use_container_width=True,
            )

    st.divider()
    with st.expander("Preview system_prompt.md"):
        st.code("\n".join(md_lines), language="markdown")

    st.divider()
    if st.button("🔄 Start New Lesson"):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

# ── Library Manager page ───────────────────────────────────────────────────

def _tab_all_prompts(db) -> None:
    entries = db.get_all()
    st.markdown(f"**Total prompts: {len(entries)}**")

    if not entries:
        st.info("No prompts saved yet. Use the Add Prompt or Bulk Add tabs.")
        return

    # Search filter
    search_query = st.text_input("Search by title or skill type", key="lib_search",
                                  placeholder="Filter prompts…")

    if search_query.strip():
        q = search_query.strip().lower()
        entries = [
            e for e in entries
            if q in e.get("title", "").lower() or q in e.get("skill_type", "").lower()
        ]

    if not entries:
        st.info("No prompts match your search.")
        return

    for entry in entries:
        entry_id = entry.get("id", "")
        with st.container(border=True):
            col1, col2 = st.columns([5, 1])
            with col1:
                st.markdown(f"**{entry.get('title', 'Untitled')}** — {entry.get('skill_type', '—')}")
                st.caption(
                    f"Created: {entry.get('created_at', '—')}  |  "
                    f"Updated: {entry.get('updated_at', '—')}"
                )
                # Tags as code badges
                tags = entry.get("tags", [])
                if tags:
                    tag_str = "  ".join(f"`{t}`" for t in tags)
                    st.markdown(tag_str)
                # Notes
                notes = entry.get("notes", "")
                if notes:
                    st.caption(notes)
                # System prompt preview
                preview = entry.get("system_prompt", "")
                st.caption(f"Prompt preview: {preview[:200]}{'…' if len(preview) > 200 else ''}")

            with col2:
                edit_btn = st.button("✏️ Edit", key=f"edit_{entry_id}")
                del_btn  = st.button("🗑 Delete", key=f"del_{entry_id}")

                if edit_btn:
                    st.session_state.editing_prompt_id = entry_id
                    st.session_state.confirm_delete_id = None
                    st.rerun()

                if del_btn:
                    st.session_state.confirm_delete_id = entry_id
                    st.session_state.editing_prompt_id = None
                    st.rerun()

            # Inline edit form
            if st.session_state.editing_prompt_id == entry_id:
                with st.form(key=f"edit_form_{entry_id}"):
                    st.markdown("**Edit Prompt**")
                    new_title    = st.text_input("Title", value=entry.get("title", ""))
                    new_obj      = st.text_input("Objective Type", value=entry.get("objective_type", ""))
                    new_skill    = st.text_input("Skill Type", value=entry.get("skill_type", ""))
                    new_tags     = st.text_input("Tags (comma-separated)",
                                                  value=", ".join(entry.get("tags", [])))
                    new_notes    = st.text_area("Notes", value=entry.get("notes", ""), height=80)
                    new_prompt   = st.text_area("System Prompt", value=entry.get("system_prompt", ""),
                                                 height=200)
                    save_col, cancel_col = st.columns(2)
                    save_edit   = save_col.form_submit_button("💾 Save")
                    cancel_edit = cancel_col.form_submit_button("Cancel")

                if save_edit:
                    db.update(entry_id, {
                        "title": new_title,
                        "objective_type": new_obj,
                        "skill_type": new_skill,
                        "tags": new_tags,
                        "notes": new_notes,
                        "system_prompt": new_prompt,
                    })
                    st.session_state.editing_prompt_id = None
                    st.success("Prompt updated.")
                    st.rerun()

                if cancel_edit:
                    st.session_state.editing_prompt_id = None
                    st.rerun()

            # Delete confirmation
            if st.session_state.confirm_delete_id == entry_id:
                st.warning(f"Are you sure you want to delete **{entry.get('title', 'this prompt')}**?")
                if st.button("Confirm Delete", key=f"confirm_del_{entry_id}", type="primary"):
                    db.delete(entry_id)
                    st.session_state.confirm_delete_id = None
                    st.success("Prompt deleted.")
                    st.rerun()


def _tab_add_prompt(db) -> None:
    with st.form("add_prompt_form"):
        title         = st.text_input("Title")
        objective_type = st.text_input("Objective Type")
        skill_type    = st.text_input("Skill Type")
        tags          = st.text_input("Tags (comma-separated)")
        notes         = st.text_area("Notes", height=80)
        system_prompt = st.text_area("System Prompt", height=300)
        submitted     = st.form_submit_button("💾 Save Prompt")

    if submitted:
        if not system_prompt.strip():
            st.error("System Prompt cannot be empty.")
        else:
            db.add({
                "title": title,
                "objective_type": objective_type,
                "skill_type": skill_type,
                "tags": tags,
                "notes": notes,
                "system_prompt": system_prompt,
            })
            st.success("Prompt saved successfully!")
            st.rerun()


def _tab_bulk_add(db) -> None:
    st.markdown(
        "Paste a JSON array. Each item needs at minimum a `system_prompt` field. "
        "Example format shown below."
    )

    example_json = json.dumps([
        {
            "title": "My Lesson Title",
            "objective_type": "Social Skills",
            "skill_type": "social communication",
            "tags": "greeting, peers, school",
            "notes": "Optional notes about this prompt",
            "system_prompt": "You are Nessa, a friendly AI tutor…"
        }
    ], indent=2)
    st.code(example_json, language="json")

    raw_json = st.text_area("Paste JSON array here", height=350, key="bulk_json_input")

    parsed_entries = None
    parse_error = None

    if st.button("Parse & Preview", key="parse_bulk"):
        if not raw_json.strip():
            st.error("Please paste a JSON array first.")
        else:
            try:
                parsed_entries = json.loads(raw_json.strip())
                if not isinstance(parsed_entries, list):
                    parse_error = "Input must be a JSON array (list)."
                    parsed_entries = None
                else:
                    st.session_state["_bulk_parsed"] = parsed_entries
                    st.session_state["_bulk_error"] = None
            except json.JSONDecodeError as exc:
                parse_error = str(exc)
                st.session_state["_bulk_parsed"] = None
                st.session_state["_bulk_error"] = parse_error

    # Retrieve stored parse state
    parsed_entries = st.session_state.get("_bulk_parsed")
    parse_error = st.session_state.get("_bulk_error")

    if parse_error:
        st.error(f"JSON parse error: {parse_error}")

    if parsed_entries is not None:
        st.success(f"Parsed {len(parsed_entries)} entries. Preview:")
        preview_data = [
            {
                "title": e.get("title", ""),
                "skill_type": e.get("skill_type", ""),
                "system_prompt_preview": e.get("system_prompt", "")[:80],
            }
            for e in parsed_entries
        ]
        st.dataframe(preview_data, use_container_width=True)

        if st.button("Import All", key="import_bulk", type="primary"):
            added = db.bulk_add(parsed_entries)
            st.success(f"Imported {len(added)} prompts successfully.")
            st.session_state["_bulk_parsed"] = None
            st.session_state["_bulk_error"] = None
            st.rerun()


def _page_library_manager() -> None:
    st.title("📚 Prompt Library Manager")
    st.caption("Manage your saved Nessa system prompts used as structural and style references.")
    st.divider()

    db = _get_db()
    tab1, tab2, tab3 = st.tabs(["📋 All Prompts", "➕ Add Prompt", "📦 Bulk Add"])

    with tab1:
        _tab_all_prompts(db)

    with tab2:
        _tab_add_prompt(db)

    with tab3:
        _tab_bulk_add(db)

# ── Router ─────────────────────────────────────────────────────────────────

_PAGES = {
    "idea":       _page_idea,
    "script":     _page_script,
    "library":    _page_library,
    "sys_prompt": _page_sys_prompt,
    "scenarios":  _page_scenarios,
    "qa":         _page_qa,
    "export":     _page_export,
}


def main() -> None:
    st.set_page_config(
        page_title="AutismGPT Lesson Creator",
        page_icon="🧩",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _init()
    _sidebar()

    if st.session_state.page == "library_manager":
        _page_library_manager()
    else:
        # lesson page
        if st.session_state.step != "idea" and not os.environ.get("ANTHROPIC_API_KEY"):
            st.error("An Anthropic API key is required. Enter it in the sidebar.")
            st.stop()
        _PAGES[st.session_state.step]()


if __name__ == "__main__":
    main()
