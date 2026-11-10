"""Rolling service-time estimates; queue waits and paused time are excluded."""
import math
from statistics import mean


def duration(seconds):
    seconds = max(0, math.ceil(seconds))
    if seconds < 60:
        return f'{seconds}s'
    minutes = math.ceil(seconds / 60)
    if minutes < 60:
        return f'{minutes}m'
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f'{hours}h {minutes:02d}m'
    days, hours = divmod(hours, 24)
    return f'{days}d {hours:02d}h {minutes:02d}m'


def estimate(pending_prompts, remaining_images, missing_originals, capacity, averages,
             elapsed=None, has_ready=False):
    """Approximate pipeline makespan, accounting for its slower stage and bounded queue."""
    elapsed = elapsed or {}
    llm, original, background = (averages.get(key) for key in ('llm', 'original', 'background'))
    prompt_work = None if pending_prompts and llm is None else max(0, pending_prompts * (llm or 0) - elapsed.get('llm', 0))
    image_work = None
    if (not missing_originals or original is not None) and (not remaining_images or background is not None):
        image_work = (max(0, missing_originals * (original or 0) - elapsed.get('original', 0))
                      + max(0, remaining_images * (background or 0) - elapsed.get('background', 0)))
    prompt_eta = prompt_work
    if pending_prompts and prompt_eta is not None and original is not None and background is not None:
        # The producer cannot finish until enough image jobs have made queue space.
        prompt_eta = max(prompt_eta, max(0, remaining_images - capacity - 1) * (original + background))
    total_eta = image_work
    if remaining_images and pending_prompts:
        if prompt_work is None or image_work is None or original is None or background is None:
            total_eta = None
        else:
            # Last newly prepared prompt still needs its image; initial starvation
            # matters when the queue has no work available to the image worker.
            total_eta = max(image_work + (0 if has_ready else (llm or 0)),
                            prompt_work + original + background)
    if not remaining_images:
        total_eta = 0
    return prompt_eta, total_eta


def rolling_averages(rows):
    by_stage = {}
    for stage, seconds in rows:
        by_stage.setdefault(stage, []).append(seconds)
    return {stage: mean(values) for stage, values in by_stage.items()}
