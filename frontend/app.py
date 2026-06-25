"""py-shiny chat UI for the Azure deep research app.

Imports the backend in-process (no API). Flow: access-key gate -> clarifier chat (<=3 turns) ->
plan review (approve / edit) -> research run inside a Shiny ExtendedTask (non-blocking, with live
progress) -> wide report card -> email the report. Long runs are session-scoped: leaving or
refreshing the page loses the in-progress research (quick-demo posture).
"""

from __future__ import annotations

import logging
import threading

from deep_research import keystore
from deep_research.clarifier import clarify
from deep_research.email import is_valid_email, send_report_email
from deep_research.observability import setup_observability
from deep_research.pipeline import run_research
from deep_research.schemas import ResearchPlan
from shiny import App, reactive, render, ui

logger = logging.getLogger(__name__)

setup_observability()

app_ui = ui.page_fillable(
    ui.tags.style(
        ".dr-msg-user{background:#eef4ff;border-radius:.6rem;padding:.6rem .8rem;margin:.3rem 0}"
        ".dr-msg-bot{background:#f6f6f6;border-radius:.6rem;padding:.6rem .8rem;margin:.3rem 0}"
        ".dr-report{max-width:none}"
    ),
    ui.h2("🔎 Deep Research"),
    ui.output_ui("gate"),
    ui.output_ui("chat_area"),
    ui.output_ui("plan_area"),
    ui.output_ui("progress_area"),
    ui.output_ui("report_area"),
    fillable_mobile=True,
)


def _plan_to_text(plan: ResearchPlan) -> str:
    tasks = "\n".join(f"- {t}" for t in plan.tasks)
    return f"Objective: {plan.objective}\n\nTasks:\n{tasks}"


