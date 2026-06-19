"""CLI entrypoint for AI Builder Compass."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
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
            current_score=0.0,
            experience_score=0.0,
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
    seeded_count = sum(1 for s in skill_graph.values() if s.base_score > 0)
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
        evidenced = sum(1 for s in scores_in_domain if s.current_score > 0)
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
        table.add_column("Current", justify="right", min_width=8)
        table.add_column("Exp.", justify="right", min_width=6)
        table.add_column("Prior", justify="right", min_width=6)
        table.add_column("Effective", justify="right", min_width=9)
        table.add_column("Conf.", min_width=6)

        for sub in _data.sub_skills_by_domain(d["id"]):
            sid = sub["id"]
            s = sg.get(sid)
            if not s:
                continue
            conf_color = _confidence_color(s.confidence)
            prior_str = f"[dim]+{s.base_score:.2f}[/dim]" if s.base_score > 0 else "[dim]—[/dim]"
            table.add_row(
                sub["name"],
                f"{s.current_score:.2f}",
                f"[dim]{s.experience_score:.2f}[/dim]",
                prior_str,
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
        sg.get(sub["id"]) and sg[sub["id"]].current_score > 0
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
            if not s or s.current_score == 0:
                continue
            credits = credit_map.get(sid, {})
            credits_str = "  ".join(
                f"{ai_id.split('.')[-1]} +{boost:.2f}" for ai_id, boost in credits.items()
            )
            conf_color = _confidence_color(s.confidence)
            table.add_row(
                sub["name"],
                f"[{conf_color}]{s.current_score:.2f}[/{conf_color}]",
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

    # Replace old evidence for this repo and persist
    state.evidence = [e for e in state.evidence if e.source_repo != result.repo_name]
    state.evidence.extend(result.evidence)
    cache = state.github_cache or GitHubCache()
    if result.repo_name not in cache.repos:
        cache.repos.append(result.repo_name)
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
    ai_evidence = [e for e in result.evidence if e.skill_id not in foundation_ids]
    foundation_evidence = [e for e in result.evidence if e.skill_id in foundation_ids]

    if not ai_evidence and not foundation_evidence:
        console.print("\n[yellow]No learning evidence found in this repo.[/yellow]")
        console.print("[dim]This may mean the repo doesn't contain AI/ML code yet, or patterns didn't match.[/dim]")
        return

    level_style = {"strong": "green bold", "moderate": "yellow", "weak": "dim"}
    level_label = {"strong": "STRONG", "moderate": "moderate", "weak": "weak"}

    # Foundation skills section
    if foundation_evidence:
        best_f: dict[str, object] = {}
        for ev in foundation_evidence:
            existing = best_f.get(ev.skill_id)
            if existing is None or ev.confidence > existing.confidence:  # type: ignore[union-attr]
                best_f[ev.skill_id] = ev

        ftable = Table(
            title="Foundation Skills Detected",
            box=box.SIMPLE, show_header=True, header_style="bold", padding=(0, 1),
        )
        ftable.add_column("Skill", min_width=26)
        ftable.add_column("Evidence", min_width=10)
        ftable.add_column("Credits AI Skills", min_width=30, style="dim")

        credit_map = _data.foundation_credit_map()
        fmeta = {
            sub["id"]: sub["name"]
            for d in _data.foundation_domains()
            for sub in d["sub_skills"]
        }

        for ev in sorted(best_f.values(), key=lambda e: e.skill_id):  # type: ignore[union-attr]
            lvl = ev.level  # type: ignore[union-attr]
            credits = credit_map.get(ev.skill_id, {})  # type: ignore[union-attr]
            credits_str = "  ".join(
                f"{ai_id.split('.')[-1]} +{boost:.2f}"
                for ai_id, boost in credits.items()
            )
            ftable.add_row(
                fmeta.get(ev.skill_id, ev.skill_id),  # type: ignore[union-attr]
                f"[{level_style.get(lvl, '')}]{level_label.get(lvl, lvl)}[/{level_style.get(lvl, '')}]",
                credits_str or "—",
            )
        console.print()
        console.print(ftable)

    if not ai_evidence:
        console.print(
            f"\n[dim]{len(foundation_evidence)} foundation evidence record(s)  ·  "
            f"0 AI skill signals  ·  Run [bold]compass assess[/bold] to apply.[/dim]"
        )
        return

    # AI skills section — best evidence per skill
    best: dict[str, object] = {}
    for ev in ai_evidence:
        existing = best.get(ev.skill_id)
        if existing is None or ev.confidence > existing.confidence:  # type: ignore[union-attr]
            best[ev.skill_id] = ev

    domain_map = _data.skill_domain_map()
    domain_names = {d["id"]: d["name"] for d in _data.domains()}
    by_domain: dict[str, list] = {}
    for ev in sorted(best.values(), key=lambda e: (domain_map.get(e.skill_id, ""), e.skill_id)):  # type: ignore[union-attr]
        dom = domain_map.get(ev.skill_id, "other")  # type: ignore[union-attr]
        by_domain.setdefault(dom, []).append(ev)

    table = Table(box=box.SIMPLE, show_header=True, header_style="bold", padding=(0, 1))
    table.add_column("Domain", style="bold", min_width=16)
    table.add_column("Skill", min_width=26)
    table.add_column("Best Level", min_width=8)

    for dom_id, evs in by_domain.items():
        first = True
        for ev in evs:
            dom_display = domain_names.get(dom_id, dom_id) if first else ""
            first = False
            lvl = ev.level  # type: ignore[union-attr]
            table.add_row(
                dom_display,
                _skill_name(ev.skill_id),  # type: ignore[union-attr]
                f"[{level_style.get(lvl, '')}]{level_label.get(lvl, lvl)}[/{level_style.get(lvl, '')}]",
            )

    console.print()
    console.print(table)

    strong_skills = {e.skill_id for e in ai_evidence if e.level == "strong"}
    moderate_skills = {e.skill_id for e in ai_evidence if e.level == "moderate"}
    weak_skills = {e.skill_id for e in ai_evidence if e.level == "weak"}
    total = len(best)
    strong = len(strong_skills)
    moderate = len(moderate_skills - strong_skills)
    weak = len(weak_skills - moderate_skills - strong_skills)

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
    from .competency.assessor import apply_evidence
    from .memory.store import load_state, save_state

    lid = resolve_learner_id(learner_id)
    state = load_state(lid)
    if state is None:
        console.print(f"[red]Learner [bold]{lid}[/bold] not found.[/red]")
        return

    if not state.evidence:
        console.print(
            "[yellow]No evidence found. Run [bold]compass scan --repo <path>[/bold] first.[/yellow]"
        )
        return

    console.print(
        f"\nAggregating [bold]{len(state.evidence)}[/bold] evidence records…"
    )

    result = apply_evidence(state)
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
                f"{s.current_score:.3f}",
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

_STEP_LABELS = {
    "repo_scan": "Repo Scan (deterministic)",
    "repo_chronology": "Repo Chronology (git log)",
    "repo_analyze": "Repo Analyze (LLM)",
    "divergence_check": "Divergence Check",
    "evidence_update": "Evidence Update",
    "profile_recompute": "Profile Recompute",
    "recommendation": "Recommendation",
}


def _format_step_line(step) -> str:
    out = step.outputs
    if step.error:
        return f"[yellow]⚠[/yellow] {_STEP_LABELS.get(step.step, step.step):<28} [yellow]{step.error}[/yellow]  [dim]{step.duration_ms}ms[/dim]"

    detail = ""
    if step.step == "repo_scan":
        detail = f"{out.get('files_scanned', 0)} files  ·  {out.get('deterministic_evidence_records', 0)} evidence records"
    elif step.step == "repo_chronology":
        if out.get("is_git_repo") and out.get("first_commit_date"):
            detail = f"{out.get('first_commit_date')} → {out.get('last_commit_date')}"
        else:
            detail = "not a git repo — no chronology"
    elif step.step == "repo_analyze":
        detail = f"{out.get('skills_assessed', 0)} skills assessed  ·  recency: {out.get('repo_recency', 'unknown')}"
    elif step.step == "divergence_check":
        detail = f"{out.get('flagged', 0)} flagged"
        if out.get("flagged_skills"):
            detail += f"  ·  {', '.join(out['flagged_skills'])}"
    elif step.step == "evidence_update":
        detail = f"{out.get('total_evidence_for_repo', 0)} evidence records for this repo"
    elif step.step == "profile_recompute":
        detail = f"{out.get('skills_updated', 0)} skills updated"
        if out.get("integration_bonuses"):
            detail += f"  ·  bonuses: {', '.join(out['integration_bonuses'])}"
    elif step.step == "recommendation":
        if out.get("re_engagement_mode"):
            detail = "re-engagement mode"
        elif out.get("no_eligible_skills"):
            detail = "all skills at target depth"
        else:
            detail = f"{out.get('domain_name', '')}  [dim](priority {out.get('priority', 0):.3f})[/dim]"

    return f"[green]✓[/green] {_STEP_LABELS.get(step.step, step.step):<28} {detail}  [dim]{step.duration_ms}ms[/dim]"


@cli.command()
@click.argument("repo_path", default=".", metavar="REPO", type=click.Path(exists=True, file_okay=False))
@click.option("--learner-id", default=None, help="Learner ID (defaults to active learner).")
def run(repo_path: str, learner_id: str | None) -> None:
    """Run the full agentic pipeline against a repo.

    Orchestrates: repo_scan → repo_analyze (LLM) → divergence_check →
    evidence_update → profile_recompute → recommendation. REPO defaults to
    the current directory. Every run is recorded as a trace — view it with
    `compass trace <run_id>`.
    """
    from pathlib import Path as _Path
    from .agent.orchestrator import run_pipeline
    from .memory.store import load_state, save_state, save_trace

    lid = resolve_learner_id(learner_id)
    state = load_state(lid)
    if state is None:
        console.print(f"[red]Learner [bold]{lid}[/bold] not found. Run [bold]compass init[/bold] first.[/red]")
        return

    repo = _Path(repo_path).resolve()

    console.print()
    console.print(
        Panel(
            f"[bold]{state.profile.name}[/bold]  ·  {repo.name}",
            title="AI Builder Compass — Agentic Run",
            title_align="left",
            style="bold blue",
            expand=False,
        )
    )
    console.print()

    with console.status("Running pipeline…"):
        trace = run_pipeline(state, repo)

    save_state(state)
    trace_path = save_trace(trace)

    for step in trace.steps:
        console.print(_format_step_line(step))

    if trace.divergence_flags:
        console.print()
        console.print("[bold]Divergence flags:[/bold]")
        for f in trace.divergence_flags:
            console.print(
                f"  [yellow]⚠[/yellow] {_skill_name(f.skill_id)}: "
                f"LLM {f.llm_confidence:.0%} vs deterministic {f.deterministic_score:.2f} — {f.reason}"
            )

    console.print()
    rec = trace.recommendation_summary
    if rec.get("re_engagement_mode"):
        console.print(
            "[yellow]Re-engagement mode.[/yellow] No activity in the past 14 days — "
            "push a small update or add a journal entry, then run again."
        )
    elif rec.get("no_eligible_skills"):
        console.print("[green]All skills at or above target depth.[/green] Consider raising desired_depth.")
    elif rec:
        console.print(
            Panel(
                f"[bold]{rec.get('domain_name', '')}[/bold]\n"
                f"[dim]Priority: {rec.get('priority', 0):.3f}  ·  Velocity: {rec.get('velocity_signal', '')}[/dim]",
                title="Next Milestone",
                title_align="left",
                style="green",
                expand=False,
            )
        )
        console.print(
            "[dim]Run [bold]compass recommend --accept[/bold] to set this as your active milestone.[/dim]"
        )

    console.print()
    console.print(
        f"[dim]Run ID: [bold]{trace.run_id}[/bold]  ·  trace saved to {trace_path}[/dim]"
    )
    console.print(f"[dim]Run [bold]compass trace {trace.run_id}[/bold] for full detail.[/dim]")


# ── compass trace ────────────────────────────────────────────────────────────

@cli.command()
@click.argument("run_id")
@click.option("--learner-id", default=None, help="Learner ID (narrows the search; defaults to active learner, then searches all learners).")
def trace(run_id: str, learner_id: str | None) -> None:
    """Show full observability detail for a `compass run` execution.

    Displays: tools called, inputs/outputs, files sampled, LLM prompt/response,
    evidence records created, divergence flags, and per-skill aggregation math.
    """
    from .memory.store import load_trace, find_trace

    lid = learner_id or get_active_learner_id()
    t = load_trace(lid, run_id) if lid else None
    if t is None:
        t = find_trace(run_id)
    if t is None:
        console.print(f"[red]No trace found for run ID [bold]{run_id}[/bold].[/red]")
        sys.exit(1)

    duration = ""
    if t.completed_at:
        duration = f"{(t.completed_at - t.started_at).total_seconds():.1f}s"

    console.print()
    console.print(
        Panel(
            f"Learner: [bold]{t.learner_id}[/bold]  ·  Repo: [bold]{t.repo_name}[/bold]\n"
            f"[dim]{t.repo_path}[/dim]\n"
            f"Started: {t.started_at.strftime('%Y-%m-%d %H:%M:%S')}  ·  Duration: {duration}",
            title=f"Run Trace: {t.run_id}",
            title_align="left",
            style="blue",
            expand=False,
        )
    )

    # ── Tools called ──────────────────────────────────────────────────────────
    console.print("\n[bold]Tools Called[/bold]")
    table = Table(box=box.SIMPLE, show_header=True, header_style="bold", padding=(0, 1))
    table.add_column("Step", min_width=20)
    table.add_column("Duration", justify="right", min_width=8)
    table.add_column("Inputs", min_width=30, style="dim")
    table.add_column("Outputs", min_width=30, style="dim")
    table.add_column("Error", style="yellow")
    for step in t.steps:
        table.add_row(
            step.step,
            f"{step.duration_ms}ms",
            ", ".join(f"{k}={v}" for k, v in step.inputs.items()),
            ", ".join(f"{k}={v}" for k, v in step.outputs.items()),
            step.error or "",
        )
    console.print(table)

    # ── Files sampled ────────────────────────────────────────────────────────
    if t.files_sampled:
        console.print("\n[bold]Files Sampled (LLM context)[/bold]")
        for f in t.files_sampled:
            console.print(f"  [dim]•[/dim] {f}")

    # ── LLM prompt/response ──────────────────────────────────────────────────
    if t.llm_prompt:
        console.print("\n[bold]LLM Prompt[/bold]")
        console.print(Panel(t.llm_prompt, style="dim", expand=False))
    if t.llm_response:
        console.print("\n[bold]LLM Response[/bold]")
        console.print(Panel(t.llm_response, style="dim", expand=False))

    # ── Evidence created ─────────────────────────────────────────────────────
    if t.evidence_created:
        console.print("\n[bold]Evidence Records Created[/bold]")
        ev_table = Table(box=box.SIMPLE, show_header=True, header_style="bold", padding=(0, 1))
        ev_table.add_column("Skill", min_width=24)
        ev_table.add_column("Type", min_width=12)
        ev_table.add_column("Recency", min_width=10)
        ev_table.add_column("Confidence", justify="right", min_width=10)
        ev_table.add_column("Rationale", style="dim", ratio=1)
        for ev in t.evidence_created:
            ev_table.add_row(
                _skill_name(ev.skill_id),
                ev.evidence_type,
                ev.recency,
                f"{ev.confidence}%",
                ev.rationale,
            )
        console.print(ev_table)

    # ── Divergence flags ─────────────────────────────────────────────────────
    if t.divergence_flags:
        console.print("\n[bold]Divergence Flags[/bold]")
        for f in t.divergence_flags:
            console.print(
                f"  [yellow]⚠[/yellow] {_skill_name(f.skill_id)}: "
                f"LLM {f.llm_confidence:.0%} vs deterministic {f.deterministic_score:.2f} — {f.reason}"
            )

    # ── Aggregation math per skill ───────────────────────────────────────────
    if t.aggregation:
        console.print("\n[bold]Aggregation Math[/bold]")
        for agg in t.aggregation:
            console.print(
                f"\n  [bold cyan]{_skill_name(agg.skill_id)}[/bold cyan]  "
                f"→ current={agg.current_score:.3f}  experience={agg.experience_score:.3f}"
            )
            if agg.contributions:
                contrib_table = Table(box=box.SIMPLE, show_header=True, header_style="bold", padding=(0, 1))
                contrib_table.add_column("Source", min_width=16)
                contrib_table.add_column("Type", min_width=10)
                contrib_table.add_column("Recency", min_width=10)
                contrib_table.add_column("Conf.", justify="right", min_width=6)
                contrib_table.add_column("Current contrib.", justify="right", min_width=14)
                contrib_table.add_column("Exp. contrib.", justify="right", min_width=12)
                for c in agg.contributions:
                    contrib_table.add_row(
                        c.get("source_repo") or "—",
                        c.get("evidence_type", ""),
                        c.get("recency", ""),
                        f"{c.get('confidence', 0)}%",
                        f"{c.get('current_contribution', 0):.3f}",
                        f"{c.get('experience_contribution', 0):.3f}",
                    )
                console.print(contrib_table)

    console.print()


# ── compass review ───────────────────────────────────────────────────────────

def _gather_unresolved_flags(learner_id: str, skill: str | None, repo: str | None):
    """Return [(trace, flag), ...] for unresolved divergence flags, most urgent first."""
    from .memory.store import list_traces

    pairs = []
    for t in list_traces(learner_id):
        if repo and t.repo_name != repo:
            continue
        for flag in t.divergence_flags:
            if flag.resolved:
                continue
            if skill and flag.skill_id != skill:
                continue
            pairs.append((t, flag))

    pairs.sort(key=lambda p: (p[1].llm_confidence - p[1].deterministic_score), reverse=True)
    return pairs


@cli.command()
@click.option("--learner-id", default=None, help="Learner ID (defaults to active learner).")
@click.option("--skill", default=None, help="Filter to a specific skill_id (e.g. mcp.building).")
@click.option("--repo", default=None, help="Filter to a specific repo name.")
def review(learner_id: str | None, skill: str | None, repo: str | None) -> None:
    """Interactively review unresolved divergence flags from past runs.

    Surfaces cases where the LLM assessment diverges from deterministic
    evidence (high LLM confidence, zero deterministic score) or where the
    LLM's rationale was too weak/generic to trust outright. For each flag:
    accept (keep as-is), downgrade (keep, lower confidence), reject (exclude
    from scoring, kept in the trace), or correct (fix skill/recency/type).
    """
    from . import _data
    from .competency.assessor import apply_evidence
    from .memory.store import load_state, save_state, save_trace
    from .models import EvidenceCorrection

    lid = resolve_learner_id(learner_id)
    state = load_state(lid)
    if state is None:
        console.print(f"[red]Learner [bold]{lid}[/bold] not found.[/red]")
        return

    pairs = _gather_unresolved_flags(lid, skill, repo)
    if not pairs:
        filt = []
        if skill:
            filt.append(f"skill={skill}")
        if repo:
            filt.append(f"repo={repo}")
        suffix = f"  [dim]({', '.join(filt)})[/dim]" if filt else ""
        console.print(f"\n[green]No unresolved divergence flags.[/green]{suffix}")
        return

    console.print(f"\n[bold]{len(pairs)}[/bold] unresolved divergence flag(s).\n")

    recency_choice = click.Choice(["", "current", "historical", "unknown"])
    etype_choice = click.Choice(["", "observed", "inferred", "synthesized"])
    valid_skill_ids = set(_data.all_skill_ids()) | set(_data.all_foundation_skill_ids())

    dirty_traces: dict[str, object] = {}
    new_corrections: list[EvidenceCorrection] = []

    try:
        for i, (t, flag) in enumerate(pairs, 1):
            ev = next((e for e in t.evidence_created if e.skill_id == flag.skill_id), None)
            body = (
                f"[bold]{_skill_name(flag.skill_id)}[/bold]  [dim]({flag.skill_id})[/dim]\n"
                f"Repo: {t.repo_name}  ·  Run: {t.run_id[:8]}…\n"
                f"LLM confidence: [bold]{flag.llm_confidence:.0%}[/bold]   "
                f"Deterministic score: [bold]{flag.deterministic_score:.2f}[/bold]\n"
                f"[dim]{flag.reason}[/dim]"
            )
            if ev:
                body += f"\n\n[italic]{ev.rationale}[/italic]"
            console.print(Panel(body, title=f"Flag {i}/{len(pairs)}", title_align="left", style="yellow", expand=False))

            console.print("  [cyan]1[/cyan] accept    — keep the LLM evidence as-is")
            console.print("  [cyan]2[/cyan] downgrade — keep it, reduce confidence")
            console.print("  [cyan]3[/cyan] reject    — exclude from scoring, keep in trace")
            console.print("  [cyan]4[/cyan] correct   — fix skill / recency / evidence_type")
            console.print("  [cyan]5[/cyan] skip      — leave unresolved for now")
            choice = click.prompt("Choice", type=click.IntRange(1, 5), default=5)

            if choice == 5:
                console.print()
                continue

            action = {1: "accept", 2: "downgrade", 3: "reject", 4: "correct"}[choice]
            corrected_skill_id = corrected_recency = corrected_evidence_type = None

            if action == "correct":
                raw_skill = click.prompt("New skill_id (blank = keep)", default="", show_default=False).strip()
                if raw_skill:
                    if raw_skill not in valid_skill_ids:
                        console.print(f"  [yellow]⚠ '{raw_skill}' is not a known skill_id — saving anyway.[/yellow]")
                    corrected_skill_id = raw_skill
                corrected_recency = click.prompt("New recency", type=recency_choice, default="", show_default=False) or None
                corrected_evidence_type = click.prompt("New evidence_type", type=etype_choice, default="", show_default=False) or None

            note = click.prompt("Note (optional)", default="", show_default=False)

            correction = EvidenceCorrection(
                skill_id=flag.skill_id,
                source_repo=t.repo_name,
                action=action,
                corrected_skill_id=corrected_skill_id,
                corrected_recency=corrected_recency,
                corrected_evidence_type=corrected_evidence_type,
                note=note,
                run_id=t.run_id,
            )
            state.corrections.append(correction)
            new_corrections.append(correction)

            flag.resolved = True
            flag.correction_id = correction.correction_id
            dirty_traces[t.run_id] = t

            console.print(f"  [green]✓[/green] Recorded: [bold]{action}[/bold]\n")

    except (KeyboardInterrupt, click.exceptions.Abort):
        console.print("\n\n[yellow]Stopped early — saving progress so far.[/yellow]")

    if new_corrections:
        apply_evidence(state)
        save_state(state)
        for t in dirty_traces.values():
            save_trace(t)
        console.print(
            f"[green]✓[/green] {len(new_corrections)} correction(s) saved. "
            f"Skill graph recomputed. [dim](compass status to see the effect)[/dim]"
        )
    else:
        console.print("[dim]No changes made.[/dim]")


# ── compass corrections ──────────────────────────────────────────────────────

@cli.group()
def corrections() -> None:
    """Manage persisted evidence corrections from `compass review`."""


_ACTION_STYLE = {"accept": "green", "downgrade": "yellow", "reject": "red", "correct": "cyan"}


@corrections.command("list")
@click.option("--learner-id", default=None, help="Learner ID (defaults to active learner).")
def corrections_list(learner_id: str | None) -> None:
    """List all persisted evidence corrections for a learner."""
    from .memory.store import load_state

    lid = resolve_learner_id(learner_id)
    state = load_state(lid)
    if state is None:
        console.print(f"[red]Learner [bold]{lid}[/bold] not found.[/red]")
        return

    if not state.corrections:
        console.print("\n[dim]No corrections recorded yet. Run [bold]compass review[/bold].[/dim]")
        return

    table = Table(box=box.SIMPLE, show_header=True, header_style="bold", padding=(0, 1))
    table.add_column("Skill", min_width=24)
    table.add_column("Repo", min_width=14)
    table.add_column("Action", min_width=10)
    table.add_column("Correction", min_width=24, style="dim")
    table.add_column("Note", min_width=20, style="dim")
    table.add_column("Date", min_width=10)

    for c in sorted(state.corrections, key=lambda c: c.created_at, reverse=True):
        style = _ACTION_STYLE.get(c.action, "")
        correction_str = ""
        if c.action == "correct":
            parts = []
            if c.corrected_skill_id:
                parts.append(f"skill→{c.corrected_skill_id}")
            if c.corrected_recency:
                parts.append(f"recency→{c.corrected_recency}")
            if c.corrected_evidence_type:
                parts.append(f"type→{c.corrected_evidence_type}")
            correction_str = "  ".join(parts)
        table.add_row(
            _skill_name(c.skill_id),
            c.source_repo or "[dim](all repos)[/dim]",
            f"[{style}]{c.action}[/{style}]",
            correction_str,
            c.note,
            c.created_at.strftime("%Y-%m-%d"),
        )

    console.print()
    console.print(table)


def _skill_name(skill_id: str) -> str:
    """Resolve skill_id to display name."""
    from . import _data
    for dom in _data.skills()["domains"] + _data.skills().get("foundation_domains", []):
        for sub in dom["sub_skills"]:
            if sub["id"] == skill_id:
                return sub["name"]
    return skill_id


# ── compass analyze ───────────────────────────────────────────────────────────

@cli.command()
@click.argument("repo_path", default=".", metavar="REPO", type=click.Path(exists=True, file_okay=False))
@click.option("--learner-id", default=None, help="Learner ID (defaults to active learner).")
def analyze(repo_path: str, learner_id: str | None) -> None:
    """Run LLM deep assessment on a repo and store the results.

    REPO defaults to the current directory. Results are stored separately
    from deterministic scan signals and do not affect skill scores.
    Use `compass explain` to view the assessment.
    """
    import time
    from pathlib import Path as _Path
    from .evidence.llm_assessor import assess_repo, apply_guardrails
    from .memory.store import load_state, save_state

    lid = resolve_learner_id(learner_id)
    state = load_state(lid)
    if state is None:
        console.print(f"[red]Learner [bold]{lid}[/bold] not found.[/red]")
        return

    repo = _Path(repo_path).resolve()
    console.print()
    console.print(Panel.fit(
        f"LLM Deep Assessment\n[dim]{repo}[/dim]",
        style="blue",
    ))
    console.print()

    t0 = time.time()
    with console.status("Analyzing repo with LLM…"):
        result = assess_repo(repo)
    elapsed = time.time() - t0

    if result.error:
        if result.error == "no_api_key":
            console.print(
                "[yellow]No API key found.[/yellow] Set [bold]OPENAI_API_KEY[/bold] in your .env file."
            )
        else:
            console.print(f"[red]Assessment failed:[/red] {result.error}")
        return

    # Apply divergence + evidence-quality guardrails before saving
    apply_guardrails(result, state.skill_graph)

    # Backfill scanner evidence recency using LLM repo_recency classification
    if result.repo_recency in ("current", "historical"):
        for ev in state.evidence:
            if ev.source_repo == result.repo_name and ev.recency == "unknown":
                ev.recency = result.repo_recency

    # Per-skill override: LLM evidence_type refines recency beyond the repo-level default
    skill_recency: dict[str, str] = {}
    for skill in result.skills:
        if skill.evidence_type == "current_demonstrated":
            skill_recency[skill.skill_id] = "current"
        elif skill.evidence_type == "historical_experience":
            skill_recency[skill.skill_id] = "historical"
    for ev in state.evidence:
        if ev.source_repo == result.repo_name and ev.skill_id in skill_recency:
            ev.recency = skill_recency[ev.skill_id]

    # Re-aggregate scores so profile reflects updated recency weights
    from .competency.assessor import apply_evidence
    apply_evidence(state)

    # Replace any existing assessment for this repo
    state.llm_assessments = [a for a in state.llm_assessments if a.repo_name != result.repo_name]
    state.llm_assessments.append(result)
    save_state(state)

    console.print(f"[green]✓[/green] Assessment complete in [bold]{elapsed:.1f}s[/bold]  "
                  f"·  [bold]{len(result.skills)}[/bold] skills assessed  "
                  f"·  model: [dim]{result.model}[/dim]")
    console.print()

    if result.repo_summary:
        console.print(Panel(result.repo_summary, title="Repo Summary", title_align="left", expand=False))
        console.print()

    if not result.skills:
        console.print("[yellow]No skills assessed.[/yellow]")
        return

    _print_llm_assessment(result, state)
    console.print()
    console.print("[dim]Run [bold]compass explain[/bold] to see LLM assessments alongside deterministic scores.[/dim]")


# ── compass explain ───────────────────────────────────────────────────────────

def _gather_all_flags_for_skill(learner_id: str, skill_id: str):
    """Return [(trace, flag), ...] for ALL divergence flags (resolved + unresolved) for one skill."""
    from .memory.store import list_traces

    pairs = []
    for t in list_traces(learner_id):
        for flag in t.divergence_flags:
            if flag.skill_id == skill_id:
                pairs.append((t, flag))
    return pairs


def _print_skill_explanation(state: LearnerState, skill_id: str, learner_id: str) -> None:
    from .agent.narrative import confidence_label, zone

    if skill_id not in state.skill_graph:
        console.print(f"\n[yellow]Compass has no evidence for [bold]{skill_id}[/bold].[/yellow]")
        return

    score = state.skill_graph[skill_id]
    records = [e for e in state.evidence if e.skill_id == skill_id]

    console.print()
    console.print(Panel.fit(f"Why {_skill_name(skill_id)}?", style="bold blue"))

    if not records:
        console.print(
            "\n[dim]No direct evidence records — this score reflects foundation credits "
            "or a role prior, not a scanned/analyzed repo.[/dim]"
        )
    else:
        by_repo: dict[str, list] = {}
        for ev in records:
            by_repo.setdefault(ev.source_repo or "unknown", []).append(ev)

        console.print("\n[bold]Evidence Sources[/bold]")
        for repo_name, evs in sorted(by_repo.items()):
            console.print(f"\n  [bold]{repo_name}[/bold]")
            scan_descs: list[str] = []
            for ev in evs:
                if ev.source == "scan":
                    for d in ev.matched_signals:
                        if d not in scan_descs:
                            scan_descs.append(d)
            for d in scan_descs:
                console.print(f"    • {d}")
            for ev in evs:
                if ev.source == "llm" and ev.rationale:
                    console.print(f"    • [dim][LLM-inferred][/dim] {ev.rationale}")
            if not scan_descs and not any(ev.source == "llm" and ev.rationale for ev in evs):
                console.print("    [dim](evidence recorded, no detailed signal text available)[/dim]")

    z = zone(score.current_score, score.experience_score)
    conf = confidence_label(score.current_score)
    console.print(f"\n[bold]Confidence[/bold]")
    conf_color = _confidence_color(conf)
    console.print(
        f"  [{conf_color}]{conf.title()}[/{conf_color}]  "
        f"[dim](current {score.current_score:.2f}, experience {score.experience_score:.2f})[/dim]"
    )

    n_repos = len({e.source_repo for e in records if e.source_repo})
    console.print("\n[bold]Reasoning[/bold]")
    if records:
        console.print(
            f"  Classified as {z} with {conf} confidence, based on "
            f"{len(records)} evidence record(s) across {n_repos} repo(s)."
        )
    else:
        console.print(f"  Classified as {z} with {conf} confidence from non-evidence sources.")

    flags = _gather_all_flags_for_skill(learner_id, skill_id)
    if flags:
        console.print("\n[bold]Divergence Flags[/bold]")
        for t, f in flags:
            if f.resolved:
                marker = "[dim](resolved)[/dim]"
            else:
                marker = "[yellow]⚠ unresolved[/yellow]"
            console.print(
                f"  {marker} {t.repo_name}: LLM {f.llm_confidence:.0%} vs "
                f"deterministic {f.deterministic_score:.2f} — {f.reason}"
            )
    console.print()


@cli.command()
@click.argument("skill_id", required=False, default=None, metavar="SKILL")
@click.option("--learner-id", default=None, help="Learner ID (defaults to active learner).")
@click.option("--repo", default=None, help="Filter to a specific repo name.")
def explain(skill_id: str | None, learner_id: str | None, repo: str | None) -> None:
    """Show why Compass believes a skill exists, or list LLM repo assessments.

    With SKILL: explains exactly why Compass believes that skill is evidenced —
    deterministic signals, LLM rationale, confidence, and any divergence flags.
    Without SKILL: lists LLM assessments alongside deterministic skill scores
    per analyzed repo (original behavior, optionally filtered by --repo).
    """
    from .memory.store import load_state

    lid = resolve_learner_id(learner_id)
    state = load_state(lid)
    if state is None:
        console.print(f"[red]Learner [bold]{lid}[/bold] not found.[/red]")
        return

    if skill_id:
        _print_skill_explanation(state, skill_id, lid)
        return

    assessments = state.llm_assessments
    if repo:
        assessments = [a for a in assessments if a.repo_name == repo]

    if not assessments:
        console.print()
        if repo:
            console.print(f"[yellow]No LLM assessment found for repo '{repo}'.[/yellow]")
        else:
            console.print("[yellow]No LLM assessments found.[/yellow]")
        console.print("[dim]Run [bold]compass analyze <repo_path>[/bold] first.[/dim]")
        return

    console.print()
    for assessment in assessments:
        assessed_date = assessment.assessed_at.strftime("%Y-%m-%d")
        console.print(Panel(
            f"{assessment.repo_summary or 'No summary.'}\n\n"
            f"[dim]Assessed {assessed_date}  ·  {assessment.model}[/dim]",
            title=f"LLM Assessment: {assessment.repo_name}",
            title_align="left",
            style="blue",
            expand=False,
        ))
        console.print()
        _print_llm_assessment(assessment, state)
        console.print()


def _print_llm_assessment(assessment, state: LearnerState) -> None:
    """Print a table of LLM-assessed skills with deterministic scores alongside."""
    etype_style = {
        "current_demonstrated":  "green",
        "historical_experience": "yellow",
        "inferred_exposure":     "dim",
        "inferred_low_confidence": "dim",
    }
    etype_label = {
        "current_demonstrated":  "current",
        "historical_experience": "historical",
        "inferred_exposure":     "inferred",
        "inferred_low_confidence": "low-conf",
    }

    order = {
        "current_demonstrated": 0,
        "historical_experience": 1,
        "inferred_exposure": 2,
        "inferred_low_confidence": 3,
    }
    sorted_skills = sorted(
        assessment.skills,
        key=lambda s: (order.get(s.evidence_type, 4), -s.confidence),
    )

    table = Table(box=box.SIMPLE, show_header=True, header_style="bold", padding=(0, 1), expand=True)
    table.add_column("Skill", min_width=24, no_wrap=True)
    table.add_column("Conf · Type", min_width=16, no_wrap=True)
    table.add_column("Flag", min_width=8, no_wrap=True)
    table.add_column("Rationale", ratio=1)

    for s in sorted_skills:
        style = etype_style.get(s.evidence_type, "")
        label = etype_label.get(s.evidence_type, s.evidence_type)
        flag = "[yellow]⚠ review[/yellow]" if s.needs_review else ""
        conf_type = f"[{style}]{s.confidence:.0%}  {label}[/{style}]"
        table.add_row(
            _skill_name(s.skill_id),
            conf_type,
            flag,
            s.rationale,
        )

    console.print(table)

    flagged = [s for s in assessment.skills if s.needs_review or s.evidence_type == "inferred_low_confidence"]
    if flagged:
        console.print()
        console.print("[bold]Flagged skills:[/bold]")
        for s in flagged:
            console.print(f"  [yellow]⚠[/yellow] [bold]{_skill_name(s.skill_id)}[/bold]: {s.review_reason}")


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


# ── compass profile ───────────────────────────────────────────────────────────

_ZONE_BADGE = {
    "core":     "[green]● CORE[/green]",
    "dormant":  "[yellow]○ DORMANT[/yellow]",
    "learning": "[dim]· LEARNING[/dim]",
}
_ZONE_SORT  = {"core": 0, "dormant": 1, "learning": 2, "none": 3}
_ZONE_STYLE = {"core": "green", "dormant": "yellow", "learning": "dim"}


def _zone(current: float, experience: float) -> str:
    if current >= 0.50:
        return "core"
    if experience >= 0.40:
        return "dormant"
    if current > 0.0 or experience > 0.0:
        return "learning"
    return "none"


def _print_profile_matrix(state: LearnerState) -> None:
    from collections import Counter
    from . import _data

    sg = state.skill_graph
    domain_map = _data.skill_domain_map()

    evidenced = [
        (sid, ss, _zone(ss.current_score, ss.experience_score))
        for sid, ss in sg.items()
        if ss.current_score > 0 or ss.experience_score > 0
    ]
    if not evidenced:
        console.print("[yellow]No evidence yet. Run [bold]compass scan[/bold] first.[/yellow]")
        return

    evidenced.sort(key=lambda x: (_ZONE_SORT[x[2]], -x[1].experience_score))
    counts = Counter(z for _, _, z in evidenced)

    parts = []
    for z, label in [("core", "core"), ("dormant", "dormant"), ("learning", "learning")]:
        if counts[z]:
            badge = _ZONE_BADGE[z]
            parts.append(f"[bold]{counts[z]}[/bold] {badge}")
    console.print()
    console.print(f"[bold]{len(evidenced)}[/bold] evidenced skills  ·  " + "  ·  ".join(parts))
    console.print()

    table = Table(box=box.SIMPLE, show_header=True, header_style="bold", padding=(0, 1))
    table.add_column("Skill", min_width=32, no_wrap=True)
    table.add_column("Current", justify="right", min_width=8)
    table.add_column("Exp.", justify="right", min_width=6)
    table.add_column("Zone", min_width=14, no_wrap=True)

    section_labels = {"core": "Core Strength", "dormant": "Dormant Skills", "learning": "Learning"}
    current_zone = None
    for sid, ss, z in evidenced:
        if z != current_zone:
            current_zone = z
            table.add_row(f"[bold dim]{section_labels.get(z, z.title())}[/bold dim]", "", "", "")
        table.add_row(
            f"  {_skill_name(sid)}",
            f"{ss.current_score:.2f}",
            f"[dim]{ss.experience_score:.2f}[/dim]",
            _ZONE_BADGE.get(z, ""),
        )
    console.print(table)

    # Role-relevant gaps: base_score set but no evidence
    gaps = [
        sid for sid in _data.all_skill_ids()
        if sid in sg
        and sg[sid].current_score == 0
        and sg[sid].experience_score == 0
        and sg[sid].base_score > 0
    ]
    if gaps:
        console.print()
        console.print("[dim]Role-relevant gaps (no evidence yet):[/dim]")
        names = "  ·  ".join(_skill_name(sid) for sid in sorted(gaps)[:8])
        if len(gaps) > 8:
            names += f"  +{len(gaps) - 8} more"
        console.print(f"  [dim]{names}[/dim]")

    console.print()
    console.print("[dim]Run [bold]compass profile --detail[/bold] for evidence-backed competency cards.[/dim]")


def _render_domain_card(
    domain_name: str,
    subs: list[dict],
    sg: dict,
    ev_by_skill: dict,
    llm_by_skill: dict,
    credit_map: dict | None = None,
) -> None:
    scores = [sg[sub["id"]] for sub in subs if sub["id"] in sg]
    max_current = max((ss.current_score for ss in scores), default=0.0)
    max_exp     = max((ss.experience_score for ss in scores), default=0.0)
    z = _zone(max_current, max_exp)

    console.print(Rule(title=f" {domain_name}  {_ZONE_BADGE.get(z, '')} ", style="bold dim"))

    # Compact skill list — 3 per row
    skill_parts = []
    for sub in subs:
        ss = sg.get(sub["id"])
        if not ss:
            continue
        sz  = _zone(ss.current_score, ss.experience_score)
        st  = _ZONE_STYLE.get(sz, "")
        label = f"[{st}]{sub['name']}  {ss.current_score:.2f}[/{st}]" if st else f"{sub['name']}  {ss.current_score:.2f}"
        skill_parts.append(label)

    for i in range(0, len(skill_parts), 3):
        console.print("  " + "   ·   ".join(skill_parts[i:i + 3]))

    # Evidence block — group by source repo
    all_ev = [ev for sub in subs for ev in ev_by_skill.get(sub["id"], [])]
    if all_ev:
        console.print()
        by_repo: dict[str, list] = {}
        for ev in all_ev:
            by_repo.setdefault(ev.source_repo or "unknown", []).append(ev)

        for repo, evs in sorted(by_repo.items()):
            types    = " & ".join(sorted({ev.evidence_type for ev in evs}))
            recency  = "/".join(sorted({ev.recency for ev in evs}))
            max_conf = max(ev.confidence for ev in evs)
            console.print(f"  [dim]{repo}  ·  {types}  ·  {recency}  ·  conf {max_conf}%[/dim]")

            # LLM rationales from this repo for any skill in this domain
            shown: set[str] = set()
            for sub in subs:
                for (llm_repo, rationale, needs_review) in llm_by_skill.get(sub["id"], []):
                    if llm_repo == repo and rationale not in shown:
                        shown.add(rationale)
                        short = rationale if len(rationale) <= 110 else rationale[:107] + "..."
                        flag  = " [yellow]⚠[/yellow]" if needs_review else ""
                        console.print(f"    [italic dim]{short}[/italic dim]{flag}")

    # No direct evidence (scores come from foundation credits or role prior)
    if not all_ev and max_current > 0:
        console.print()
        console.print("  [dim]No direct evidence — scores reflect foundation credits or role prior[/dim]")

    # Historical-only warning
    if all_ev and all(ev.recency == "historical" for ev in all_ev):
        console.print(f"  [yellow dim]All evidence is historical — no recent activity detected[/yellow dim]")

    # Foundation credits
    if credit_map:
        credit_parts: list[str] = []
        for sub in subs:
            ss = sg.get(sub["id"])
            if ss and ss.current_score > 0:
                for ai_id, boost in credit_map.get(sub["id"], {}).items():
                    credit_parts.append(f"{ai_id.split('.')[-1]} +{boost:.2f}")
        if credit_parts:
            console.print(f"  [dim]→ credits AI skills:  {'  ·  '.join(credit_parts)}[/dim]")

    console.print()


def _print_competency_cards(state: LearnerState) -> None:
    from . import _data

    sg = state.skill_graph

    llm_by_skill: dict[str, list[tuple[str, str, bool]]] = {}
    for assessment in state.llm_assessments:
        for skill in assessment.skills:
            if skill.rationale:
                llm_by_skill.setdefault(skill.skill_id, []).append(
                    (assessment.repo_name, skill.rationale, skill.needs_review)
                )

    ev_by_skill: dict[str, list] = {}
    for ev in state.evidence:
        ev_by_skill.setdefault(ev.skill_id, []).append(ev)

    console.print()
    for d in _data.domains():
        evidenced = [
            sub for sub in _data.sub_skills_by_domain(d["id"])
            if sub["id"] in sg and (sg[sub["id"]].current_score > 0 or sg[sub["id"]].experience_score > 0)
        ]
        if evidenced:
            _render_domain_card(d["name"], evidenced, sg, ev_by_skill, llm_by_skill)

    foundation_subs = [
        sub
        for fdom in _data.foundation_domains()
        for sub in fdom["sub_skills"]
        if sub["id"] in sg and (sg[sub["id"]].current_score > 0 or sg[sub["id"]].experience_score > 0)
    ]
    if foundation_subs:
        _render_domain_card(
            "Foundation Skills",
            foundation_subs,
            sg,
            ev_by_skill,
            llm_by_skill,
            credit_map=_data.foundation_credit_map(),
        )


def _print_profile_narrative(state: LearnerState) -> None:
    from .agent.narrative import build_profile_narrative

    narrative = build_profile_narrative(state)

    console.print()
    console.print(Panel.fit(narrative.archetype, title="Builder Archetype", title_align="left", style="bold blue"))

    if narrative.secondary_clusters:
        console.print("\n[bold]Secondary Focus[/bold]")
        for c in narrative.secondary_clusters:
            console.print(f"  • {c}")

    if narrative.emerging_clusters:
        console.print("\n[bold]Exploring[/bold]")
        for c in narrative.emerging_clusters:
            console.print(f"  • {c}")

    if narrative.strengths:
        console.print("\n[bold]Current Strengths[/bold]")
        for s in narrative.strengths:
            console.print(f"  • {s}")

    if narrative.emerging:
        console.print("\n[bold]Emerging Skills[/bold]")
        for s in narrative.emerging:
            console.print(f"  • {s}")

    if narrative.foundation_skills or narrative.dormant_ai_skills:
        console.print("\n[bold]Foundation Skills[/bold]")
        if narrative.dormant_ai_skills:
            if narrative.foundation_skills:
                console.print("  [dim]Foundation:[/dim]")
                for s in narrative.foundation_skills:
                    console.print(f"    • {s}")
            console.print("  [dim]Previously demonstrated (not recently reinforced):[/dim]")
            for s in narrative.dormant_ai_skills:
                console.print(f"    • {s}")
        else:
            for s in narrative.foundation_skills:
                console.print(f"  • {s}")

    console.print("\n[bold]Confidence Summary[/bold]")
    console.print(f"  {narrative.confidence_summary}")

    console.print("\n[bold]Recommended Direction[/bold]")
    console.print(f"  {narrative.recommended_direction}")
    console.print()


@cli.command()
@click.option("--learner-id", default=None, help="Learner ID (defaults to active learner).")
@click.option("--detail", is_flag=True, default=False, help="Evidence-backed competency cards.")
@click.option("--matrix", is_flag=True, default=False, help="Raw current vs experience score matrix (old default view).")
def profile(learner_id: str | None, detail: bool, matrix: bool) -> None:
    """Builder profile: archetype, strengths, emerging skills, and direction.

    Default: an evidence-grounded narrative (archetype, strengths, emerging
    skills, foundation skills, confidence summary, recommended direction).
    --matrix: raw current vs experience score matrix with zone classification.
    --detail: evidence-backed competency cards per domain.
    """
    from .memory.store import load_state

    lid = resolve_learner_id(learner_id)
    state = load_state(lid)
    if state is None:
        console.print(f"[red]Learner [bold]{lid}[/bold] not found.[/red]")
        return

    if not state.evidence:
        console.print(
            "[yellow]No evidence yet. Run [bold]compass scan --repo <path>[/bold] first.[/yellow]"
        )
        return

    _print_header(state.profile)

    if detail:
        _print_competency_cards(state)
    elif matrix:
        _print_profile_matrix(state)
    else:
        _print_profile_narrative(state)


# ── compass story ─────────────────────────────────────────────────────────────

def _print_story(narrative) -> None:
    console.print()
    console.print(Panel.fit("Your Builder Journey", style="bold blue"))
    console.print()

    if narrative.insufficient_history:
        console.print(
            "[yellow]Not enough repository history yet to build a chronological story.[/yellow]\n"
            "[dim]Run [bold]compass run <repo>[/bold] against a git-tracked repo to begin.[/dim]"
        )
        console.print()
        return

    for chapter in narrative.chapters:
        console.print(f"[bold]{chapter.year}[/bold]")
        console.print(f"  {chapter.text}\n")

    console.print("[bold]Today[/bold]")
    console.print(f"  {narrative.today_text}\n")

    console.print("[bold]Likely Next Frontier[/bold]")
    console.print(f"  {narrative.next_frontier}")
    console.print()


@cli.command()
@click.option("--learner-id", default=None, help="Learner ID (defaults to active learner).")
def story(learner_id: str | None) -> None:
    """Chronological builder-journey narrative grounded in repo commit history.

    Built from real git commit dates (compass run populates these) and
    credited evidence per repo — never a fabricated timeline. If chronology
    data isn't available yet, says so explicitly instead of guessing.
    """
    from .agent.narrative import build_story_narrative
    from .memory.store import load_state

    lid = resolve_learner_id(learner_id)
    state = load_state(lid)
    if state is None:
        console.print(f"[red]Learner [bold]{lid}[/bold] not found.[/red]")
        return

    narrative = build_story_narrative(state)
    _print_story(narrative)


# ── compass coach ─────────────────────────────────────────────────────────────

def _print_coach(rec) -> None:
    console.print()
    console.print(Panel.fit("Compass Coach", style="bold blue"))

    if rec.mode == "no_evidence":
        console.print(f"\n[yellow]{rec.rationale}[/yellow]\n")
        return

    if rec.demonstrated:
        console.print("\n[bold]What you've demonstrated[/bold]")
        for s in rec.demonstrated:
            console.print(f"  • {s}")
        console.print(f"  [dim]Archetype: {rec.archetype}[/dim]")

    if rec.close_to_next:
        console.print("\n[bold]Also within reach right now[/bold]")
        for s in rec.close_to_next:
            console.print(f"  • {s}")

    if rec.target_skill_name:
        console.print(f"\n[bold]Learn next:[/bold] {rec.target_skill_name}  [dim]({rec.target_domain_name})[/dim]")
        console.print(f"\n[bold]Why[/bold]\n  {rec.rationale}")
        if rec.alternative_skill_name:
            alt_line = f"  [dim]Alternative: {rec.alternative_skill_name}[/dim]"
            if rec.alternative_rationale:
                alt_line += f" [dim]— {rec.alternative_rationale}[/dim]"
            console.print(f"\n{alt_line}")
        if rec.build_suggestion:
            console.print(f"\n[bold]What to build[/bold]\n  {rec.build_suggestion}")
        if rec.confirming_evidence:
            console.print("\n[bold]Evidence Compass will look for afterward[/bold]")
            for e in rec.confirming_evidence:
                console.print(f"  • {e}")
        if rec.source == "llm":
            console.print("\n[dim]Chosen by Compass Coach (AI-assisted, bounded to the planner's eligible/near-eligible set).[/dim]")
        elif rec.mode == "normal":
            reason = f" ({rec.fallback_reason})" if rec.fallback_reason else ""
            console.print(f"\n[dim]Rule-based pick — AI coaching unavailable this run{reason}.[/dim]")
    else:
        console.print(f"\n{rec.rationale}")

    console.print()


@cli.command()
@click.option("--learner-id", default=None, help="Learner ID (defaults to active learner).")
def coach(learner_id: str | None) -> None:
    """The coaching loop: what you've demonstrated, what to learn next, why, what to build, and what evidence will confirm it.

    The deterministic planner (plan_next_milestone) bounds the search space —
    eligible, near-eligible, and blocked-with-reasons skills. An LLM then
    provides coaching judgment: which of exactly those candidates is the
    best next step for this learner, and why. The LLM can never choose a
    skill outside that bounded set, and never generates the build suggestion
    or confirming evidence — those are always a deterministic lookup from
    build_suggestions.yaml / evidence_signals.yaml for whichever skill is
    chosen. Falls back to the planner's own top-priority pick if the LLM is
    unavailable or its choice fails validation.
    """
    from .agent.coach import build_coaching_recommendation
    from .memory.store import load_state

    lid = resolve_learner_id(learner_id)
    state = load_state(lid)
    if state is None:
        console.print(f"[red]Learner [bold]{lid}[/bold] not found.[/red]")
        return

    rec = build_coaching_recommendation(state)
    _print_coach(rec)


# ── compass learner ─────────────────────────────────────────────────────────
# New learner-centered coaching path — runs alongside the skill_graph/planner
# path above (compass run / recommend / coach), does not replace it. The
# learner is the unit of analysis here: a persistent model built from
# accumulated evidence across repos, docs, blogs, and reflections, not a
# single repo's skill inventory. See HANDOFF.md.

def _print_learner_profile(profile) -> None:
    console.print()
    console.print(Panel.fit(f"Learner Model — {profile.learner_id}", style="bold blue"))
    console.print(f"\n[bold]Goals[/bold]: {', '.join(profile.goals) or '(none stated)'}")

    if profile.strengths:
        console.print("\n[bold]Strengths[/bold]")
        for s in profile.strengths:
            console.print(f"  • {s.strength} [dim](confidence {s.confidence:.2f})[/dim]")

    if profile.growth_edges:
        console.print("\n[bold]Growth edges[/bold]")
        for g in profile.growth_edges:
            console.print(f"  • {g.growth_edge} [dim](confidence {g.confidence:.2f})[/dim]")

    if profile.uncertainties:
        console.print("\n[bold]Open uncertainties[/bold]")
        for u in profile.uncertainties:
            console.print(f"  • {u.uncertainty}")

    if profile.coach_beliefs:
        console.print("\n[bold]Coach beliefs[/bold]")
        for b in profile.coach_beliefs:
            console.print(f"  • {b.belief} [dim](confidence {b.confidence:.2f})[/dim]")

    if profile.learning_style:
        console.print(f"\n[bold]Learning style[/bold]: {', '.join(profile.learning_style)}")
    if profile.builder_patterns:
        console.print(f"[bold]Builder patterns[/bold]: {', '.join(profile.builder_patterns)}")

    console.print(f"\n[dim]Last updated: {profile.updated_at}[/dim]")
    console.print()


def _print_learner_assessment(assessment) -> None:
    console.print()
    console.print(Panel.fit("Coach Assessment", style="bold blue"))
    console.print(f"\n[bold]Stage[/bold]: {assessment.current_stage}")
    console.print(f"\n{assessment.coach_summary}")

    if assessment.demonstrated_capabilities:
        console.print("\n[bold]Demonstrated capabilities[/bold]")
        for c in assessment.demonstrated_capabilities:
            console.print(f"  • {c.capability} [dim](confidence {c.confidence:.2f})[/dim]")

    if assessment.growth_gaps:
        console.print("\n[bold]Growth gaps[/bold]")
        for g in assessment.growth_gaps:
            console.print(f"  • {g.gap} [dim](confidence {g.confidence:.2f})[/dim]")

    if assessment.uncertainties:
        console.print("\n[bold]Uncertainties[/bold]")
        for u in assessment.uncertainties:
            console.print(f"  • {u.uncertainty}")

    if assessment.source == "deterministic_fallback":
        console.print(f"\n[dim]Deterministic fallback — AI assessment unavailable this run ({assessment.fallback_reason}).[/dim]")
    console.print()


def _print_learner_recommendation(rec) -> None:
    console.print()
    console.print(Panel.fit("Next Challenge", style="bold blue"))
    console.print(f"\n[bold]{rec.next_challenge}[/bold]")
    console.print(f"\n[bold]Why[/bold]\n  {rec.why_this}")

    if rec.build_spec.required_capabilities or rec.build_spec.suggested_artifacts:
        console.print(f"\n[bold]Build[/bold]: {rec.build_spec.project_goal}")
        if rec.build_spec.required_capabilities:
            console.print(f"  Requires: {', '.join(rec.build_spec.required_capabilities)}")
        if rec.build_spec.suggested_artifacts:
            console.print(f"  Suggested artifacts: {', '.join(rec.build_spec.suggested_artifacts)}")

    if rec.success_criteria:
        console.print("\n[bold]Success criteria[/bold]")
        for c in rec.success_criteria:
            console.print(f"  • {c}")

    if rec.evidence_compass_will_look_for:
        console.print("\n[bold]Evidence Compass will look for[/bold]")
        for e in rec.evidence_compass_will_look_for:
            console.print(f"  • {e}")

    if rec.source == "deterministic_fallback":
        console.print(f"\n[dim]Deterministic fallback — AI recommendation unavailable this run ({rec.fallback_reason}).[/dim]")
    console.print()


@cli.group()
def learner() -> None:
    """Learner-centered coaching: a persistent learner model built from
    accumulated evidence (repos, docs, blogs, reflections) — the learner is
    the unit of analysis, not any single repository."""


@learner.command(name="init")
@click.argument("learner_id")
@click.option("--goal", default=None, help="A learning goal for this learner.")
def learner_init(learner_id: str, goal: str | None) -> None:
    """Create (or add a goal to) a learner-coach profile."""
    from .learner.coach import load_or_create_state
    from .learner.store import save_coach_state

    state = load_or_create_state(learner_id, goal)
    save_coach_state(state)
    console.print(f"[green]Learner-coach profile ready for [bold]{learner_id}[/bold].[/green]")
    console.print(f"Goals: {state.profile.goals or '(none stated)'}")


@learner.command(name="add-source")
@click.argument("learner_id")
@click.option("--github", "github_path", default=None, type=click.Path(exists=True, file_okay=False), help="Path to a local clone of a GitHub repo.")
@click.option("--doc", "doc_path", default=None, type=click.Path(exists=True, dir_okay=False), help="Path to a project doc/writeup.")
@click.option("--blog", "blog_path", default=None, type=click.Path(exists=True, dir_okay=False), help="Path to a blog post.")
@click.option("--reflection", "reflection_path", default=None, type=click.Path(exists=True, dir_okay=False), help="Path to a reflection note.")
def learner_add_source(
    learner_id: str,
    github_path: str | None,
    doc_path: str | None,
    blog_path: str | None,
    reflection_path: str | None,
) -> None:
    """Add one evidence source to a learner's evidence bundle."""
    from .learner.coach import load_or_create_state
    from .learner.evidence import collect_doc_evidence, collect_repo_evidence
    from .learner.store import save_coach_state

    given = [p for p in (github_path, doc_path, blog_path, reflection_path) if p]
    if len(given) != 1:
        console.print("[red]Pass exactly one of --github, --doc, --blog, --reflection.[/red]")
        sys.exit(1)

    state = load_or_create_state(learner_id)
    if github_path:
        source = collect_repo_evidence(Path(github_path))
    elif doc_path:
        source = collect_doc_evidence(Path(doc_path), "doc")
    elif blog_path:
        source = collect_doc_evidence(Path(blog_path), "blog")
    else:
        source = collect_doc_evidence(Path(reflection_path), "reflection")

    state.evidence_sources.append(source)
    save_coach_state(state)
    console.print(
        f"[green]Added {source.source_type} source '{source.source_name}' "
        f"— {len(source.items)} evidence item(s).[/green]"
    )


