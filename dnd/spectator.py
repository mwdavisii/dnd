import re


def _world_state_list(world_state: dict, key: str) -> list[str]:
    value = world_state.get(key, [])
    if isinstance(value, list):
        return [str(entry).strip() for entry in value if str(entry).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _get_current_beat_goal(world_state: dict) -> str:
    story_arc = world_state.get("story_arc") or {}
    current_beat = str(world_state.get("current_beat", "hook") or "hook")
    beat_data = story_arc.get(current_beat) or {}
    return str(beat_data.get("goal", "") or "")


def build_turn_context(
    world_state: dict,
    actor_name: str,
    actor_type: str,
    scene_summary: str,
    recent_party_actions: list[str] | None = None,
) -> dict:
    recent_actions = [str(action).strip() for action in (recent_party_actions or []) if str(action).strip()]
    current_round = int(world_state.get("current_round", 1) or 1)
    target_rounds = int(world_state.get("target_rounds", 0) or 0)
    remaining_rounds = int(world_state.get("remaining_rounds", max(target_rounds - current_round, 0)) or 0)
    pending_enemies = _world_state_list(world_state, "pending_encounter_enemies")
    notable_npcs = _world_state_list(world_state, "notable_npcs")
    nearby_locations = _world_state_list(world_state, "nearby_locations")
    resolved_events = _world_state_list(world_state, "resolved_events")
    last_progress_events = _world_state_list(world_state, "last_progress_events")
    pending_roll = world_state.get("pending_roll")
    scene_stall_count = int(world_state.get("scene_stall_count", 0) or 0)
    immediate_danger = "No immediate danger recorded."
    if pending_enemies:
        immediate_danger = f"Hostile pressure from: {', '.join(pending_enemies[:4])}."
    elif pending_roll and isinstance(pending_roll, dict):
        immediate_danger = f"Pending roll: {pending_roll.get('label', 'Resolve the requested check.')}"

    return {
        "actor_name": actor_name,
        "actor_type": actor_type,
        "location": world_state.get("current_location") or world_state.get("location") or "Unknown",
        "objective": world_state.get("objective") or "No objective recorded.",
        "story_phase": world_state.get("story_phase") or "opening",
        "current_round": current_round,
        "target_rounds": target_rounds,
        "remaining_rounds": remaining_rounds,
        "phase_goal": phase_goal(world_state.get("story_phase") or "opening", remaining_rounds),
        "immediate_danger": immediate_danger,
        "scene_momentum": momentum_label(scene_stall_count),
        "scene_stall_count": scene_stall_count,
        "scene_summary": scene_summary or "No scene summary recorded yet.",
        "recent_party_actions": recent_actions[-3:],
        "notable_npcs": notable_npcs[:4],
        "nearby_locations": nearby_locations[:4],
        "resolved_events": resolved_events[-4:],
        "last_progress_events": last_progress_events[-3:],
        "focus_keywords": focus_keywords(
            world_state.get("objective") or "",
            scene_summary or "",
            notable_npcs[:4],
            nearby_locations[:4],
        ),
        "current_beat_goal": _get_current_beat_goal(world_state),
        "story_summary": str(world_state.get("story_summary", "") or ""),
    }


def format_turn_context(turn_context: dict) -> str:
    def render_list(label: str, values: list[str]) -> str:
        if not values:
            return f"{label}: none"
        return f"{label}: " + "; ".join(values)

    return "\n".join(
        [
            f"Actor: {turn_context['actor_name']} ({turn_context['actor_type']})",
            f"Location: {turn_context['location']}",
            f"Objective: {turn_context['objective']}",
            (
                "Pacing: "
                f"round {turn_context['current_round']} of {turn_context['target_rounds'] or '?'}"
                f", {turn_context['story_phase']}, {turn_context['remaining_rounds']} rounds remaining"
            ),
            f"Phase goal: {turn_context['phase_goal']}",
            f"Current beat goal: {turn_context.get('current_beat_goal', '')}",
            f"Story summary: {turn_context.get('story_summary', 'No summary yet.')}",
            f"Scene momentum: {turn_context['scene_momentum']}",
            f"Immediate danger: {turn_context['immediate_danger']}",
            f"Scene summary: {turn_context['scene_summary']}",
            render_list("Recent party actions", turn_context.get("recent_party_actions", [])),
            render_list("Recent progress", turn_context.get("last_progress_events", [])),
            render_list("Resolved events", turn_context.get("resolved_events", [])),
            render_list("Notable NPCs", turn_context.get("notable_npcs", [])),
            render_list("Nearby locations", turn_context.get("nearby_locations", [])),
        ]
    )


def extract_open_threads(story_summary: str) -> str:
    """Extract the OPEN THREADS section from a rolling story summary."""
    if not story_summary or "OPEN THREADS" not in story_summary:
        return ""
    match = re.search(r"OPEN THREADS:\s*\n(.*?)(?:\n\n|\nESCALATION|\Z)", story_summary, re.DOTALL)
    if not match:
        return ""
    return match.group(1).strip()


def build_scene_memory(user_input: str, response: str) -> str:
    cleaned = re.sub(r"<[^>]+>", " ", response)
    cleaned = re.sub(r"\bWhat do you do next\?\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bWhat action do you take\?\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bOutcome:\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        cleaned = "The scene changes, but the details are unclear."
    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    summary = " ".join(sentence.strip() for sentence in sentences[:3] if sentence.strip())
    if len(summary) > 220:
        summary = summary[:217].rstrip() + "..."
    return f"Last turn: {user_input} Consequences: {summary}"


def validate_turn_output(
    action: str,
    actor_name: str,
    actor_type: str,
    recent_party_actions: list[str] | None = None,
    turn_context: dict | None = None,
    fallback: str | None = None,
) -> str:
    cleaned = (action or "").strip()
    if not cleaned:
        return fallback or default_fallback_action(actor_name, actor_type, turn_context)

    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = re.sub(r"\*\*", "", cleaned)
    cleaned = re.sub(rf"^(?:{re.escape(actor_name)}\s*:\s*)+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(?:Assistant|DM|Narrator)\s*:\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<[^>]*thinking[^>]*>", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:What do you do next\?|What action do you take\?)\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bOutcome:\b.*", " ", cleaned, flags=re.IGNORECASE)
    cleaned = " ".join(cleaned.split())
    cleaned = _strip_other_speaker_labels(cleaned, actor_name)

    if _contains_non_latin_script(cleaned):
        return fallback or default_fallback_action(actor_name, actor_type, turn_context)
    if not cleaned or len(cleaned.split()) < 3:
        return fallback or suggest_objective_action(actor_name, actor_type, turn_context)

    normalized_recent = {
        _normalize_for_comparison(entry.split(" acted: ", 1)[-1])
        for entry in (recent_party_actions or [])[-3:]
    }
    if _normalize_for_comparison(cleaned) in normalized_recent:
        return fallback or suggest_objective_action(actor_name, actor_type, turn_context)

    if turn_context and action_abandons_objective(cleaned, turn_context):
        return fallback or suggest_objective_action(actor_name, actor_type, turn_context)

    if len(cleaned) > 180:
        cleaned = cleaned[:177].rstrip() + "..."
    return cleaned


_FALLBACK_MARKER = "[fallback]"


def is_fallback_action(action: str) -> bool:
    """Return True if the action was generated by the fallback system, not the LLM."""
    return action.endswith(_FALLBACK_MARKER)


def _mark_fallback(action: str) -> str:
    """Tag an action so callers can detect it was a fallback."""
    return f"{action} {_FALLBACK_MARKER}"


def _strip_fallback_marker(action: str) -> str:
    """Remove the fallback marker for display purposes."""
    if action.endswith(_FALLBACK_MARKER):
        return action[: -len(_FALLBACK_MARKER)].rstrip()
    return action


_PHASE_FALLBACKS_COMPANION = {
    "opening": [
        "I scan the area for tracks, marks, or anything out of place.",
        "I move ahead to check the nearest doorway for danger.",
        "I listen carefully and report what I hear to the group.",
    ],
    "midgame": [
        "I press the nearest figure for answers, demanding to know what they know.",
        "I search for a hidden passage or alternate route around the obstacle.",
        "I move to flank the threat, cutting off its escape.",
    ],
    "climax": [
        "I charge the main threat, weapon raised, aiming to strike.",
        "I move to shield the most vulnerable ally and brace for impact.",
        "I rush forward and attack, trying to end this now.",
    ],
    "resolution": [
        "I check the fallen enemy to make sure the threat is truly over.",
        "I tend to the wounded and secure the area.",
        "I gather what's left behind and signal that we should move on.",
    ],
}

_PHASE_FALLBACKS_PLAYER = {
    "opening": [
        "{name} approaches the nearest lead and asks for more information.",
        "{name} examines the scene closely, looking for clues.",
    ],
    "midgame": [
        "{name} presses forward toward the heart of the problem.",
        "{name} confronts the obstacle head-on, looking for a way through.",
    ],
    "climax": [
        "{name} charges the main threat, weapon ready.",
        "{name} strikes at the enemy, committing fully to the fight.",
    ],
    "resolution": [
        "{name} surveys the aftermath and helps secure the area.",
        "{name} checks on allies and looks for anything left behind.",
    ],
}

_phase_fallback_index = 0


def default_fallback_action(actor_name: str, actor_type: str, turn_context: dict | None = None) -> str:
    global _phase_fallback_index
    phase = "opening"
    if turn_context:
        phase = str(turn_context.get("story_phase", "opening") or "opening")

    if actor_type == "companion":
        options = _PHASE_FALLBACKS_COMPANION.get(phase, _PHASE_FALLBACKS_COMPANION["opening"])
    else:
        options = _PHASE_FALLBACKS_PLAYER.get(phase, _PHASE_FALLBACKS_PLAYER["opening"])

    action = options[_phase_fallback_index % len(options)]
    _phase_fallback_index += 1

    if actor_type != "companion":
        action = action.format(name=actor_name)

    return _mark_fallback(action)


def suggest_objective_action(actor_name: str, actor_type: str, turn_context: dict | None = None) -> str:
    if not turn_context:
        return default_fallback_action(actor_name, actor_type, turn_context)
    objective = str(turn_context.get("objective", "")).strip()
    nearby_locations = turn_context.get("nearby_locations", []) or []
    notable_npcs = turn_context.get("notable_npcs", []) or []
    phase = str(turn_context.get("story_phase", "opening") or "opening")
    if actor_type == "companion":
        if phase in ("climax", "resolution"):
            return default_fallback_action(actor_name, actor_type, turn_context)
        if notable_npcs:
            return _mark_fallback(f"I focus on {notable_npcs[0]}, stay on the main lead, and point out the safest next move.")
        return default_fallback_action(actor_name, actor_type, turn_context)
    if nearby_locations:
        return _mark_fallback(f"{actor_name} stays on the main lead, moves toward {nearby_locations[0]}, and looks for the fastest way to advance.")
    if objective:
        return _mark_fallback(f"{actor_name} commits to the active objective, presses for a key answer, and keeps the scene moving.")
    return default_fallback_action(actor_name, actor_type, turn_context)


def phase_goal(story_phase: str, remaining_rounds: int) -> str:
    if remaining_rounds <= 2:
        return "Force a decisive confrontation, rescue, escape, or clear ending."
    if story_phase == "opening":
        return "Commit to the hook, gather one key fact, and move toward the first threat."
    if story_phase == "midgame":
        return "Escalate pressure, reveal a complication, or force a meaningful choice."
    if story_phase == "climax":
        return "Bring the main threat into direct conflict or reveal the decisive truth."
    return "Resolve the central problem, show consequences, and close the scene."


def momentum_label(scene_stall_count: int) -> str:
    if scene_stall_count >= 3:
        return "stalled - force a reveal, attack, deadline, or irreversible change now"
    if scene_stall_count >= 1:
        return "slow - avoid repeating the same cautious beat"
    return "steady"


def detect_scene_stall(
    previous_summary: str,
    new_summary: str,
    new_progress_events: list[str] | None = None,
    previous_threads: str = "",
    current_threads: str = "",
) -> bool:
    if new_progress_events:
        return False

    # Primary signal: compare open threads from story summary
    if previous_threads and current_threads:
        prev_tokens = set(_normalize_for_comparison(previous_threads).split())
        curr_tokens = set(_normalize_for_comparison(current_threads).split())
        if prev_tokens and curr_tokens:
            thread_overlap = len(prev_tokens & curr_tokens) / max(len(prev_tokens | curr_tokens), 1)
            if thread_overlap >= 0.70:
                return True

    # Fallback: existing scene summary overlap check
    previous = _normalize_for_comparison(previous_summary)
    current = _normalize_for_comparison(new_summary)
    if not previous or not current:
        return False
    previous_tokens = set(previous.split())
    current_tokens = set(current.split())
    if not previous_tokens or not current_tokens:
        return False
    overlap = len(previous_tokens & current_tokens) / max(len(previous_tokens | current_tokens), 1)
    return overlap >= 0.55


def focus_keywords(objective: str, scene_summary: str, notable_npcs: list[str], nearby_locations: list[str]) -> list[str]:
    combined = " ".join([objective, scene_summary, " ".join(notable_npcs), " ".join(nearby_locations)])
    tokens = [token for token in re.findall(r"[A-Za-z]{4,}", combined.lower()) if token not in _STOPWORDS]
    seen = []
    for token in tokens:
        if token not in seen:
            seen.append(token)
    return seen[:16]


def action_abandons_objective(action: str, turn_context: dict) -> bool:
    focus = set(turn_context.get("focus_keywords", []))
    if not focus:
        return False
    action_tokens = {token for token in re.findall(r"[A-Za-z]{4,}", action.lower()) if token not in _STOPWORDS}
    if not action_tokens:
        return False
    if action_tokens & focus:
        return False
    story_phase = str(turn_context.get("story_phase", "opening"))
    if story_phase in {"climax", "resolution"}:
        return True
    opening_midgame_verbs = {
        "browse", "window", "shop", "stall", "counter"
    }
    if action_tokens & opening_midgame_verbs:
        return True
    return False


_ROLE_LABELS = {"assistant", "dm", "narrator", "player", "companion", "outcome", "result"}


def _strip_other_speaker_labels(text: str, actor_name: str) -> str:
    # Only inspect a leading "Word: " pattern — mid-sentence colons (e.g. "Move to Mill: ...") are not speaker labels.
    speaker_pattern = re.compile(r"^([A-Z][a-zA-Z'-]{1,20})\s*:\s*")
    match = speaker_pattern.match(text)
    if not match:
        return text
    speaker = match.group(1)
    if speaker.lower() == actor_name.lower():
        return text[match.end():].strip()
    # Discard only if the label is a known role word or looks like another character name.
    # Unknown words (e.g. "Move:", "Option:", "Note:") are left in place.
    if speaker.lower() in _ROLE_LABELS:
        return ""
    return text


def _normalize_for_comparison(text: str) -> str:
    text = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    return " ".join(text.split())


def _contains_non_latin_script(text: str) -> bool:
    return bool(re.search(r"[\u0400-\u052F\u0590-\u05FF\u0600-\u06FF\u0900-\u0D7F\u3040-\u30FF\u3400-\u9FFF\uAC00-\uD7AF]", text))


_STOPWORDS = {
    "about", "above", "across", "after", "again", "against", "almost", "along", "already", "also", "another",
    "around", "because", "before", "being", "between", "could", "enough", "follow", "from", "further", "guard",
    "into", "just", "keep", "look", "more", "near", "need", "next", "only", "other", "over", "quick", "ready",
    "seems", "some", "than", "that", "their", "them", "then", "there", "these", "they", "this", "toward",
    "under", "until", "very", "what", "when", "where", "which", "while", "with", "would", "your",
}
