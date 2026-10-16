from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from backend.config import settings
from backend.models.schemas import (
    AudioCueMap,
    InstagramPostCopy,
    MediaItem,
    StylePreset,
    TimelineClip,
)


def _extract_media_personalization_context(
    matched_media: List[MediaItem],
    timeline_clips: List[TimelineClip],
) -> Dict[str, object]:
    """
    Extracts personalized human-readable details from the imported media items:
    - Dancer name / routine title parsed from camelCase filenames (e.g. '093LillianWeiInTheCurrentCont12903.JPG')
    - Detected dance styles & tags (e.g. Contemporary, Lyrical, Stage Performance, Pro Stage Photo)
    - Capture dates (e.g. 2026-03-26) and camera models (e.g. Canon EOS R6 Mark III, Apple iPhone 17 Pro)
    - Photo vs. Video counts and Jump/Turn peak counts
    """
    used_media_ids = {c.media_id for c in timeline_clips}
    active_media = [m for m in matched_media if m.id in used_media_ids] or matched_media

    parsed_phrases: List[str] = []
    dancer_name: Optional[str] = None
    routine_title: Optional[str] = None
    styles: List[str] = []
    tags: List[str] = []
    dates: List[str] = []
    cameras: List[str] = []
    media_descriptions: List[str] = []

    for m in active_media:
        for t in m.tags:
            if t not in tags:
                tags.append(t)
            if t in ("Contemporary", "Lyrical", "Ballet", "Jazz", "Acro", "Hip Hop") and t not in styles:
                styles.append(t)

        if m.creation_time:
            date_only = m.creation_time.split(" ")[0]
            if date_only and date_only not in dates:
                dates.append(date_only)

        if m.camera_model and m.camera_model not in cameras:
            cameras.append(m.camera_model)

        if m.semantic_caption:
            media_descriptions.append(f"{m.filename}: {m.semantic_caption}")

        stem = Path(m.filename).stem
        # Split camelCase like '093LillianWeiInTheCurrentCont12903' -> 'Lillian Wei In The Current Cont'
        spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", stem)
        cleaned = re.sub(r"[0-9_]+", " ", spaced).strip()
        lower_stem = cleaned.lower()
        if (
            len(cleaned) > 5
            and not lower_stem.startswith("img")
            and not lower_stem.startswith("gp")
            and not lower_stem.startswith("sample")
            and not lower_stem.startswith("vid")
        ):
            # Remove trailing style abbreviations like 'Cont', 'Lyr', 'Jazz'
            tokens = cleaned.split()
            if tokens and tokens[-1].lower() in ("cont", "contemporary", "lyr", "lyrical", "ballet", "solo"):
                style_tok = tokens.pop()
                if style_tok.lower().startswith("cont") and "Contemporary" not in styles:
                    styles.append("Contemporary")
            phrase = " ".join(tokens)
            if phrase and phrase not in parsed_phrases:
                parsed_phrases.append(phrase)
            # Heuristic: if first 2 tokens are capitalized names and remaining tokens are routine title
            if len(tokens) >= 4 and not dancer_name:
                dancer_name = f"{tokens[0]} {tokens[1]}"
                routine_title = " ".join(tokens[2:])
            elif len(tokens) >= 2 and not dancer_name:
                dancer_name = " ".join(tokens[:2])

    video_count = sum(1 for m in active_media if m.media_type.value == "video")
    photo_count = sum(1 for m in active_media if m.media_type.value == "photo")
    jump_count = sum(
        1 for c in timeline_clips if c.matched_dance_move and "jump" in c.matched_dance_move.value
    )
    turn_count = sum(
        1 for c in timeline_clips if c.matched_dance_move and "turn" in c.matched_dance_move.value
    )

    return {
        "dancer_name": dancer_name,
        "routine_title": routine_title,
        "parsed_phrases": parsed_phrases,
        "styles": styles or ["Dance"],
        "tags": tags,
        "dates": dates,
        "cameras": cameras,
        "video_count": video_count,
        "photo_count": photo_count,
        "jump_count": jump_count,
        "turn_count": turn_count,
        "media_descriptions": media_descriptions,
        "filenames": [m.filename for m in active_media],
    }