@learner.command(name="coach")
@click.argument("learner_id")
def learner_coach(learner_id: str) -> None:
    """Run the coach loop: assess the learner, update the learner model, recommend the next challenge."""
    from .learner.coach import run_coach

    try:
        state = run_coach(learner_id)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        sys.exit(1)

    cycle = state.latest_cycle
    _print_learner_assessment(cycle.assessment)
    _print_learner_recommendation(cycle.recommendation)


@learner.command(name="show")
@click.argument("learner_id")
def learner_show(learner_id: str) -> None:
    """Show the current learner-coach profile."""
    from .learner.store import load_coach_state

    state = load_coach_state(learner_id)
    if state is None:
        console.print(
            f"[red]No learner-coach profile for [bold]{learner_id}[/bold]. "
            "Run [bold]compass learner init[/bold] first.[/red]"
        )
        return

    _print_learner_profile(state.profile)


@learner.command(name="history")
@click.argument("learner_id")
@click.option("--cycle", "cycle_index", default=None, type=int, help="Show one cycle in full (1-based, as listed).")
def learner_history(learner_id: str, cycle_index: int | None) -> None:
    """List past coaching cycles, or show one in full with --cycle."""
    from .learner.store import load_coach_state

    state = load_coach_state(learner_id)
    if state is None:
        console.print(
            f"[red]No learner-coach profile for [bold]{learner_id}[/bold]. "
            "Run [bold]compass learner init[/bold] first.[/red]"
        )
        return
    if not state.history:
        console.print(f"[yellow]No coaching cycles yet for [bold]{learner_id}[/bold]. Run [bold]compass learner coach[/bold] first.[/yellow]")
        return

    if cycle_index is not None:
        if not 1 <= cycle_index <= len(state.history):
            console.print(f"[red]Cycle {cycle_index} out of range (1-{len(state.history)}).[/red]")
            return
        cycle = state.history[cycle_index - 1]
        _print_learner_assessment(cycle.assessment)
        _print_learner_recommendation(cycle.recommendation)
        return

    console.print()
    console.print(Panel.fit(f"Coaching History — {learner_id}", style="bold blue"))
    for i, cycle in enumerate(state.history, start=1):
        source_tag = "[dim](fallback)[/dim]" if cycle.assessment.source == "deterministic_fallback" else ""
        console.print(
            f"\n[bold]{i}.[/bold] {cycle.ran_at:%Y-%m-%d %H:%M} {source_tag}\n"
            f"   Stage: {cycle.assessment.current_stage}\n"
            f"   Next challenge: {cycle.recommendation.next_challenge}"
        )
    console.print(f"\n[dim]Use --cycle <n> to see one in full.[/dim]\n")
