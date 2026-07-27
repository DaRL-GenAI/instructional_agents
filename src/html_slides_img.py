"""Best-effort dynamic image generation for frontend slide artifacts."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from src.agents import Agent, LLM
from src.html_slides_style import (
    CourseSlideStyle,
    IMAGE_VISUAL_TYPES,
    ImageGuidance,
)


IMAGE_CONFIG_FILENAME = "course_image_generation.json"
IMAGE_MANIFEST_FILENAME = "image-manifest.json"
IMAGE_STATISTICS_FILENAME = "statistics_slide_images.json"
IMAGE_CONFIG_SCHEMA_VERSION = 1
IMAGE_MANIFEST_SCHEMA_VERSION = 2
IMAGE_PIPELINE_VERSION = "slide-images-2026-07-23-v2"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
TEXT_FREE_PROMPT_SUFFIX = (
    " The pixels must contain absolutely no text, letters, numbers, labels, "
    "captions, logos, watermarks, UI chrome, or identifiable real people. "
    "Any requested labels or legend content will be rendered separately in HTML."
)


@dataclass(frozen=True)
class ImageGenerationConfig:
    enabled: bool = False
    max_images_per_chapter: int = 3
    ai_decides_image_count: bool = False
    model: str = "gpt-image-2"
    size: str = "1536x864"
    quality: str = "medium"
    estimated_cost_per_image_usd: float = 0.06
    replace_images: bool = False
    max_images_override: int | None = None

    def validated(self) -> "ImageGenerationConfig":
        if (
            not isinstance(self.enabled, bool)
            or not isinstance(self.replace_images, bool)
            or not isinstance(self.ai_decides_image_count, bool)
        ):
            raise ValueError(
                "Image enable, replacement, and AI-count values must be booleans."
            )
        if (
            isinstance(self.max_images_per_chapter, bool)
            or not isinstance(self.max_images_per_chapter, int)
            or not 0 <= self.max_images_per_chapter <= 3
        ):
            raise ValueError("max_images_per_chapter must be an integer from 0 to 3.")
        if (
            self.max_images_override is not None
            and (
                isinstance(self.max_images_override, bool)
                or not isinstance(self.max_images_override, int)
                or not 0 <= self.max_images_override <= 3
            )
        ):
            raise ValueError("max_images_override must be an integer from 0 to 3.")
        if not isinstance(self.model, str) or not self.model.strip():
            raise ValueError("Image model must be a nonempty string.")
        if not re.fullmatch(r"\d+x\d+", self.size):
            raise ValueError("Image size must use WIDTHxHEIGHT syntax.")
        width, height = (int(value) for value in self.size.split("x", 1))
        if width % 16 or height % 16 or width < 1 or height < 1:
            raise ValueError("Image dimensions must be positive multiples of 16.")
        if width * 9 != height * 16:
            raise ValueError("Image dimensions must use a true 16:9 aspect ratio.")
        if self.quality not in {"low", "medium", "high", "auto"}:
            raise ValueError("Image quality must be low, medium, high, or auto.")
        if (
            isinstance(self.estimated_cost_per_image_usd, bool)
            or not isinstance(self.estimated_cost_per_image_usd, (int, float))
            or self.estimated_cost_per_image_usd < 0
        ):
            raise ValueError("Estimated image cost must be nonnegative.")
        return self

    @property
    def effective_operator_cap(self) -> int | None:
        if self.max_images_override is not None:
            return self.max_images_override
        if self.ai_decides_image_count:
            return None
        return self.max_images_per_chapter


@dataclass(frozen=True)
class GeneratedImageRecord:
    slide_index: int
    concept: str
    visual_type: str
    labels: list[str]
    prompt: str
    prompt_sha256: str
    file: str
    data_uri: str = field(repr=False, compare=False)

    def manifest_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("data_uri", None)
        return payload


@dataclass
class ChapterImageResult:
    attempted: int = 0
    generated: int = 0
    reused_from_cache: bool = False
    replaced: bool = False
    committed: bool = False
    elapsed_time: float = 0.0
    token_usage: int = 0
    estimated_cost_usd: float = 0.0
    warnings: list[str] = field(default_factory=list)
    slides: list[int] = field(default_factory=list)
    images: list[GeneratedImageRecord] = field(default_factory=list)
    request_fingerprint: str = ""
    pending_manifest: dict[str, Any] | None = field(default=None, repr=False)
    pending_files: list[Path] = field(default_factory=list, repr=False)
    previous_files: list[str] = field(default_factory=list, repr=False)

    def statistics_dict(self) -> dict[str, Any]:
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "attempted": self.attempted,
            "generated": 0 if self.reused_from_cache else self.generated,
            "current_image_count": self.generated,
            "reused_from_cache": self.reused_from_cache,
            "replaced": self.replaced,
            "committed": self.committed,
            "elapsed_time": self.elapsed_time,
            "token_usage": self.token_usage,
            "estimated_cost_usd": self.estimated_cost_usd,
            "slides": self.slides,
            "warnings": self.warnings,
            "request_fingerprint": self.request_fingerprint,
        }


def load_image_generation_config(
    course_dir: Path | str,
) -> ImageGenerationConfig:
    path = Path(course_dir) / IMAGE_CONFIG_FILENAME
    if not path.is_file():
        return ImageGenerationConfig()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("configuration must be a JSON object")
        allowed_fields = {
            "schema_version",
            "enabled",
            "max_images_per_chapter",
            "ai_decides_image_count",
            "model",
            "size",
            "quality",
            "estimated_cost_per_image_usd",
        }
        unknown_fields = sorted(set(raw) - allowed_fields)
        if unknown_fields:
            raise ValueError(
                "unsupported image configuration fields: "
                + ", ".join(unknown_fields)
            )
        if raw.get("schema_version") != IMAGE_CONFIG_SCHEMA_VERSION:
            raise ValueError("unsupported image configuration schema")
        config = ImageGenerationConfig(
            enabled=raw.get("enabled", False),
            max_images_per_chapter=raw.get("max_images_per_chapter", 3),
            ai_decides_image_count=raw.get("ai_decides_image_count", False),
            model=raw.get("model", "gpt-image-2"),
            size=raw.get("size", "1536x864"),
            quality=raw.get("quality", "medium"),
            estimated_cost_per_image_usd=raw.get(
                "estimated_cost_per_image_usd", 0.06
            ),
        )
        return config.validated()
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ValueError(f"Cannot load {path}: {exc}") from exc


def write_image_generation_config(
    course_dir: Path | str,
    config: ImageGenerationConfig,
) -> Path:
    config = config.validated()
    path = Path(course_dir) / IMAGE_CONFIG_FILENAME
    payload = {
        "schema_version": IMAGE_CONFIG_SCHEMA_VERSION,
        "enabled": config.enabled or config.replace_images,
        "max_images_per_chapter": config.max_images_per_chapter,
        "ai_decides_image_count": config.ai_decides_image_count,
        "model": config.model,
        "size": config.size,
        "quality": config.quality,
        "estimated_cost_per_image_usd": config.estimated_cost_per_image_usd,
    }
    _atomic_write(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return path


def configured_for_invocation(
    stored: ImageGenerationConfig,
    *,
    enable: bool = False,
    replace_images: bool = False,
    max_images_override: int | None = None,
    ai_decides_image_count: bool | None = None,
) -> ImageGenerationConfig:
    resolved = replace(
        stored,
        enabled=stored.enabled or enable or replace_images,
        replace_images=replace_images,
        max_images_override=max_images_override,
        ai_decides_image_count=(
            stored.ai_decides_image_count
            if ai_decides_image_count is None
            else ai_decides_image_count
        ),
    )
    return resolved.validated()


def style_has_explicit_image_guidance(course_dir: Path | str) -> bool:
    path = Path(course_dir) / "course_slide_style.json"
    if not path.is_file():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(payload, dict) and isinstance(
        payload.get("image_guidance"), dict
    )


def effective_cap(
    config: ImageGenerationConfig, guidance: ImageGuidance
) -> int | None:
    operator_cap = config.validated().effective_operator_cap
    if operator_cap is None:
        return None
    if guidance.max_images_per_chapter is None:
        return operator_cap
    return min(operator_cap, guidance.max_images_per_chapter)


def image_request_fingerprint(
    *,
    source_sha256: str,
    style_sha256: str,
    chapter: dict[str, str] | None,
    config: ImageGenerationConfig,
    guidance: ImageGuidance,
) -> str:
    payload = {
        "pipeline_version": IMAGE_PIPELINE_VERSION,
        "source_sha256": source_sha256,
        "style_sha256": style_sha256,
        "chapter": {
            "title": str((chapter or {}).get("title", "")),
            "description": str((chapter or {}).get("description", "")),
        },
        "enabled": config.enabled,
        "guidance_enabled": guidance.enabled,
        "effective_cap": effective_cap(config, guidance),
        "model": config.model,
        "size": config.size,
        "quality": config.quality,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def desired_image_state(
    config: ImageGenerationConfig, guidance: ImageGuidance
) -> bool:
    cap = effective_cap(config, guidance)
    return bool(
        config.enabled
        and guidance.enabled
        and (cap is None or cap > 0)
    )


def image_cache_is_current(
    chapter_path: Path,
    request_fingerprint: str,
) -> bool:
    manifest = _read_image_manifest(chapter_path)
    return _manifest_is_current(chapter_path, manifest, request_fingerprint)


def augment_deck_with_generated_images(
    deck: Any,
    *,
    chapter_path: Path,
    style: CourseSlideStyle,
    chapter: dict[str, str] | None,
    llm: LLM | None,
    config: ImageGenerationConfig,
    source_sha256: str,
    style_sha256: str,
) -> ChapterImageResult:
    """Mutate ``deck`` with generated images; never raise."""
    started = time.time()
    result = ChapterImageResult(replaced=config.replace_images)
    try:
        config = config.validated()
        fingerprint = image_request_fingerprint(
            source_sha256=source_sha256,
            style_sha256=style_sha256,
            chapter=chapter,
            config=config,
            guidance=style.image_guidance,
        )
        result.request_fingerprint = fingerprint
        if not desired_image_state(config, style.image_guidance):
            old_manifest = _read_image_manifest(chapter_path)
            old_placements = old_manifest.get("placements", [])
            if isinstance(old_placements, list) and old_placements:
                result.previous_files = [
                    str(entry.get("file", ""))
                    for entry in old_placements
                    if isinstance(entry, dict)
                ]
                result.pending_manifest = {
                    "schema_version": IMAGE_MANIFEST_SCHEMA_VERSION,
                    "pipeline_version": IMAGE_PIPELINE_VERSION,
                    "request_fingerprint": fingerprint,
                    "source_sha256": source_sha256,
                    "style_sha256": style_sha256,
                    "configuration": {
                        "model": config.model,
                        "size": config.size,
                        "quality": config.quality,
                        "effective_cap": effective_cap(
                            config, style.image_guidance
                        ),
                    },
                    "placements": [],
                }
            else:
                result.committed = True
            result.elapsed_time = time.time() - started
            return result

        old_manifest = _read_image_manifest(chapter_path)
        old_current = _manifest_is_current(
            chapter_path, old_manifest, fingerprint
        )
        if old_current and not config.replace_images:
            records = _records_from_manifest(chapter_path, old_manifest)
            _attach_records(deck, records, result.warnings)
            result.reused_from_cache = True
            result.committed = True
            result.images = records
            result.generated = len(records)
            result.slides = [record.slide_index for record in records]
            result.elapsed_time = time.time() - started
            return result

        prior_records = _records_from_manifest(chapter_path, old_manifest)
        result.previous_files = [
            str(entry.get("file", ""))
            for entry in old_manifest.get("placements", [])
            if isinstance(entry, dict)
        ]
        if llm is None:
            result.warnings.append(
                "Image generation was enabled, but no LLM client was supplied; "
                "no image calls were made."
            )
            if config.replace_images and prior_records:
                _attach_records(deck, prior_records, result.warnings)
                result.reused_from_cache = True
                result.committed = True
                result.images = prior_records
                result.generated = len(prior_records)
                result.slides = [
                    record.slide_index for record in prior_records
                ]
            result.elapsed_time = time.time() - started
            return result

        placements, placement_tokens, placement_warnings, valid_selection = (
            _plan_placements(
                deck,
                chapter=chapter,
                guidance=style.image_guidance,
                llm=llm,
                cap=effective_cap(config, style.image_guidance),
            )
        )
        result.token_usage += placement_tokens
        result.warnings.extend(placement_warnings)
        if not valid_selection:
            if config.replace_images and prior_records:
                _attach_records(deck, prior_records, result.warnings)
                result.reused_from_cache = True
                result.committed = True
                result.images = prior_records
                result.generated = len(prior_records)
                result.slides = [record.slide_index for record in prior_records]
            result.elapsed_time = time.time() - started
            return result

        prompts, prompt_tokens, prompt_warnings = _write_prompts(
            placements, style=style, llm=llm
        )
        result.token_usage += prompt_tokens
        result.warnings.extend(prompt_warnings)
        result.attempted = len(prompts)
        (
            generated,
            generation_warnings,
            pending_files,
            billable_generations,
        ) = _generate_images(
            prompts,
            chapter_path=chapter_path,
            llm=llm,
            config=config,
        )
        result.warnings.extend(generation_warnings)
        result.estimated_cost_usd = round(
            billable_generations * config.estimated_cost_per_image_usd, 6
        )

        if (
            config.replace_images
            and prior_records
            and len(generated) != len(prompts)
        ):
            for path in pending_files:
                path.unlink(missing_ok=True)
            _attach_records(deck, prior_records, result.warnings)
            result.warnings.append(
                "Replacement was incomplete; retained the previous image set."
            )
            result.reused_from_cache = True
            result.committed = True
            result.images = prior_records
            result.generated = len(prior_records)
            result.slides = [record.slide_index for record in prior_records]
            result.elapsed_time = time.time() - started
            return result

        if prompts and not generated:
            result.elapsed_time = time.time() - started
            return result

        _attach_records(deck, generated, result.warnings)
        result.images = generated
        result.generated = len(generated)
        result.slides = [record.slide_index for record in generated]
        result.pending_files = pending_files
        result.pending_manifest = {
            "schema_version": IMAGE_MANIFEST_SCHEMA_VERSION,
            "pipeline_version": IMAGE_PIPELINE_VERSION,
            "request_fingerprint": fingerprint,
            "source_sha256": source_sha256,
            "style_sha256": style_sha256,
            "configuration": {
                "model": config.model,
                "size": config.size,
                "quality": config.quality,
                "effective_cap": effective_cap(
                    config, style.image_guidance
                ),
            },
            "placements": [record.manifest_dict() for record in generated],
        }
    except Exception as exc:
        result.warnings.append(f"Dynamic image generation failed: {exc}")
    result.elapsed_time = time.time() - started
    return result


def commit_image_result(chapter_path: Path, result: ChapterImageResult) -> None:
    if result.pending_manifest is None:
        return
    images_dir = chapter_path / "html" / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = images_dir / IMAGE_MANIFEST_FILENAME
    _atomic_write(
        manifest_path,
        json.dumps(result.pending_manifest, indent=2, sort_keys=True) + "\n",
    )
    active = {
        str(entry.get("file", ""))
        for entry in result.pending_manifest.get("placements", [])
        if isinstance(entry, dict)
    }
    cleanup_candidates = {
        images_dir / Path(old_file).name
        for old_file in result.previous_files
        if old_file
    }
    cleanup_candidates.update(images_dir.glob("img-*.png"))
    for candidate in cleanup_candidates:
        if candidate.name not in active:
            try:
                candidate.unlink(missing_ok=True)
            except OSError as exc:
                result.warnings.append(
                    f"Could not remove unreferenced image {candidate.name}: {exc}"
                )
    result.pending_manifest = None
    result.pending_files.clear()
    result.committed = True


def discard_image_result(result: ChapterImageResult) -> None:
    for path in result.pending_files:
        path.unlink(missing_ok=True)
    result.pending_files.clear()
    result.pending_manifest = None


def append_image_statistics(
    chapter_path: Path, result: ChapterImageResult
) -> Path:
    """Append one invocation record without changing the current asset manifest."""
    path = chapter_path / IMAGE_STATISTICS_FILENAME
    ledger: dict[str, Any] = {"schema_version": 1, "runs": []}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if (
                isinstance(loaded, dict)
                and loaded.get("schema_version") == 1
                and isinstance(loaded.get("runs"), list)
            ):
                ledger = loaded
        except (OSError, json.JSONDecodeError):
            pass
    ledger["runs"].append(result.statistics_dict())
    _atomic_write(path, json.dumps(ledger, indent=2, sort_keys=True) + "\n")
    return path


def _plan_placements(
    deck: Any,
    *,
    chapter: dict[str, str] | None,
    guidance: ImageGuidance,
    llm: LLM,
    cap: int | None,
) -> tuple[list[dict[str, Any]], int, list[str], bool]:
    warnings: list[str] = []
    tokens = 0
    outline = _deck_outline(deck)
    image_count_policy = {
        "mode": "ai_decides" if cap is None else "capped",
        "maximum": cap,
    }
    guidance_payload = asdict(guidance)
    if cap is None:
        guidance_payload["max_images_per_chapter"] = None
    count_instruction = (
        "The image count is delegated to you without a numeric chapter budget; "
        "propose every strong eligible opportunity."
        if cap is None
        else f"Do not propose more than the chapter maximum of {cap}."
    )
    context = json.dumps(
        {
            "chapter": chapter or {},
            "guidance": guidance_payload,
            "image_count_policy": image_count_policy,
            "slides": outline,
        },
        ensure_ascii=False,
    )
    lenses = {
        "pedagogy": (
            "Find abstract concepts, processes, relationships, or structures that "
            "would become easier to understand through one clear figure."
        ),
        "engagement": (
            "Find dry or text-heavy moments where a relevant visual metaphor or "
            "scene would improve recall without distorting the content."
        ),
    }

    def run_scout(name: str, lens: str) -> tuple[list[dict[str, Any]], int, list[str], bool]:
        payload, used, local_warnings, valid = _call_json_agent(
            llm,
            name=f"Image Scout — {name}",
            role="Teaching Assistant — Visual Opportunity Scout",
            system_prompt=(
                "You decide where text-free AI-generated imagery genuinely improves "
                f"a slide deck. {lens} Few or zero suggestions is correct. Never "
                "suggest title slides or technically dominated slides. "
                f"{count_instruction}"
            ),
            prompt=context,
            output_constraint=_placement_contract("suggestions", len(deck.slides)),
            validator=lambda value: _validate_payload_list(value, "suggestions"),
        )
        return (
            payload.get("suggestions", []) if payload else [],
            used,
            local_warnings,
            valid,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(run_scout, name, lens)
            for name, lens in lenses.items()
        ]
        scout_results = [future.result() for future in futures]
    scouts: list[list[dict[str, Any]]] = []
    for entries, used, local_warnings, valid in scout_results:
        tokens += used
        warnings.extend(local_warnings)
        if valid:
            filtered, filtered_warnings = _filter_placements(
                entries, deck, guidance
            )
            scouts.append(filtered)
            warnings.extend(filtered_warnings)
    if not any(scouts):
        return [], tokens, warnings, all(item[3] for item in scout_results)

    payload, used, local_warnings, valid = _call_json_agent(
        llm,
        name="Image Placement Referee",
        role="Teaching Assistant — Image Placement Referee",
        system_prompt=(
            "Merge two image-placement reports. Keep only images that materially "
            "improve learning, at most one per slide, and return an empty list if "
            "none is strong enough. When image_count_policy.mode is ai_decides, "
            "keep every strong eligible placement without applying a numeric "
            "chapter budget."
        ),
        prompt=json.dumps(
            {
                "slides": outline,
                "image_count_policy": image_count_policy,
                "scout_reports": scouts,
            },
            ensure_ascii=False,
        ),
        output_constraint=_placement_contract("placements", len(deck.slides)),
        validator=lambda value: _validate_payload_list(value, "placements"),
    )
    tokens += used
    warnings.extend(local_warnings)
    if not valid or payload is None:
        return [], tokens, warnings, False
    placements, filtered_warnings = _filter_placements(
        payload["placements"], deck, guidance
    )
    warnings.extend(filtered_warnings)
    deduped: list[dict[str, Any]] = []
    seen: set[int] = set()
    for placement in placements:
        if placement["slide_index"] in seen:
            warnings.append(
                f"Dropped duplicate image placement for slide {placement['slide_index']}."
            )
            continue
        seen.add(placement["slide_index"])
        deduped.append(placement)
    selected = deduped if cap is None else deduped[:cap]
    return selected, tokens, warnings, True


def _write_prompts(
    placements: list[dict[str, Any]],
    *,
    style: CourseSlideStyle,
    llm: LLM,
) -> tuple[list[dict[str, Any]], int, list[str]]:
    if not placements:
        return [], 0, []
    indexes = [entry["slide_index"] for entry in placements]
    colors = style.render_theme.colors
    payload, tokens, warnings, valid = _call_json_agent(
        llm,
        name="Image Prompt Writer",
        role="Teaching Assistant — Image Prompt Writer",
        system_prompt=(
            "Write one GPT Image prompt per placement. Use a true 16:9 composition "
            "with generous negative space. The pixels must contain no text, letters, "
            "numbers, labels, captions, logos, watermarks, UI chrome, or identifiable "
            "real people."
        ),
        prompt=json.dumps(
            {
                "selected_style": asdict(style.selected_style),
                "palette": {
                    "accent": colors["accent"],
                    "background": colors["background"],
                    "text": colors["text"],
                },
                "ta_guidance": style.ta_guidance[:1600],
                "image_guidance": asdict(style.image_guidance),
                "placements": placements,
            },
            ensure_ascii=False,
        ),
        output_constraint=(
            '{"prompts":[{"slide_index":1,"prompt":"1-1500 characters"}]}. '
            f"Cover exactly these slide indexes: {indexes}."
        ),
        validator=lambda value: _validate_prompt_payload(value, indexes),
    )
    if not valid or payload is None:
        warnings.append("Used deterministic fallback image prompts.")
        return [
            {
                **placement,
                "prompt": _fallback_prompt(
                    placement["image_concept"],
                    colors["accent"],
                    colors["background"],
                ),
            }
            for placement in placements
        ], tokens, warnings
    by_index = {
        entry["slide_index"]: _with_text_free_prompt(
            entry["prompt"].strip()
        )
        for entry in payload["prompts"]
    }
    return [
        {**placement, "prompt": by_index[placement["slide_index"]]}
        for placement in placements
    ], tokens, warnings


def _generate_images(
    prompts: list[dict[str, Any]],
    *,
    chapter_path: Path,
    llm: LLM,
    config: ImageGenerationConfig,
) -> tuple[list[GeneratedImageRecord], list[str], list[Path], int]:
    generated: list[GeneratedImageRecord] = []
    warnings: list[str] = []
    pending_files: list[Path] = []
    billable_generations = 0
    images_dir = chapter_path / "html" / "images"
    for entry in prompts:
        index = entry["slide_index"]
        try:
            response = llm.client.images.generate(
                model=config.model,
                prompt=entry["prompt"],
                size=config.size,
                quality=config.quality,
            )
            billable_generations += 1
            data = getattr(response, "data", None)
            b64 = getattr(data[0], "b64_json", None) if data else None
            if not isinstance(b64, str) or not b64:
                raise ValueError("response contained no base64 image")
            raw = base64.b64decode(b64, validate=True)
            if not raw.startswith(PNG_SIGNATURE):
                raise ValueError("response was not a PNG")
            if len(raw) < 24 or raw[12:16] != b"IHDR":
                raise ValueError("response contained a malformed PNG header")
            actual_size = (
                int.from_bytes(raw[16:20], "big"),
                int.from_bytes(raw[20:24], "big"),
            )
            expected_size = tuple(
                int(value) for value in config.size.split("x", 1)
            )
            if actual_size != expected_size:
                raise ValueError(
                    "response dimensions were "
                    f"{actual_size[0]}x{actual_size[1]}, expected {config.size}"
                )
            images_dir.mkdir(parents=True, exist_ok=True)
            prompt_hash = hashlib.sha256(
                entry["prompt"].encode("utf-8")
            ).hexdigest()
            unique = hashlib.sha256(
                f"{time.time_ns()}:{index}".encode("utf-8")
            ).hexdigest()[:8]
            filename = f"img-{index:02d}-{prompt_hash[:12]}-{unique}.png"
            path = images_dir / filename
            temporary = path.with_suffix(".png.tmp")
            try:
                temporary.write_bytes(raw)
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
            pending_files.append(path)
            generated.append(
                GeneratedImageRecord(
                    slide_index=index,
                    concept=entry["image_concept"],
                    visual_type=entry["visual_type"],
                    labels=entry["labels"],
                    prompt=entry["prompt"],
                    prompt_sha256=prompt_hash,
                    file=filename,
                    data_uri=f"data:image/png;base64,{b64}",
                )
            )
        except Exception as exc:
            warnings.append(f"Slide {index}: image generation failed: {exc}")
    return generated, warnings, pending_files, billable_generations


def _call_json_agent(
    llm: LLM,
    *,
    name: str,
    role: str,
    system_prompt: str,
    prompt: str,
    output_constraint: str,
    validator: Callable[[dict[str, Any]], list[str]],
) -> tuple[dict[str, Any] | None, int, list[str], bool]:
    agent = Agent(
        name=name,
        role=role,
        llm=llm,
        system_prompt=system_prompt,
        output_constraint=output_constraint,
    )
    total_tokens = 0
    warnings: list[str] = []
    attempt_prompt = prompt
    for _ in range(3):
        try:
            result = agent.generate_response(
                attempt_prompt, stream=False, save_to_history=False
            )
            if not isinstance(result, tuple) or len(result) != 3:
                raise ValueError("agent returned no accounting tuple")
            response, _elapsed, tokens = result
            total_tokens += int(tokens)
            parsed = _parse_json_object(str(response))
            errors = ["response was not a JSON object"] if parsed is None else validator(parsed)
            if not errors:
                return parsed, total_tokens, warnings, True
            attempt_prompt = (
                f"{prompt}\n\nPrevious response rejected: {'; '.join(errors)}.\n"
                f"Previous response:\n{str(response)[:1500]}\n"
                "Return only the complete corrected JSON object."
            )
        except Exception as exc:
            warnings.append(f"{name} failed: {exc}")
            return None, total_tokens, warnings, False
    warnings.append(f"{name} returned invalid JSON after retries.")
    return None, total_tokens, warnings, False


def _filter_placements(
    entries: list[dict[str, Any]],
    deck: Any,
    guidance: ImageGuidance,
) -> tuple[list[dict[str, Any]], list[str]]:
    slides = {slide.index: slide for slide in deck.slides}
    valid: list[dict[str, Any]] = []
    warnings: list[str] = []
    for entry in entries:
        index = entry.get("slide_index")
        if isinstance(index, bool) or not isinstance(index, int) or index not in slides:
            warnings.append(f"Dropped invalid image slide index {index!r}.")
            continue
        slide = slides[index]
        if slide.is_titlepage:
            warnings.append(f"Dropped title-slide image placement {index}.")
            continue
        if _technically_dominated(slide):
            warnings.append(f"Dropped technically dominated slide {index}.")
            continue
        rationale = entry.get("rationale")
        concept = entry.get("image_concept")
        visual_type = entry.get("visual_type")
        labels = entry.get("labels", [])
        if (
            not isinstance(rationale, str)
            or not rationale.strip()
            or len(rationale.strip()) > 500
            or not isinstance(concept, str)
            or not concept.strip()
            or len(concept.strip()) > 500
        ):
            warnings.append(f"Dropped slide {index} with invalid rationale or concept.")
            continue
        if visual_type not in guidance.visual_types:
            warnings.append(f"Dropped slide {index} with disallowed visual type.")
            continue
        if (
            not isinstance(labels, list)
            or len(labels) > 4
            or any(
                not isinstance(label, str)
                or not label.strip()
                or len(label.strip()) > 80
                for label in labels
            )
        ):
            warnings.append(f"Dropped slide {index} with invalid native labels.")
            continue
        valid.append(
            {
                "slide_index": index,
                "rationale": rationale.strip(),
                "image_concept": concept.strip(),
                "visual_type": visual_type,
                "labels": [label.strip() for label in labels],
            }
        )
    return valid, warnings


def _technically_dominated(slide: Any) -> bool:
    from src.html_slides import element_weight

    weights = [(element.kind, element_weight(element)) for element in slide.elements]
    total = sum(weight for _kind, weight in weights)
    if total <= 0:
        return False
    technical = sum(
        weight
        for kind, weight in weights
        if kind in {"code", "table", "equation", "raw"}
    )
    return technical / total >= 0.6


def _deck_outline(deck: Any) -> list[dict[str, Any]]:
    from src.html_slides import element_weight

    outline: list[dict[str, Any]] = []
    for slide in deck.slides:
        fragments = [
            fragment
            for element in slide.elements
            for fragment in _element_fragments(element)
        ]
        outline.append(
            {
                "slide_index": slide.index,
                "title": slide.title,
                "is_titlepage": slide.is_titlepage,
                "element_weights": [
                    {"kind": element.kind, "weight": element_weight(element)}
                    for element in slide.elements
                ],
                "content_excerpt": " ".join(fragments)[:500],
            }
        )
    return outline


def _element_fragments(element: Any) -> list[str]:
    fragments = [str(element.title or ""), str(element.text or "")]
    for row in getattr(element, "rows", []):
        fragments.extend(str(cell) for cell in row)
    for item in getattr(element, "items", []):
        fragments.append(str(item.text))
        for child in getattr(item, "children", []):
            fragments.extend(_element_fragments(child))
    for child in getattr(element, "children", []):
        fragments.extend(_element_fragments(child))
    return [" ".join(fragment.split()) for fragment in fragments if fragment.strip()]


def _attach_records(
    deck: Any, records: list[GeneratedImageRecord], warnings: list[str]
) -> None:
    from src.html_slides import ContentElement

    slides = {slide.index: slide for slide in deck.slides}
    for record in records:
        slide = slides.get(record.slide_index)
        if slide is None or slide.is_titlepage:
            warnings.append(
                f"Generated image for slide {record.slide_index} could not be attached."
            )
            continue
        slide.elements.append(
            ContentElement(
                kind="generated_image",
                title=record.concept[:200],
                text=record.concept,
                image_data_uri=record.data_uri,
                image_labels=record.labels,
            )
        )


def _records_from_manifest(
    chapter_path: Path, manifest: dict[str, Any]
) -> list[GeneratedImageRecord]:
    records: list[GeneratedImageRecord] = []
    images_dir = chapter_path / "html" / "images"
    seen_indexes: set[int] = set()
    for entry in manifest.get("placements", []):
        if not isinstance(entry, dict):
            return []
        try:
            raw_filename = str(entry["file"])
            filename = Path(raw_filename).name
            if filename != raw_filename:
                return []
            raw = (images_dir / filename).read_bytes()
            if not _valid_png_bytes(raw):
                return []
            slide_index = int(entry["slide_index"])
            concept = str(entry["concept"])
            visual_type = str(entry["visual_type"])
            labels = entry.get("labels", [])
            prompt = str(entry["prompt"])
            prompt_sha256 = str(entry["prompt_sha256"])
            if (
                slide_index < 1
                or slide_index in seen_indexes
                or not concept.strip()
                or len(concept.strip()) > 500
                or visual_type not in IMAGE_VISUAL_TYPES
                or not isinstance(labels, list)
                or len(labels) > 4
                or any(
                    not isinstance(label, str)
                    or not label.strip()
                    or len(label.strip()) > 80
                    for label in labels
                )
                or not prompt.strip()
                or len(prompt.strip()) > 1500
                or hashlib.sha256(prompt.encode("utf-8")).hexdigest()
                != prompt_sha256
            ):
                return []
            seen_indexes.add(slide_index)
            records.append(
                GeneratedImageRecord(
                    slide_index=slide_index,
                    concept=concept,
                    visual_type=visual_type,
                    labels=[str(value) for value in labels],
                    prompt=prompt,
                    prompt_sha256=prompt_sha256,
                    file=filename,
                    data_uri=(
                        "data:image/png;base64,"
                        + base64.b64encode(raw).decode("ascii")
                    ),
                )
            )
        except (KeyError, OSError, TypeError, ValueError):
            return []
    return records


def _manifest_is_current(
    chapter_path: Path,
    manifest: dict[str, Any],
    fingerprint: str,
) -> bool:
    if (
        manifest.get("schema_version") != IMAGE_MANIFEST_SCHEMA_VERSION
        or manifest.get("request_fingerprint") != fingerprint
    ):
        return False
    placements = manifest.get("placements")
    if not isinstance(placements, list):
        return False
    records = _records_from_manifest(chapter_path, manifest)
    if len(records) != len(placements):
        return False
    configuration = manifest.get("configuration")
    if not isinstance(configuration, dict):
        return False
    size = configuration.get("size")
    if not isinstance(size, str) or not re.fullmatch(r"\d+x\d+", size):
        return False
    expected_size = tuple(int(value) for value in size.split("x", 1))
    images_dir = chapter_path / "html" / "images"
    try:
        return all(
            _png_dimensions(
                (images_dir / record.file).read_bytes()
            )
            == expected_size
            for record in records
        )
    except OSError:
        return False


def _valid_png_bytes(raw: bytes) -> bool:
    if (
        len(raw) < 24
        or not raw.startswith(PNG_SIGNATURE)
        or raw[12:16] != b"IHDR"
    ):
        return False
    width = int.from_bytes(raw[16:20], "big")
    height = int.from_bytes(raw[20:24], "big")
    return width > 0 and height > 0 and width * 9 == height * 16


def _png_dimensions(raw: bytes) -> tuple[int, int] | None:
    if not _valid_png_bytes(raw):
        return None
    return (
        int.from_bytes(raw[16:20], "big"),
        int.from_bytes(raw[20:24], "big"),
    )


def _read_image_manifest(chapter_path: Path) -> dict[str, Any]:
    path = chapter_path / "html" / "images" / IMAGE_MANIFEST_FILENAME
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _placement_contract(key: str, slide_count: int) -> str:
    return (
        '{"' + key + '":[{"slide_index":1,"rationale":"one sentence",'
        '"image_concept":"one sentence","visual_type":"allowed value",'
        '"labels":["native HTML label"]}]}. '
        f"Indexes must be integers from 1 to {slide_count}. Labels are optional, "
        "maximum four, and are rendered outside the image."
    )


def _validate_payload_list(payload: dict[str, Any], key: str) -> list[str]:
    entries = payload.get(key)
    if not isinstance(entries, list):
        return [f"{key} must be a list"]
    if any(not isinstance(entry, dict) for entry in entries):
        return [f"every {key} entry must be an object"]
    return []


def _validate_prompt_payload(
    payload: dict[str, Any], indexes: list[int]
) -> list[str]:
    entries = payload.get("prompts")
    if not isinstance(entries, list):
        return ["prompts must be a list"]
    found: list[int] = []
    for entry in entries:
        if not isinstance(entry, dict):
            return ["every prompt must be an object"]
        index = entry.get("slide_index")
        prompt = entry.get("prompt")
        if isinstance(index, bool) or not isinstance(index, int):
            return ["every prompt needs an integer slide_index"]
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt.strip()) > 1500:
            return [f"slide {index} has an invalid prompt"]
        found.append(index)
    return [] if sorted(found) == sorted(indexes) else ["prompt indexes do not match placements"]


def _fallback_prompt(concept: str, accent: str, background: str) -> str:
    return _with_text_free_prompt(
        f"Clean minimal presentation figure illustrating: {concept}. "
        "True 16:9 landscape composition, flat modern illustration, palette "
        f"accents {accent} on {background}, generous negative space."
    )


def _with_text_free_prompt(prompt: str) -> str:
    available = 1500 - len(TEXT_FREE_PROMPT_SUFFIX)
    base = prompt.strip()[:available].rstrip()
    return f"{base}{TEXT_FREE_PROMPT_SUFFIX}"


def _parse_json_object(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", stripped, flags=re.DOTALL)
    if fenced:
        stripped = fenced.group(1).strip()
    start, end = stripped.find("{"), stripped.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