def generate_instagram_post_copy(
    search_query: str,
    style_preset: StylePreset,
    supplemental_directions: str,
    matched_media: List[MediaItem],
    timeline_clips: List[TimelineClip],
    audio_cue_map: Optional[AudioCueMap] = None,
    custom_prompt: str = "",
) -> InstagramPostCopy:
    """
    Generates personalized Instagram Reel titles, on-screen hooks, multi-style captions, and hashtags
    grounded in the analyzed media metadata (filenames, dancer/routine name, EXIF dates/cameras, tags,
    photo/video composition) and any user custom prompt.
    """
    ctx = _extract_media_personalization_context(matched_media, timeline_clips)
    dancer_name = str(ctx.get("dancer_name") or "").strip()
    routine_title = str(ctx.get("routine_title") or "").strip()
    styles: List[str] = list(ctx.get("styles") or ["Dance"])  # type: ignore
    tags: List[str] = list(ctx.get("tags") or [])  # type: ignore
    dates: List[str] = list(ctx.get("dates") or [])  # type: ignore
    cameras: List[str] = list(ctx.get("cameras") or [])  # type: ignore
    video_count = int(ctx.get("video_count") or 0)  # type: ignore
    photo_count = int(ctx.get("photo_count") or 0)  # type: ignore
    jump_count = int(ctx.get("jump_count") or 0)  # type: ignore
    turn_count = int(ctx.get("turn_count") or 0)  # type: ignore
    media_descriptions: List[str] = list(ctx.get("media_descriptions") or [])  # type: ignore
    bpm_val = int(audio_cue_map.bpm) if audio_cue_map else 120

    # Try live Gemini API first if a valid AI Studio key (AIza...) is configured
    if settings.gemini_api_key and settings.gemini_api_key.startswith("AIza"):
        try:
            from google import genai

            client = genai.Client(api_key=settings.gemini_api_key)
            prompt = f"""
You are a creative social media director for a proud dance parent creating a personalized Instagram Reel.
Ground the post specifically in the imported media metadata below:
- Dancer Name (if detected): {dancer_name or 'Our dancer'}
- Routine / Piece Title (if detected): {routine_title or 'Stage & studio performance'}
- Detected Dance Style(s): {', '.join(styles)}
- Media Tags: {', '.join(tags)}
- Event Capture Date(s): {', '.join(dates) if dates else 'Recent event'}
- Cameras Used: {', '.join(cameras) if cameras else 'Stage & mobile cameras'}
- Media Breakdown: {photo_count} photos and {video_count} videos ({jump_count} jump peaks, {turn_count} turn highlights) synced at {bpm_val} BPM to "{audio_cue_map.title if audio_cue_map else 'dance track'}".
- Per-Item Analyzed Descriptions:
{chr(10).join('  * ' + d for d in media_descriptions[:8])}
- Selected Style Preset: {style_preset.name} ({style_preset.tagline})
- Supplemental Directions: {supplemental_directions}
- User Custom Regeneration Prompt (HIGHEST PRIORITY): {custom_prompt or 'Write a deeply personalized post matching the media above.'}

Return ONLY valid JSON matching this schema:
{{
  "hook_title_overlay": "Short punchy 4-7 word on-screen hook for the first 2.5s of the video",
  "ending_call_to_action": "Short inspiring closing overlay",
  "post_headline": "Attractive personalized headline title for the Instagram post",
  "caption_primary": "Engaging, personalized multi-paragraph Instagram caption referencing the specific routine/style/media and fulfilling the user's custom prompt",
  "caption_alternatives": [
    {{"label": "Proud Parent & Heartfelt", "text": "..."}},
    {{"label": "Short & Punchy Hype", "text": "..."}},
    {{"label": "Stage & Technique Spotlight", "text": "..."}}
  ],
  "hashtags": ["#dancemom", "#dancerlife", "...12 personalized hashtags"]
}}
"""
            response = client.models.generate_content(
                model=settings.gemini_model,
                contents=prompt,
            )
            raw_text = (response.text or "").strip()
            if "```json" in raw_text:
                raw_text = raw_text.split("```json")[1].split("```")[0].strip()
            elif "```" in raw_text:
                raw_text = raw_text.split("```")[1].split("```")[0].strip()
            parsed = json.loads(raw_text)
            return InstagramPostCopy(
                hook_title_overlay=parsed.get("hook_title_overlay", "Flying higher with every 8-count ✨"),
                ending_call_to_action=parsed.get("ending_call_to_action", "Born for the stage ✨"),
                post_headline=parsed.get("post_headline", "From Studio Counts to Stage Spotlights"),
                caption_primary=parsed.get("caption_primary", ""),
                caption_alternatives=parsed.get("caption_alternatives", []),
                hashtags=parsed.get("hashtags", []),
                music_credit_note=f"Synced to: {audio_cue_map.title}" if audio_cue_map else "",
            )
        except Exception:
            pass

    # Personalized, media-grounded copywriting engine with full custom_prompt responsiveness
    primary_style = styles[0] if styles else "Contemporary"
    subject_label = dancer_name if dancer_name else "she"
    subject_possessive = f"{dancer_name}'s" if dancer_name else "her"
    routine_clause = f' "{routine_title}"' if routine_title else ""
    date_clause = f" ({dates[0]})" if dates else ""
    pro_photo_clause = (
        f"from high-resolution {cameras[0]} stage captures to candid behind-the-scenes moments"
        if len(cameras) >= 2
        else (f"captured on {cameras[0]}" if cameras else "captured under the stage spotlights")
    )

    if video_count == 0 and photo_count > 0:
        media_action_desc = (
            f"Each of these {photo_count} {primary_style.lower()} stage and candid portraits ({pro_photo_clause}) "
            f"is timed to breathe with the music at {bpm_val} BPM using smooth Ken Burns motion."
        )
    elif video_count > 0 and photo_count > 0:
        media_action_desc = (
            f"Blending {video_count} dynamic video clip(s) ({jump_count or 1} peak leaps & turns synced to the {bpm_val} BPM downbeats) "
            f"with {photo_count} poised {primary_style.lower()} still frame(s) ({pro_photo_clause}) on the sustained musical notes."
        )
    else:
        media_action_desc = (
            f"Syncing {jump_count or 2} peak leaps and sharp turns across {video_count} clips directly to the {bpm_val} BPM measure downbeats."
        )

    combined_instructions = f"{custom_prompt} {supplemental_directions} {search_query}".lower()
    prompt_clean = custom_prompt.strip()

    # Check if user asked for Chinese / bilingual, short/witty, coach thank-you, etc.
    wants_chinese = any(w in combined_instructions for w in ["chinese", "中文", "bilingual", "双语"])
    wants_short = any(w in combined_instructions for w in ["short", "brief", "concise", "one line", "minimal", "punchy"])
    wants_funny = any(w in combined_instructions for w in ["funny", "humor", "witty", "playful", "fun"])
    wants_thank_you = any(w in combined_instructions for w in ["thank", "coach", "teacher", "choreographer", "studio", "gratitude"])

    # Build Hook & Headline grounded in Dancer Name + Routine Title + Style + Custom Prompt
    if dancer_name and routine_title:
        hook_options = [
            f"{dancer_name} • \"{routine_title}\" ✨",
            f"{dancer_name} soaring in \"{routine_title}\" 🩰✨",
            f"Every note of \"{routine_title}\" — {dancer_name} 💫",
        ]
        headline_options = [
            f"{dancer_name} in \"{routine_title}\" — {primary_style} Stage Highlights{date_clause} 🩰✨",
            f"Poise, Passion & Stage Lights: {dancer_name} Performing \"{routine_title}\" 🌟",
            f"\"{routine_title}\": {dancer_name}'s {primary_style} Journey Under the Spotlights 🏆💫",
        ]
    elif dancer_name:
        hook_options = [
            f"{dancer_name} • {primary_style} Highlights ✨",
            f"Built in rehearsal, shining on stage • {dancer_name} 🩰",
        ]
        headline_options = [
            f"{dancer_name}'s {primary_style} Stage & Studio Moments{date_clause} 🩰✨",
            f"Grace & Grit: {dancer_name} Under the Stage Lights 🌟",
        ]
    else:
        hook_options = [
            f"{primary_style} grace in every count ✨",
            f"When the stage lights hit, she takes flight 🩰✨",
            f"Poise, extension & heart on the stage 💫",
        ]
        headline_options = [
            f"Leaving Her Heart on the {primary_style} Stage{date_clause} 🏆🩰",
            f"From Studio Counts to Stage Spotlights: {primary_style} Highlights ✨",
        ]

    # Pick deterministically on first generation, or rotate when custom_prompt is used
    seed_idx = random.randint(0, len(hook_options) - 1) if prompt_clean else 0
    hook_title = hook_options[seed_idx % len(hook_options)]
    headline = headline_options[seed_idx % len(headline_options)]

    # Build personalized primary caption
    custom_highlight_line = ""
    if prompt_clean:
        custom_highlight_line = f"\n\n✨ {prompt_clean}"
    elif supplemental_directions and len(supplemental_directions.strip()) > 4:
        # Don't dump raw technical editing instructions verbatim if they look like default template text;
        # instead summarize or include user's custom notes naturally
        if not supplemental_directions.startswith("Sync her highest jump peak to the main measure downbeat"):
            custom_highlight_line = f"\n\n✨ {supplemental_directions.strip()}"

    thank_you_line = ""
    if wants_thank_you:
        thank_you_line = (
            f"\n\nA huge thank-you to {subject_possessive} dedicated teachers, choreographers, and dance family "
            f"for guiding every detail of{routine_clause or ' this piece'}!"
        )

    bilingual_block = ""
    if wants_chinese:
        cn_name = dancer_name or "她"
        cn_routine = f"《{routine_title}》" if routine_title else f"{primary_style}舞台"
        bilingual_block = (
            f"\n\n🩰 舞台瞬间：{cn_name}在{cn_routine}中的每一次延伸与定格，都凝聚着台下无数个小时的汗水与热爱。继续闪耀吧！✨"
        )

    if wants_short:
        primary_caption = (
            f"{headline}\n\n"
            f"{dancer_name or 'She'} bringing {primary_style.lower()} artistry and emotion to{routine_clause or ' the stage'}"
            f"{date_clause}. {media_action_desc}"
            f"{custom_highlight_line}{thank_you_line}{bilingual_block}"
        )
    elif wants_funny:
        primary_caption = (
            f"{headline}\n\n"
            f"90% bobby pins, 10% hairspray, 100% heart on stage 😄🩰! "
            f"Watching {dancer_name or 'her'} command the floor in{routine_clause or f' her {primary_style.lower()} piece'} "
            f"({pro_photo_clause}) makes every early morning call time worth it."
            f"{custom_highlight_line}{thank_you_line}{bilingual_block}"
        )
    else:
        primary_caption = (
            f"{headline}\n\n"
            f"Every count tells a story of dedication, musicality, and pure love for dance. "
            f"Watching {dancer_name or 'her'} bring{routine_clause or f' this {primary_style.lower()} piece'} to life{date_clause} "
            f"never gets old! 🥺💖\n\n"
            f"{media_action_desc}"
            f"{custom_highlight_line}{thank_you_line}{bilingual_block}\n\n"
            f"Drop a 🔥 or 🩰 in the comments to cheer {dancer_name or 'her'} on!"
        )

    alternatives = [
        {
            "label": "Proud Parent & Heartfelt",
            "text": (
                f"From rehearsals to stepping under the stage lights for{routine_clause or f' {subject_possessive} {primary_style.lower()} performance'}"
                f"{date_clause}—so proud of the grace, poise, and focus {subject_label} pours into every movement. "
                f"{prompt_clean + ' ' if prompt_clean else ''}Keep shining, {dancer_name or 'sweet girl'}! 🌟🩰💖"
                f"{bilingual_block}"
            ),
        },
        {
            "label": "Short & Punchy Hype",
            "text": (
                f"{dancer_name + ' • ' if dancer_name else ''}{routine_title or primary_style} 🔥✨ "
                f"{photo_count} stage & candid captures + {video_count} clips locked to {bpm_val} BPM. "
                f"{prompt_clean if prompt_clean else 'Poise, extension, and stage presence on 100! 💯🩰'}"
            ),
        },
        {
            "label": "Stage & Camera Details",
            "text": (
                f"Highlighting {subject_possessive} {primary_style.lower()} lines and stage framing"
                f"{routine_clause}{date_clause} ({pro_photo_clause}). "
                f"Synced to \"{audio_cue_map.title if audio_cue_map else 'the music'}\" at {bpm_val} BPM. 📈🩰"
            ),
        },
    ]

    # Build personalized hashtags from media metadata
    hashtags: List[str] = []
    if dancer_name:
        hashtags.append("#" + re.sub(r"[^A-Za-z0-9]", "", dancer_name))
    if routine_title:
        hashtags.append("#" + re.sub(r"[^A-Za-z0-9]", "", routine_title))
    for st in styles:
        tag_str = "#" + re.sub(r"[^A-Za-z0-9]", "", st) + ("Dance" if "dance" not in st.lower() else "")
        if tag_str not in hashtags:
            hashtags.append(tag_str)

    default_tags = [
        "#CompetitionDance",
        "#StagePerformance",
        "#DanceMom",
        "#DancerLife",
        "#YoungDancer",
        "#DanceReels",
        "#DancePhotography",
        "#ProudParent",
        "#StageLights",
        "#FullOut",
    ]
    for dt in default_tags:
        if dt not in hashtags and len(hashtags) < 12:
            hashtags.append(dt)

    return InstagramPostCopy(
        hook_title_overlay=hook_title,
        ending_call_to_action=f" Bravo, {dancer_name}! ✨".strip() if dancer_name else "Keep shining on stage ✨",
        post_headline=headline,
        caption_primary=primary_caption,
        caption_alternatives=alternatives,
        hashtags=hashtags,
        music_credit_note=f"Synced to: {audio_cue_map.title}" if audio_cue_map else "Beat-Synced Dance Edit",
    )
