"""CLI orchestrator — human-in-the-loop vocabulary lesson creation."""
from __future__ import annotations

import sys
from typing import Any, Dict, List

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.rule import Rule
from rich.table import Table

from .exporters import excel as excel_exporter
from .exporters import markdown as md_exporter
from .schemas import LessonPackage
from .steps import (
    lesson_flow as lesson_flow_step,
    prompt_library as prompt_library_step,
    qa_review as qa_step,
    scenarios as scenario_step,
    system_prompt as system_prompt_step,
)


class LessonCreationAgent:
    def __init__(self):
        self.console = Console()
        self.package = LessonPackage()
        self.history: List[Dict[str, Any]] = []

    def _step(self, n: int, title: str) -> None:
        self.console.print()
        self.console.print(Rule(f"[bold blue]Step {n}: {title}[/bold blue]"))

    def _choice(self) -> str:
        self.console.print("\n[bold]Options:[/bold]  [green]a[/green] Approve  [yellow]f[/yellow] Feedback  [red]q[/red] Quit")
        return Prompt.ask(">", choices=["a", "f", "q"], default="a")

    def _push(self, role: str, content: str) -> None:
        self.history.append({"role": role, "content": content})

    # ── Script rendering ───────────────────────────────────────────────────

    def _print_script(self, ss) -> None:
        self.console.print(f"\n[bold]{ss.lesson_title}[/bold]  ([dim]{ss.lesson_id}[/dim])")
        self.console.print(f"Demo word: [cyan]{', '.join(ss.target_words)}[/cyan]\n")

        self.console.print("[bold underline]Intro[/bold underline]")
        for line in ss.intro:
            self._print_line(line)

        for rnd in ss.rounds:
            self.console.print(f"\n[bold underline]Round {rnd.round_number}: {rnd.round_label}[/bold underline]")
            for line in rnd.dialog:
                self._print_line(line)

    def _print_line(self, line) -> None:
        if line.is_action:
            self.console.print(f"  [bold yellow]🎁 {line.text}[/bold yellow]")
        elif line.speaker == "Bot":
            self.console.print(f"  [blue]Bot:[/blue] {line.text}")
        else:
            self.console.print(f"  [green]Kid:[/green] {line.text}")

    # ── Step handlers ──────────────────────────────────────────────────────

    def _run_session_script(self, idea: str) -> None:
        self.console.print("[dim]Drafting session script…[/dim]")
        script = lesson_flow_step.draft(idea, self.history)
        self._push("user", f"Draft session script for: {idea}")

        while True:
            self._print_script(script)
            choice = self._choice()
            if choice == "a":
                self.package.session_script = script
                self._push("assistant", script.model_dump_json())
                self.console.print("[green]✓ Session script approved.[/green]")
                return
            elif choice == "f":
                feedback = Prompt.ask("[yellow]Feedback[/yellow]")
                self._push("user", feedback)
                self.console.print("[dim]Revising…[/dim]")
                script = lesson_flow_step.revise(script, feedback, self.history)
                self._push("assistant", script.model_dump_json())
            else:
                sys.exit(0)

    def _retrieve_library(self) -> List[dict]:
        self.console.print("[dim]Searching prompt library…[/dim]")
        entries, is_fallback = prompt_library_step.retrieve(self.package.session_script)
        if is_fallback:
            self.console.print("[dim]No saved prompts found. Using sample fallback references.[/dim]")
        if entries:
            t = Table(title="Similar Prompts Found", show_lines=True)
            t.add_column("Title", style="cyan"); t.add_column("Skill"); t.add_column("Tags")
            for e in entries:
                t.add_row(e.get("title",""), e.get("skill",""), ", ".join(e.get("tags",[])))
            self.console.print(t)
        else:
            self.console.print("[dim]No similar prompts found.[/dim]")
        return entries

    def _run_system_prompt(self, library_entries: List[dict]) -> None:
        self.console.print("[dim]Creating system prompt…[/dim]")
        sp = system_prompt_step.draft(self.package.session_script, library_entries, self.history)
        self._push("user", "Create system prompt")

        while True:
            self.console.print(Panel(sp, title="[cyan]System Prompt[/cyan]", expand=False))
            choice = self._choice()
            if choice == "a":
                self.package.system_prompt = sp
                self._push("assistant", sp)
                self.console.print("[green]✓ System prompt approved.[/green]")
                return
            elif choice == "f":
                feedback = Prompt.ask("[yellow]Feedback[/yellow]")
                self._push("user", feedback)
                self.console.print("[dim]Revising…[/dim]")
                sp = system_prompt_step.revise(sp, feedback, self.history)
                self._push("assistant", sp)
            else:
                sys.exit(0)

    def _run_content_package(self) -> None:
        count = int(Prompt.ask("How many vocabulary words?", default="6"))

        self.console.print("[dim]Generating practice scenarios…[/dim]")
        vocab = scenario_step.create_scenarios(self.package.session_script, self.history, count)
        self.package.scenarios = vocab
        self._push("assistant", "[" + ",".join(s.model_dump_json() for s in vocab) + "]")

        t = Table(title=f"{len(vocab)} Practice Scenarios", show_lines=True)
        t.add_column("ID", style="cyan"); t.add_column("Title"); t.add_column("Difficulty")
        for s in vocab:
            t.add_row(s.scenario_id, s.title, s.difficulty)
        self.console.print(t)

        self.console.print("[dim]Generating image prompts…[/dim]")
        images = scenario_step.create_scenario_images(vocab, self.package.session_script, self.history)
        self.package.scenario_images = images
        self.console.print(f"[green]✓ {len(images)} image prompts created.[/green]")

    def _run_qa(self) -> None:
        self.console.print("[dim]Running QA checklist…[/dim]")
        qa = qa_step.run(self.package, self.history)
        self.package.qa_review = qa

        t = Table(title="QA Review", show_lines=True)
        t.add_column("Category"); t.add_column("Item"); t.add_column("Status"); t.add_column("Notes")
        all_items = qa.prompt_quality + qa.scenario_clarity + qa.image_scenario_match + qa.description_length + qa.tool_use_rules
        colors = {"pass": "green", "fail": "red", "warning": "yellow"}
        for item in all_items:
            c = colors.get(item.status.lower(), "white")
            t.add_row(item.category, item.item, f"[{c}]{item.status.upper()}[/{c}]", item.notes)
        self.console.print(t)

        overall_c = "green" if qa.overall_pass else "red"
        self.console.print(f"\n[bold]Overall: [{overall_c}]{'PASS' if qa.overall_pass else 'FAIL'}[/{overall_c}][/bold]")
        self.console.print(f"Notes: {qa.reviewer_notes}")

        if Confirm.ask("\nApprove and re-export with QA sheet?", default=True):
            self._export()
            self.console.print("[green]✓ QA approved and files updated.[/green]")

    def _export(self) -> None:
        excel_path = excel_exporter.export(self.package)
        md_path = md_exporter.export(self.package)
        self.console.print(Panel(
            f"[green]✓ Excel:[/green]         {excel_path}\n"
            f"[green]✓ System prompt:[/green] {md_path}",
            title="[bold green]Export Complete[/bold green]",
        ))

    # ── Main ───────────────────────────────────────────────────────────────

    def run(self) -> None:
        self.console.print(Panel(
            "[bold]AutismGPT Lesson Creation Agent[/bold]\n"
            "Word Mystery Game — vocabulary lesson workflow",
            style="blue",
        ))

        self._step(1, "Session Script")
        idea = Prompt.ask(
            "[bold]Describe your vocabulary lesson idea[/bold]\n"
            "(e.g. 'science vocabulary about shapes and textures for grade 3')"
        )
        self._run_session_script(idea)

        self._step(2, "Prompt Library Retrieval")
        library_entries = self._retrieve_library()

        self._step(3, "System Prompt")
        self._run_system_prompt(library_entries)

        self._step(4, "Vocabulary Words + Images")
        self._run_content_package()

        self._step(5, "Export")
        self._export()

        self._step(6, "QA Review")
        self._run_qa()

        self.console.print(Panel("[bold green]Workflow complete![/bold green]", style="green"))