def server(input, output, session):  # noqa: ANN001
    # --- per-session state ---------------------------------------------------
    access_key = reactive.value("")
    phase = reactive.value("locked" if keystore.auth_enabled() else "clarify")
    history: reactive.Value[list[tuple[str, str]]] = reactive.value([])
    current_plan: reactive.Value[ResearchPlan | None] = reactive.value(None)
    report = reactive.value(None)
    thinking = reactive.value(False)

    # Progress is appended from the ExtendedTask thread; guard with a lock and poll to render.
    progress_lock = threading.Lock()
    progress_lines: list[str] = []

    def progress_cb(msg: str) -> None:
        with progress_lock:
            progress_lines.append(msg)

    def progress_reset() -> None:
        with progress_lock:
            progress_lines.clear()

    def progress_snapshot() -> list[str]:
        with progress_lock:
            return list(progress_lines)

    @reactive.extended_task
    async def research_task(plan: ResearchPlan):
        return await run_research(plan, progress=progress_cb)

    # --- access-key gate -----------------------------------------------------
    @render.ui
    def gate():
        if phase() != "locked":
            return None
        return ui.card(
            ui.card_header("Enter your access key"),
            ui.input_password("access_key_in", None, placeholder="access key"),
            ui.input_action_button("unlock", "Unlock", class_="btn-primary"),
            ui.p(ui.tags.small("Ask the administrator for a key (minted with utils/mint_key.py).")),
        )

    @reactive.effect
    @reactive.event(input.unlock)
    async def _unlock():
        key = (input.access_key_in() or "").strip()
        name = await keystore.validate_key(key)
        if name is None:
            ui.notification_show("Invalid access key.", type="error")
            return
        access_key.set(key)
        phase.set("clarify")

    # --- clarifier chat ------------------------------------------------------
    @render.ui
    def chat_area():
        if phase() not in ("clarify", "plan_review", "plan_edit"):
            return None
        bubbles = []
        if not history():
            bubbles.append(
                ui.div(
                    "Hi! Describe what you'd like me to research. I'll ask a couple of "
                    "clarifying questions, then propose a plan for you to approve.",
                    class_="dr-msg-bot",
                )
            )
        for role, content in history():
            cls = "dr-msg-user" if role == "user" else "dr-msg-bot"
            bubbles.append(ui.div(ui.markdown(content), class_=cls))
        if thinking():
            bubbles.append(ui.div(ui.tags.em("Clarifier is thinking…"), class_="dr-msg-bot"))

        composer = None
        if phase() == "clarify":
            composer = ui.div(
                ui.input_text_area(
                    "user_msg", None, placeholder="Type your message…", width="100%", rows=2
                ),
                ui.input_action_button("send", "Send", class_="btn-primary"),
            )
        return ui.card(ui.card_header("Conversation"), *bubbles, composer)

    @reactive.effect
    @reactive.event(input.send)
    async def _on_send():
        msg = (input.user_msg() or "").strip()
        if not msg:
            return
        hist = history() + [("user", msg)]
        history.set(hist)
        ui.update_text_area("user_msg", value="")
        thinking.set(True)
        try:
            turn = await clarify(hist)
        except Exception as exc:  # noqa: BLE001 - surface a friendly error
            thinking.set(False)
            ui.notification_show(f"Clarifier error: {exc}", type="error")
            return
        thinking.set(False)
        history.set(hist + [("assistant", turn.message)])
        if turn.plan_ready and turn.plan is not None:
            current_plan.set(turn.plan)
            phase.set("plan_review")

    # --- plan review (approve / edit) ---------------------------------------
    @render.ui
    def plan_area():
        plan = current_plan()
        if plan is None or phase() not in ("plan_review", "plan_edit"):
            return None
        if phase() == "plan_edit":
            return ui.card(
                ui.card_header("Edit the plan"),
                ui.input_text_area(
                    "plan_edit_in", None, value=_plan_to_text(plan), width="100%", rows=10
                ),
                ui.div(
                    ui.input_action_button("submit_edit", "Submit changes", class_="btn-primary"),
                    ui.input_action_button("cancel_edit", "Cancel"),
                ),
            )
        tasks = ui.tags.ol(*[ui.tags.li(t) for t in plan.tasks])
        return ui.card(
            ui.card_header("Proposed research plan"),
            ui.markdown(f"**Objective:** {plan.objective}"),
            ui.strong("Tasks:"),
            tasks,
            ui.div(
                ui.input_action_button("approve", "Approve & run", class_="btn-success"),
                ui.input_action_button("edit", "Edit plan"),
            ),
        )

    @reactive.effect
    @reactive.event(input.edit)
    def _edit():
        phase.set("plan_edit")

    @reactive.effect
    @reactive.event(input.cancel_edit)
    def _cancel_edit():
        phase.set("plan_review")

    @reactive.effect
    @reactive.event(input.submit_edit)
    async def _submit_edit():
        edited = (input.plan_edit_in() or "").strip()
        if not edited:
            return
        hist = history() + [("user", f"Here is my edited plan; please use it:\n\n{edited}")]
        history.set(hist)
        phase.set("clarify")
        thinking.set(True)
        try:
            turn = await clarify(hist)
        finally:
            thinking.set(False)
        history.set(hist + [("assistant", turn.message)])
        if turn.plan_ready and turn.plan is not None:
            current_plan.set(turn.plan)
            phase.set("plan_review")

    @reactive.effect
    @reactive.event(input.approve)
    async def _approve():
        plan = current_plan()
        if plan is None:
            return
        ok, _name, message = await keystore.consume_run(access_key())
        if not ok:
            ui.notification_show(message, type="warning")
            return
        progress_reset()
        report.set(None)
        phase.set("researching")
        research_task(plan)

    # --- research progress ---------------------------------------------------
    @render.ui
    def progress_area():
        if phase() != "researching":
            return None
        reactive.invalidate_later(0.8)
        lines = progress_snapshot() or ["Starting research…"]
        return ui.card(
            ui.card_header("Researching…"),
            ui.p(
                "⚠️ This can take several minutes. ",
                ui.strong("Leaving or refreshing this page will lose the in-progress research."),
            ),
            ui.tags.ul(*[ui.tags.li(line) for line in lines]),
        )

    @reactive.effect
    def _watch_research():
        status = research_task.status()
        if status == "success":
            report.set(research_task.result())
            phase.set("report")
        elif status == "error":
            phase.set("plan_review")
            # Surface the real exception (it's also captured in the OpenTelemetry traces).
            try:
                research_task.result()
                detail = "unknown error"
            except Exception as exc:  # noqa: BLE001 - show the cause to the user
                detail = f"{type(exc).__name__}: {exc}"
                logger.exception("Research run failed")
            ui.notification_show(f"Research failed: {detail}", type="error", duration=None)

    # --- report + email ------------------------------------------------------
    @render.ui
    def report_area():
        res = report()
        if res is None or phase() != "report":
            return None
        return ui.card(
            ui.card_header("Research report"),
            ui.div(ui.markdown(res.markdown), class_="dr-report"),
            ui.hr(),
            ui.h5("Email this report"),
            ui.div(
                ui.input_text("email_to", None, placeholder="name@example.com", width="320px"),
                ui.input_action_button("send_email", "Send as .md", class_="btn-primary"),
            ),
            ui.input_action_button("new_query", "Start a new query"),
            class_="dr-report",
        )

    @reactive.effect
    @reactive.event(input.send_email)
    async def _send_email():
        res = report()
        if res is None:
            return
        to = (input.email_to() or "").strip()
        if not is_valid_email(to):
            ui.notification_show("Enter a valid email address.", type="warning")
            return
        try:
            await send_report_email(to, res.markdown)
            ui.notification_show(f"Report sent to {to}.", type="message")
        except Exception as exc:  # noqa: BLE001
            ui.notification_show(f"Could not send email: {exc}", type="error")

    @reactive.effect
    @reactive.event(input.new_query)
    def _new_query():
        history.set([])
        current_plan.set(None)
        report.set(None)
        progress_reset()
        phase.set("clarify")


app = App(app_ui, server)
