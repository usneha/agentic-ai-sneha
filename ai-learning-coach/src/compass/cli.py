"""CLI entrypoint for AI Builder Compass."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from . import __version__
from .config import ACTIVE_LEARNER_FILE, COMPASS_HOME, LEARNERS_DIR
from .models import LearnerProfile, LearnerState, SkillScore

console = Console()


# ── Active learner helpers ────────────────────────────────────────────────────

def get_active_learner_id() -> str | None:
    if ACTIVE_LEARNER_FILE.exists():
        return ACTIVE_LEARNER_FILE.read_text().strip() or None
    return None


def set_active_learner_id(learner_id: str) -> None:
    COMPASS_HOME.mkdir(parents=True, exist_ok=True)
    ACTIVE_LEARNER_FILE.write_text(learner_id)


def resolve_learner_id(learner_id_opt: str | None) -> str:
    lid = learner_id_opt or get_active_learner_id()
    if not lid:
        console.print(
            "[red]No active learner. Run [bold]compass init[/bold] first.[/red]"
        )
        sys.exit(1)
    return lid


# ── Learner ID generation ─────────────────────────────────────────────────────

def make_learner_id(name: str) -> str:
    base = re.sub(r"[^a-z0-9-]", "", name.lower().strip().replace(" ", "-"))
    if not base:
        base = "learner"
    if not (LEARNERS_DIR / base).exists():
        return base
    for i in range(2, 100):
        candidate = f"{base}-{i}"
        if not (LEARNERS_DIR / candidate).exists():
            return candidate
    import uuid
    return f"{base}-{uuid.uuid4().hex[:6]}"


# ── Skill graph initialization ────────────────────────────────────────────────

def build_initial_skill_graph(background: str) -> dict[str, SkillScore]:
    from . import _data
    seeded = _data.pre_seeded_scores(background)
    graph: dict[str, SkillScore] = {}
    for skill_id in _data.all_skill_ids() + _data.all_foundation_skill_ids():
        base = seeded.get(skill_id, 0.0)
        graph[skill_id] = SkillScore(
            skill_id=skill_id,
            score=0.0,
            base_score=base,
            confidence="low",
            evidence_sources=[],
        )
    return graph


# ── CLI group ─────────────────────────────────────────────────────────────────

@click.group()
@click.version_option(version=__version__, prog_name="compass")
def cli() -> None:
    """AI Builder Compass — personalized AI learning roadmap."""


# ── compass init ──────────────────────────────────────────────────────────────

@cli.command()
@click.option("--name", prompt="Your name", help="Your name (used as learner ID).")
@click.option(
    "--background",
    type=click.Choice(
        ["software_engineer", "data_scientist", "ml_engineer", "product_manager"],
        case_sensitive=False,
    ),
    help="Your current background.",
)
@click.option(
    "--depth",
    type=click.Choice(["awareness", "practitioner", "expert"], case_sensitive=False),
    help="Target learning depth.",
)
@click.option(
    "--style",
    type=click.Choice(["build_first", "concept_first", "balanced"], case_sensitive=False),
    help="How you prefer to learn.",
)
@click.option("--github-username", default="", help="Your GitHub username (optional).")
def init(
    name: str,
    background: str | None,
    depth: str | None,
    style: str | None,
    github_username: str,
) -> None:
    """Create a new learner profile."""
    from .memory.store import save_state

    console.print()
    console.print(Panel.fit("AI Builder Compass — Setup", style="bold blue"))
    console.print()

    # Warn if overwriting
    existing = get_active_learner_id()
    if existing:
        console.print(f"[yellow]Active learner: [bold]{existing}[/bold][/yellow]")
        if not click.confirm("Create a new learner profile?", default=False):
            console.print("Aborted.")
            return
        console.print()

    # Interactive prompts for any fields not passed as flags
    if not background:
        console.print("Your current background:")
        console.print("  [cyan]1[/cyan]  Software Engineer")
        console.print("  [cyan]2[/cyan]  Data Scientist")
        console.print("  [cyan]3[/cyan]  Machine Learning Engineer")
        console.print("  [cyan]4[/cyan]  Product Manager")
        choice = click.prompt("Choice", type=click.IntRange(1, 4))
        background = {
            1: "software_engineer",
            2: "data_scientist",
            3: "ml_engineer",
            4: "product_manager",
        }[choice]
        console.print()

    if not depth:
        console.print("Target depth:")
        console.print("  [cyan]1[/cyan]  Awareness      — understand what's possible")
        console.print("  [cyan]2[/cyan]  Practitioner   — build end-to-end AI applications")
        console.print("  [cyan]3[/cyan]  Expert         — production patterns, advanced techniques")
        choice = click.prompt("Choice", type=click.IntRange(1, 3))
        depth = {1: "awareness", 2: "practitioner", 3: "expert"}[choice]
        console.print()

    if not style:
        console.print("How do you prefer to learn?")
        console.print("  [cyan]1[/cyan]  Build first    — dive into projects, learn by doing")
        console.print("  [cyan]2[/cyan]  Concept first  — understand before building")
        console.print("  [cyan]3[/cyan]  Balanced       — a bit of both")
        choice = click.prompt("Choice", type=click.IntRange(1, 3))
        style = {1: "build_first", 2: "concept_first", 3: "balanced"}[choice]
        console.print()

    if not github_username:
        github_username = click.prompt(
            "GitHub username (optional, press Enter to skip)", default="", show_default=False
        )

    # Build profile
    learner_id = make_learner_id(name)
    profile = LearnerProfile(
        learner_id=learner_id,
        name=name,
        github_username=github_username or None,
        background=background,
        desired_depth=depth,
        learning_style=style,
    )

    # Pre-seed skill graph
    skill_graph = build_initial_skill_graph(background)
    seeded_count = sum(1 for s in skill_graph.values() if s.score > 0)
    total_skills = len(skill_graph)

    state = LearnerState(profile=profile, skill_graph=skill_graph)
    save_state(state)
    set_active_learner_id(learner_id)

    console.print()
    console.print(f"[green]✓[/green] Profile created: [bold]{learner_id}[/bold]")
    console.print(
        f"[green]✓[/green] Skill graph initialized "
        f"({total_skills} skills, {seeded_count} pre-seeded for [bold]{background}[/bold])"
    )
    console.print(
        f"[green]✓[/green] State saved to [dim]data/learners/{learner_id}/[/dim]"
    )
    console.print()
    console.print(
        "[dim]Next step:[/dim] Run [bold]compass scan --repo <path>[/bold] "
        "to scan a local repository."
    )


# ── compass status ─────────────────────────────────────────────────────────────

@cli.command()
@click.option("--learner-id", default=None, help="Learner ID (defaults to active learner).")
@click.option("--all-skills", is_flag=True, default=False, help="Show all 44 skills instead of domain summaries.")
def status(learner_id: str | None, all_skills: bool) -> None:
    """Show current learner state and skill graph."""
    from .memory.store import load_state, list_learners
    from . import _data

    lid = resolve_learner_id(learner_id)
    state = load_state(lid)
    if state is None:
        console.print(f"[red]Learner [bold]{lid}[/bold] not found.[/red]")
        sys.exit(1)

    p = state.profile
    _print_header(p)

    if all_skills:
        _print_all_skills(state)
    else:
        _print_domain_summary(state)

    _print_foundation_summary(state)
    _print_evidence_summary(state)
    _print_milestone_status(state)


def _print_header(p: LearnerProfile) -> None:
    bg_labels = {
        "software_engineer": "Software Engineer",
        "data_scientist": "Data Scientist",
        "ml_engineer": "ML Engineer",
        "product_manager": "Product Manager",
    }
    console.print()
    console.print(
        Panel(
            f"[bold]{p.name}[/bold]  ·  "
            f"{bg_labels[p.background]} → {p.target_role.replace('_', ' ').title()}\n"
            f"Depth: [bold]{p.desired_depth}[/bold]  ·  "
            f"Style: [bold]{p.learning_style}[/bold]  ·  "
            f"ID: [dim]{p.learner_id}[/dim]",
            title="AI Builder Compass",
            title_align="left",
            style="blue",
            expand=False,
        )
    )


def _score_bar(score: float, width: int = 10) -> str:
    filled = round(score * width)
    return "█" * filled + "░" * (width - filled)


def _confidence_color(confidence: str) -> str:
    return {"low": "dim", "medium": "yellow", "high": "green"}[confidence]


def _domain_confidence(scores: list[SkillScore]) -> str:
    """Aggregate confidence: any high → high if most are; any low → low."""
    if not scores:
        return "low"
    counts = {"high": 0, "medium": 0, "low": 0}
    for s in scores:
        counts[s.confidence] += 1
    if counts["high"] > len(scores) / 2:
        return "high"
    if counts["low"] > len(scores) / 2:
        return "low"
    return "medium"


def _print_domain_summary(state: LearnerState) -> None:
    from . import _data

    table = Table(
        box=box.SIMPLE,
        show_header=True,
        header_style="bold",
        padding=(0, 1),
    )
    table.add_column("Domain", style="bold", min_width=34)
    table.add_column("Progress", min_width=12, justify="left")
    table.add_column("Score", justify="right", min_width=5)
    table.add_column("Conf.", min_width=6)
    table.add_column("Skills", justify="right", min_width=7)

    domain_list = _data.domains()
    sg = state.skill_graph

    for d in domain_list:
        sub_ids = [s["id"] for s in _data.sub_skills_by_domain(d["id"])]
        scores_in_domain = [sg[sid] for sid in sub_ids if sid in sg]
        if not scores_in_domain:
            continue

        avg = sum(s.effective_score for s in scores_in_domain) / len(scores_in_domain)
        conf = _domain_confidence(scores_in_domain)
        evidenced = sum(1 for s in scores_in_domain if s.score > 0)
        total = len(scores_in_domain)

        conf_color = _confidence_color(conf)
        table.add_row(
            d["name"],
            f"[cyan]{_score_bar(avg)}[/cyan]",
            f"{avg:.2f}",
            f"[{conf_color}]{conf}[/{conf_color}]",
            f"{evidenced}/{total}",
        )

    console.print()
    console.print(table)


def _print_all_skills(state: LearnerState) -> None:
    from . import _data

    domain_list = _data.domains()
    sg = state.skill_graph

    for d in domain_list:
        table = Table(
            title=d["name"],
            box=box.SIMPLE,
            show_header=True,
            header_style="bold",
            padding=(0, 1),
        )
        table.add_column("Skill", min_width=30)
        table.add_column("Evidence", justify="right", min_width=8)
        table.add_column("Assumed", justify="right", min_width=8)
        table.add_column("Effective", justify="right", min_width=9)
        table.add_column("Conf.", min_width=6)

        for sub in _data.sub_skills_by_domain(d["id"]):
            sid = sub["id"]
            s = sg.get(sid)
            if not s:
                continue
            conf_color = _confidence_color(s.confidence)
            assumed_str = f"[dim]+{s.base_score:.2f}[/dim]" if s.base_score > 0 else "[dim]—[/dim]"
            table.add_row(
                sub["name"],
                f"{s.score:.2f}",
                assumed_str,
                f"{s.effective_score:.2f}",
                f"[{conf_color}]{s.confidence}[/{conf_color}]",
            )
        console.print()
        console.print(table)


def _print_foundation_summary(state: LearnerState) -> None:
    from . import _data

    fdomains = _data.foundation_domains()
    sg = state.skill_graph
    has_any = any(
        sg.get(sub["id"]) and sg[sub["id"]].score > 0
        for d in fdomains for sub in d["sub_skills"]
    )
    if not has_any:
        return

    table = Table(
        title="Foundation Skills",
        box=box.SIMPLE,
        show_header=True,
        header_style="bold",
        padding=(0, 1),
    )
    table.add_column("Skill", min_width=28)
    table.add_column("Score", justify="right", min_width=6)
    table.add_column("Credits AI Skills", min_width=30, style="dim")

    credit_map = _data.foundation_credit_map()

    for fdom in fdomains:
        for sub in fdom["sub_skills"]:
            sid = sub["id"]
            s = sg.get(sid)
            if not s or s.score == 0:
                continue
            credits = credit_map.get(sid, {})
            credits_str = "  ".join(
                f"{ai_id.split('.')[-1]} +{boost:.2f}" for ai_id, boost in credits.items()
            )
            conf_color = _confidence_color(s.confidence)
            table.add_row(
                sub["name"],
                f"[{conf_color}]{s.score:.2f}[/{conf_color}]",
                credits_str or "—",
            )

    console.print()
    console.print(table)


def _print_evidence_summary(state: LearnerState) -> None:
    repos = state.github_cache.repos if state.github_cache else []
    journal_count = len(state.journal_entries)
    console.print(
        f"[dim]Evidence:[/dim]  "
        f"{len(repos)} repo{'s' if len(repos) != 1 else ''} scanned  ·  "
        f"{journal_count} journal entr{'ies' if journal_count != 1 else 'y'}"
    )


# ── compass scan ──────────────────────────────────────────────────────────────

@cli.command()
@click.argument("repo_path", default=".", metavar="REPO", type=click.Path(exists=True, file_okay=False))
@click.option("--learner-id", default=None, help="Learner ID (defaults to active learner).")
def scan(repo_path: str, learner_id: str | None) -> None:
    """Scan a local repository for learning evidence.

    REPO defaults to the current directory.
    """
    import time
    from pathlib import Path as _Path
    from .evidence.scanner import scan_repo
    from .memory.store import load_state, save_state
    from .models import GitHubCache
    from . import _data

    lid = resolve_learner_id(learner_id)
    state = load_state(lid)
    if state is None:
        console.print(f"[red]Learner [bold]{lid}[/bold] not found. Run [bold]compass init[/bold] first.[/red]")
        return

    repo = _Path(repo_path).resolve()
    console.print()
    console.print(f"Scanning [bold]{repo}[/bold] …")

    t0 = time.time()
    result = scan_repo(repo)
    elapsed = time.time() - t0

    # Persist raw signals in github_cache so compass assess can use them
    cache = state.github_cache or GitHubCache()
    if result.repo_name not in cache.repos:
        cache.repos.append(result.repo_name)
    cache.latest_signals = result.signals
    cache.files_scanned = result.files_scanned
    cache.scan_errors = result.errors
    from .models import _now
    cache.last_scan = _now()
    state.github_cache = cache
    save_state(state)

    # Print results
    console.print(
        f"\n[green]✓[/green] {result.files_scanned} files scanned in [bold]{elapsed:.2f}s[/bold]"
    )

    if result.errors:
        console.print(f"[yellow]Warnings:[/yellow] {len(result.errors)} pattern errors (run with --verbose to see)")

    foundation_ids = set(_data.all_foundation_skill_ids())
    ai_signals = [s for s in result.signals if s.skill_id not in foundation_ids]
    foundation_signals = [s for s in result.signals if s.skill_id in foundation_ids]

    if not ai_signals and not foundation_signals:
        console.print("\n[yellow]No learning evidence found in this repo.[/yellow]")
        console.print("[dim]This may mean the repo doesn't contain AI/ML code yet, or patterns didn't match.[/dim]")
        return

    # Foundation skills section
    if foundation_signals:
        level_rank = {"github_strong": 3, "github_moderate": 2, "github_weak": 1}
        best_f: dict[str, object] = {}
        for sig in foundation_signals:
            existing = best_f.get(sig.skill_id)
            if existing is None or level_rank[sig.signal_type] > level_rank[existing.signal_type]:  # type: ignore[union-attr]
                best_f[sig.skill_id] = sig

        ftable = Table(
            title="Foundation Skills Detected",
            box=box.SIMPLE, show_header=True, header_style="bold", padding=(0, 1),
        )
        ftable.add_column("Skill", min_width=26)
        ftable.add_column("Evidence", min_width=10)
        ftable.add_column("Credits AI Skills", min_width=30, style="dim")

        level_style = {"github_strong": "green bold", "github_moderate": "yellow", "github_weak": "dim"}
        level_label = {"github_strong": "STRONG", "github_moderate": "moderate", "github_weak": "weak"}
        credit_map = _data.foundation_credit_map()
        fmeta = {
            sub["id"]: sub["name"]
            for d in _data.foundation_domains()
            for sub in d["sub_skills"]
        }

        for sig in sorted(best_f.values(), key=lambda s: s.skill_id):  # type: ignore[union-attr]
            lvl = sig.signal_type  # type: ignore[union-attr]
            credits = credit_map.get(sig.skill_id, {})  # type: ignore[union-attr]
            credits_str = "  ".join(
                f"{ai_id.split('.')[-1]} +{boost:.2f}"
                for ai_id, boost in credits.items()
            )
            ftable.add_row(
                fmeta.get(sig.skill_id, sig.skill_id),  # type: ignore[union-attr]
                f"[{level_style.get(lvl, '')}]{level_label.get(lvl, lvl)}[/{level_style.get(lvl, '')}]",
                credits_str or "—",
            )
        console.print()
        console.print(ftable)

    if not ai_signals:
        console.print(
            f"\n[dim]{len(foundation_signals)} foundation signal(s) detected  ·  "
            f"0 AI skill signals  ·  Run [bold]compass assess[/bold] to apply.[/dim]"
        )
        return

    # AI skills section
    level_rank = {"github_strong": 3, "github_moderate": 2, "github_weak": 1}
    best: dict[str, object] = {}
    for sig in ai_signals:
        existing = best.get(sig.skill_id)
        if existing is None or level_rank[sig.signal_type] > level_rank[existing.signal_type]:  # type: ignore[union-attr]
            best[sig.skill_id] = sig

    # Group by domain
    domain_map = _data.skill_domain_map()
    domain_names = {d["id"]: d["name"] for d in _data.domains()}
    by_domain: dict[str, list] = {}
    for sig in sorted(best.values(), key=lambda s: (domain_map.get(s.skill_id, ""), s.skill_id)):  # type: ignore[union-attr]
        dom = domain_map.get(sig.skill_id, "other")  # type: ignore[union-attr]
        by_domain.setdefault(dom, []).append(sig)

    table = Table(box=box.SIMPLE, show_header=True, header_style="bold", padding=(0, 1))
    table.add_column("Domain", style="bold", min_width=16)
    table.add_column("Skill", min_width=26)
    table.add_column("Best Level", min_width=8)

    level_style = {"github_strong": "green bold", "github_moderate": "yellow", "github_weak": "dim"}
    level_label = {"github_strong": "STRONG", "github_moderate": "moderate", "github_weak": "weak"}

    for dom_id, sigs in by_domain.items():
        first = True
        for sig in sigs:
            dom_display = domain_names.get(dom_id, dom_id) if first else ""
            first = False
            skill_name = _skill_name(sig.skill_id)  # type: ignore[union-attr]
            lvl = sig.signal_type  # type: ignore[union-attr]
            table.add_row(
                dom_display,
                skill_name,
                f"[{level_style.get(lvl, '')}]{level_label.get(lvl, lvl)}[/{level_style.get(lvl, '')}]",
            )

    console.print()
    console.print(table)

    ai_signal_set = set(ai_signals)
    strong = len({s.skill_id for s in ai_signals if s.signal_type == "github_strong"})
    moderate_set = {s.skill_id for s in ai_signals if s.signal_type == "github_moderate"}
    strong_set = {s.skill_id for s in ai_signals if s.signal_type == "github_strong"}
    weak_set = {s.skill_id for s in ai_signals if s.signal_type == "github_weak"}
    moderate = len(moderate_set - strong_set)
    weak = len(weak_set - moderate_set - strong_set)
    total = len(best)

    console.print(
        f"[dim]{total} skills evidenced  ·  "
        f"[green]{strong} strong[/green]  ·  "
        f"[yellow]{moderate} moderate[/yellow]  ·  "
        f"{weak} weak[/dim]"
    )
    console.print()
    console.print("[dim]Run [bold]compass assess[/bold] to apply these signals to your skill graph.[/dim]")


# ── compass assess ────────────────────────────────────────────────────────────

@cli.command()
@click.option("--learner-id", default=None, help="Learner ID (defaults to active learner).")
def assess(learner_id: str | None) -> None:
    """Apply scan evidence to the skill graph."""
    from .competency.assessor import apply_signals
    from .memory.store import load_state, save_state

    lid = resolve_learner_id(learner_id)
    state = load_state(lid)
    if state is None:
        console.print(f"[red]Learner [bold]{lid}[/bold] not found.[/red]")
        return

    if not state.github_cache or not state.github_cache.latest_signals:
        console.print(
            "[yellow]No scan results found. Run [bold]compass scan --repo <path>[/bold] first.[/yellow]"
        )
        return

    signals = state.github_cache.latest_signals
    console.print(
        f"\nApplying [bold]{len(signals)}[/bold] signals to skill graph…"
    )

    result = apply_signals(state, signals)
    save_state(state)

    if not result.updated_skills:
        console.print("[yellow]No skill scores changed.[/yellow]")
        return

    from . import _data
    domain_names = {d["id"]: d["name"] for d in _data.domains()}
    domain_map = _data.skill_domain_map()

    table = Table(box=box.SIMPLE, show_header=True, header_style="bold", padding=(0, 1))
    table.add_column("Skill", min_width=30)
    table.add_column("Score", justify="right", min_width=10)
    table.add_column("Δ", justify="right", min_width=6)
    table.add_column("Confidence", min_width=10)

    # Group by domain, sort by domain then skill
    by_domain: dict[str, list[str]] = {}
    for skill_id in sorted(result.updated_skills, key=lambda s: (domain_map.get(s, "foundation"), s)):
        dom = domain_map.get(skill_id, "foundation")
        by_domain.setdefault(dom, []).append(skill_id)

    for dom_id, skill_ids in by_domain.items():
        dom_name = domain_names.get(dom_id, "Foundation Skills" if dom_id == "foundation" else dom_id)
        table.add_row(f"[bold dim]{dom_name}[/bold dim]", "", "", "", end_section=False)
        for skill_id in skill_ids:
            s = state.skill_graph[skill_id]
            delta = result.score_deltas.get(skill_id, 0.0)
            conf = result.confidence_changes.get(skill_id, s.confidence)
            conf_color = _confidence_color(conf)
            table.add_row(
                f"  {_skill_name(skill_id)}",
                f"{s.score:.3f}",
                f"[green]+{delta:.3f}[/green]" if delta > 0 else f"{delta:.3f}",
                f"[{conf_color}]{conf}[/{conf_color}]",
            )

    console.print()
    console.print(table)

    if result.integration_bonuses:
        pairs_str = ", ".join(f"{a} + {b}" for a, b in result.integration_bonuses)
        console.print(
            f"\n[dim]Integration bonuses (+0.10) applied for co-occurring skills: {pairs_str}[/dim]"
        )

    console.print(
        f"\n[green]✓[/green] {len(result.updated_skills)} skills updated and saved."
    )
    console.print(
        "[dim]Run [bold]compass status[/bold] to see your updated skill graph, "
        "or [bold]compass recommend[/bold] for your next milestone.[/dim]"
    )


# ── compass recommend ─────────────────────────────────────────────────────────

@cli.command()
@click.option("--learner-id", default=None, help="Learner ID (defaults to active learner).")
@click.option("--accept", is_flag=True, default=False, help="Accept and save the top recommendation as the active milestone.")
def recommend(learner_id: str | None, accept: bool) -> None:
    """Run the planner and show the next recommended milestone."""
    from .agent.planner import plan_next_milestone, compute_velocity
    from .memory.store import load_state, save_state
    from .models import Milestone
    from . import _data

    lid = resolve_learner_id(learner_id)
    state = load_state(lid)
    if state is None:
        console.print(f"[red]Learner [bold]{lid}[/bold] not found.[/red]")
        return

    console.print("\nRunning planner…")
    result = plan_next_milestone(state)

    # Velocity banner
    vel_color = {"high": "green", "moderate": "cyan", "low": "yellow", "stalled": "red"}
    v = result.velocity
    console.print(
        f"\nVelocity: [{vel_color.get(v.tier, 'white')}]{v.signal}[/{vel_color.get(v.tier, 'white')}]"
        f"  [dim](7d: {v.score_7d:.1f}  14d: {v.score_14d:.1f}  ×{v.multiplier:.2f})[/dim]"
    )

    if result.re_engagement_mode:
        console.print(
            "\n[yellow]Re-engagement mode.[/yellow] "
            "No activity detected in the past 14 days.\n"
            "Suggestion: Push a small update to any repo you've been working on, "
            "or add a journal entry about what you've learned recently.\n"
            "Run [bold]compass recommend[/bold] again after any activity."
        )
        return

    if result.no_eligible_skills:
        console.print(
            "\n[green]All skills at or above your target depth.[/green] "
            "Consider raising your [bold]desired_depth[/bold] or exploring a new domain."
        )
        return

    top = result.top
    if top is None:
        console.print("\n[yellow]No milestone candidates found.[/yellow]")
        return

    # Top milestone panel
    depth_thresh = _data.depth_threshold(state.profile.desired_depth)

    console.print()
    console.print(
        Panel(
            f"[bold]{top.domain_name}[/bold]\n"
            f"[dim]Priority score: {top.priority:.3f}[/dim]",
            title="Next Milestone",
            title_align="left",
            style="green",
            expand=False,
        )
    )

    # Target skills table
    table = Table(box=box.SIMPLE, show_header=True, header_style="bold", padding=(0, 1))
    table.add_column("Target Skill", min_width=30)
    table.add_column("Effective", justify="right", min_width=9)
    table.add_column("Target", justify="right", min_width=8)
    table.add_column("Gap", justify="right", min_width=6)
    table.add_column("Unlock Bonus", justify="right", min_width=12)

    for sid in top.target_skills:
        effective = top.skill_scores.get(sid, 0.0)
        gap = max(0.0, depth_thresh - effective)
        priority = top.skill_priorities.get(sid, 0.0)
        table.add_row(
            _skill_name(sid),
            f"{effective:.2f}",
            f"{depth_thresh:.2f}",
            f"{gap:.2f}",
            f"{priority:.3f}",
        )

    console.print(table)

    # Horizon
    if result.horizon:
        console.print("[bold]Horizon[/bold] (next milestones after this one):")
        for i, m in enumerate(result.horizon, 2):
            console.print(f"  {i}. {m.domain_name:<35} [dim]priority: {m.priority:.3f}[/dim]")

    console.print(
        f"\n[dim]{result.eligible_skill_count} eligible skills across all domains[/dim]"
    )

    # Accept flag — save as active milestone
    if accept:
        milestone = Milestone(
            domain=top.domain,
            title=f"{top.domain_name} — {state.profile.desired_depth.capitalize()} Level",
            target_skills=top.target_skills,
            state="in_progress",
            success_criteria=[
                f"Score ≥ {depth_thresh:.2f} on {sid}" for sid in top.target_skills
            ],
        )
        from .models import _now
        milestone.started_at = _now()
        state.active_milestone = milestone
        save_state(state)
        console.print(
            f"\n[green]✓[/green] Milestone saved: [bold]{milestone.title}[/bold]  "
            f"[dim](ID: {milestone.milestone_id[:8]}…)[/dim]"
        )
        console.print(
            "[dim]Run [bold]compass module[/bold] to generate a learning curriculum.[/dim]"
        )
    else:
        console.print(
            "\n[dim]Run [bold]compass recommend --accept[/bold] to set this as your active milestone, "
            "then [bold]compass module[/bold] to generate a curriculum.[/dim]"
        )


# ── compass module ────────────────────────────────────────────────────────────

@cli.command()
@click.option("--learner-id", default=None, help="Learner ID (defaults to active learner).")
@click.option("--refresh", is_flag=True, default=False, help="Regenerate even if a module already exists.")
def module(learner_id: str | None, refresh: bool) -> None:
    """Generate a curriculum module for the active milestone."""
    from datetime import datetime, timedelta, timezone
    from .agent.curriculum import generate_module
    from .memory.store import load_state, save_state

    lid = resolve_learner_id(learner_id)
    state = load_state(lid)
    if state is None:
        console.print(f"[red]Learner [bold]{lid}[/bold] not found.[/red]")
        return

    if state.active_milestone is None:
        console.print(
            "[yellow]No active milestone.[/yellow] "
            "Run [bold]compass recommend --accept[/bold] first."
        )
        return

    milestone = state.active_milestone
    existing = state.modules.get(milestone.milestone_id)

    # Show cached module if fresh (< 30 days) and --refresh not set
    if existing and not refresh:
        from .models import _now
        age_days = (_now() - existing.generated_at).days if hasattr(existing, "generated_at") else 0
        if age_days < 30:
            console.print(
                f"\n[dim]Using cached module (generated {age_days}d ago). "
                "Use [bold]--refresh[/bold] to regenerate.[/dim]"
            )
            _print_module(existing)
            return

    console.print(f"\nGenerating curriculum module for [bold]{milestone.title}[/bold]…")
    result = generate_module(state, milestone)

    if result.failure_mode:
        console.print(
            f"[yellow]⚠ Module generated in fallback mode ({result.failure_mode}).[/yellow] "
            "Showing curated resources only."
        )
    else:
        console.print("[green]✓[/green] Full module generated.")

    state.modules[milestone.milestone_id] = result.module
    save_state(state)
    _print_module(result.module)
    console.print(
        "\n[dim]Run [bold]compass status[/bold] to see your overall progress.[/dim]"
    )


def _print_module(mod: "CurriculumModule") -> None:  # type: ignore[name-defined]
    from .models import CurriculumModule  # noqa: F401 — used for type check above

    console.print()
    console.print(
        Panel(
            f"[bold]{mod.title}[/bold]"
            + (f"\n[dim]Estimated time: {mod.duration_estimate}[/dim]" if mod.duration_estimate else ""),
            title="Curriculum Module",
            title_align="left",
            style="blue",
            expand=False,
        )
    )

    if mod.learning_objectives:
        console.print("\n[bold]Learning Objectives[/bold]")
        for i, obj in enumerate(mod.learning_objectives, 1):
            console.print(f"  {i}. {obj}")

    if mod.concept_primer:
        console.print("\n[bold]Concept Primer[/bold]")
        for c in mod.concept_primer:
            console.print(f"\n  [bold cyan]{c.concept}[/bold cyan]")
            for line in c.explanation.strip().splitlines():
                console.print(f"  {line}")
            if c.why_it_matters:
                console.print()
                for line in c.why_it_matters.strip().splitlines():
                    if line.startswith("Suggested project:"):
                        console.print(f"  [bold]Suggested Project:[/bold] {line[len('Suggested project: '):]}")
                    else:
                        console.print(f"  [dim]{line}[/dim]")

    if mod.resources:
        console.print("\n[bold]Resources[/bold]")
        table = Table(box=box.SIMPLE, show_header=True, header_style="bold", padding=(0, 1))
        table.add_column("#", justify="right", min_width=2)
        table.add_column("Title", min_width=36)
        table.add_column("Type", min_width=8)
        table.add_column("Note", min_width=30)

        for r in sorted(mod.resources, key=lambda x: x.sequence_position):
            table.add_row(
                str(r.sequence_position),
                f"[link={r.url}]{r.title}[/link]",
                f"[dim]{r.resource_type}[/dim]",
                f"[dim]{r.relevance_note}[/dim]",
            )
        console.print(table)


# ── compass run ───────────────────────────────────────────────────────────────

@cli.command()
@click.argument("repo_path", default=".", metavar="REPO", type=click.Path(exists=True, file_okay=False))
@click.option("--learner-id", default=None, help="Learner ID (defaults to active learner).")
@click.option("--no-module", is_flag=True, default=False, help="Skip curriculum module generation.")
def run(repo_path: str, learner_id: str | None, no_module: bool) -> None:
    """End-to-end: scan → assess → recommend → generate module.

    REPO defaults to the current directory.
    """
    import time
    from pathlib import Path as _Path
    from .evidence.scanner import scan_repo
    from .competency.assessor import apply_signals
    from .agent.planner import plan_next_milestone
    from .agent.curriculum import generate_module
    from .memory.store import load_state, save_state
    from .models import GitHubCache, Milestone, _now
    from . import _data

    lid = resolve_learner_id(learner_id)
    state = load_state(lid)
    if state is None:
        console.print(f"[red]Learner [bold]{lid}[/bold] not found. Run [bold]compass init[/bold] first.[/red]")
        return

    repo = _Path(repo_path).resolve()

    # ── Step 1: Scan ──────────────────────────────────────────────────────────
    console.print()
    console.print(
        Panel(
            f"[bold]{state.profile.name}[/bold]  ·  {repo.name}",
            title="AI Builder Compass — Full Run",
            title_align="left",
            style="bold blue",
            expand=False,
        )
    )
    console.print(f"\n[bold]1/4[/bold]  Scanning [bold]{repo}[/bold] …")

    t0 = time.time()
    scan_result = scan_repo(repo)
    elapsed = time.time() - t0

    cache = state.github_cache or GitHubCache()
    if scan_result.repo_name not in cache.repos:
        cache.repos.append(scan_result.repo_name)
    cache.latest_signals = scan_result.signals
    cache.files_scanned = scan_result.files_scanned
    cache.scan_errors = scan_result.errors
    cache.last_scan = _now()
    state.github_cache = cache

    console.print(
        f"    [green]✓[/green] {scan_result.files_scanned} files  ·  "
        f"{len(scan_result.signals)} signals found  ·  {elapsed:.1f}s"
    )

    if not scan_result.signals:
        console.print(
            "\n[yellow]No learning evidence found.[/yellow] "
            "This repo may not contain AI/ML code yet.\n"
            "Try pointing at a different repo, or add AI code first."
        )
        save_state(state)
        return

    # ── Step 2: Assess ────────────────────────────────────────────────────────
    console.print(f"\n[bold]2/4[/bold]  Applying signals to skill graph…")
    assess_result = apply_signals(state, scan_result.signals)
    console.print(
        f"    [green]✓[/green] {len(assess_result.updated_skills)} skills updated"
        + (
            f"  ·  {len(assess_result.integration_bonuses)} integration bonus(es)"
            if assess_result.integration_bonuses else ""
        )
    )

    # ── Step 3: Recommend ─────────────────────────────────────────────────────
    console.print(f"\n[bold]3/4[/bold]  Running planner…")
    plan = plan_next_milestone(state)

    vel_color = {"high": "green", "moderate": "cyan", "low": "yellow", "stalled": "red"}
    v = plan.velocity
    console.print(
        f"    Velocity: [{vel_color.get(v.tier, 'white')}]{v.signal}[/{vel_color.get(v.tier, 'white')}]"
        f"  [dim](×{v.multiplier:.2f})[/dim]"
    )

    if plan.re_engagement_mode:
        save_state(state)
        console.print(
            "\n[yellow]Re-engagement mode.[/yellow] "
            "No recent activity detected — push some code or add a journal entry first."
        )
        return

    if plan.no_eligible_skills or plan.top is None:
        save_state(state)
        console.print(
            "\n[green]All skills at target depth.[/green] "
            "Consider raising your desired depth."
        )
        return

    top = plan.top
    depth_thresh = _data.depth_threshold(state.profile.desired_depth)
    milestone = Milestone(
        domain=top.domain,
        title=f"{top.domain_name} — {state.profile.desired_depth.capitalize()} Level",
        target_skills=top.target_skills,
        state="in_progress",
        success_criteria=[
            f"Score ≥ {depth_thresh:.2f} on {sid}" for sid in top.target_skills
        ],
    )
    milestone.started_at = _now()
    state.active_milestone = milestone
    console.print(
        f"    [green]✓[/green] Milestone: [bold]{milestone.title}[/bold]  "
        f"[dim](priority: {top.priority:.3f})[/dim]"
    )

    # ── Step 4: Module ────────────────────────────────────────────────────────
    if no_module:
        save_state(state)
        console.print("\n[dim]Skipped module generation (--no-module).[/dim]")
    else:
        console.print(f"\n[bold]4/4[/bold]  Generating curriculum module…")
        mod_result = generate_module(state, milestone)
        state.modules[milestone.milestone_id] = mod_result.module
        save_state(state)

        if mod_result.failure_mode:
            console.print(
                f"    [yellow]⚠ Fallback mode ({mod_result.failure_mode})[/yellow] — curated resources only"
            )
        else:
            console.print("    [green]✓[/green] Full module generated")

        _print_module(mod_result.module)

    # ── Summary ───────────────────────────────────────────────────────────────
    console.print()
    console.print(
        Panel(
            f"Scanned [bold]{scan_result.files_scanned}[/bold] files  ·  "
            f"Updated [bold]{len(assess_result.updated_skills)}[/bold] skills  ·  "
            f"Milestone: [bold]{milestone.title}[/bold]",
            title="Done",
            title_align="left",
            style="green",
            expand=False,
        )
    )
    console.print(
        "[dim]Run [bold]compass status[/bold] to see your full skill graph, "
        "or [bold]compass module[/bold] to view the curriculum again.[/dim]"
    )


def _skill_name(skill_id: str) -> str:
    """Resolve skill_id to display name."""
    from . import _data
    for dom in _data.skills()["domains"]:
        for sub in dom["sub_skills"]:
            if sub["id"] == skill_id:
                return sub["name"]
    return skill_id


def _print_milestone_status(state: LearnerState) -> None:
    console.print()
    if state.active_milestone:
        m = state.active_milestone
        console.print(f"[bold]Active milestone:[/bold]  {m.title}  [dim]({m.domain})[/dim]")
        console.print(f"  State: [bold]{m.state}[/bold]")
        if m.project:
            console.print(f"  Project: {m.project.title}  [{m.project.size}]")
        if state.modules.get(m.milestone_id):
            console.print("  [green]✓ Curriculum module available[/green]")
        console.print()
        console.print(
            "[dim]Commands:[/dim]  "
            "[bold]compass scan --repo .[/bold]  ·  "
            "[bold]compass assess[/bold]  ·  "
            "[bold]compass module[/bold]"
        )
    else:
        console.print("[bold]Active milestone:[/bold]  None")
        console.print()
        if state.is_new_learner:
            console.print(
                "[dim]Run [bold]compass scan --repo <path>[/bold] to scan a repo, "
                "then [bold]compass recommend[/bold] to get your first milestone.[/dim]"
            )
        else:
            console.print(
                "[dim]Run [bold]compass recommend[/bold] to get your next milestone.[/dim]"
            )
    console.print()
