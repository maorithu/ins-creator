from __future__ import annotations

import json
from typing import List, Optional
from backend.config import settings
from backend.models.schemas import (
    AudioCueMap,
    InstagramPostCopy,
    MediaItem,
    StylePreset,
    TimelineClip,
)


def generate_instagram_post_copy(
    search_query: str,
    style_preset: StylePreset,
    supplemental_directions: str,
    matched_media: List[MediaItem],
    timeline_clips: List[TimelineClip],
    audio_cue_map: Optional[AudioCueMap] = None,
) -> InstagramPostCopy:
    """
    Generates attractive Instagram Reel titles, on-screen hooks, multi-style captions, and hashtags.
    Uses Google Gemini API (`google.genai`) if `GEMINI_API_KEY` is configured, with a rich,
    context-aware dance storytelling generator fallback so the workflow always succeeds immediately.
    """
    jump_count = sum(
        1 for c in timeline_clips if c.matched_dance_move and "jump" in c.matched_dance_move.value
    )
    turn_count = sum(
        1 for c in timeline_clips if c.matched_dance_move and "turn" in c.matched_dance_move.value
    )
    photo_count = sum(1 for c in timeline_clips if c.media_type.value == "photo")
    bpm_val = int(audio_cue_map.bpm) if audio_cue_map else 120

    # Try live Gemini API first if key is available
    if settings.gemini_api_key:
        try:
            from google import genai

            client = genai.Client(api_key=settings.gemini_api_key)
            prompt = f"""
You are a creative social media director for a proud dance parent creating an Instagram Reel of their daughter's dance event.
Search Query: {search_query}
Selected Style Preset: {style_preset.name} ({style_preset.tagline})
Supplemental User Directions: {supplemental_directions}
Choreography Sync Summary: {len(timeline_clips)} cuts at {bpm_val} BPM ({jump_count} jump peaks synced to downbeats, {turn_count} spin/turn highlights, {photo_count} photos placed on sustained notes/pauses with Ken Burns effects).

Return ONLY valid JSON matching this schema:
{{
  "hook_title_overlay": "Short punchy 4-7 word on-screen hook for the first 2.5s of the video",
  "ending_call_to_action": "Short inspiring closing overlay",
  "post_headline": "Attractive headline title for the Instagram post",
  "caption_primary": "Engaging, heartfelt multi-paragraph Instagram caption incorporating the user's supplemental directions",
  "caption_alternatives": [
    {{"label": "Short & Punchy Hype", "text": "..."}},
    {{"label": "Technique & Studio Grit", "text": "..."}},
    {{"label": "Proud Parent Storytelling", "text": "..."}}
  ],
  "hashtags": ["#dancemom", "#dancerlife", "...12 relevant hashtags"]
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
                music_credit_note=audio_cue_map.title if audio_cue_map else "",
            )
        except Exception:
            pass

    # Rich, context-adaptive copywriting tailored to preset, query, and supplemental directions
    q_lower = f"{search_query} {supplemental_directions}".lower()
    is_rehearsal = "rehearsal" in q_lower or style_preset.id == "rehearsal_gritty_raw"
    is_training = "training" in q_lower or style_preset.id == "training_technique_spotlight"
    is_lyrical = "lyrical" in q_lower or "ballet" in q_lower or style_preset.id == "lyrical_graceful_flow"

    if is_rehearsal:
        hook_title = "Count by count, rehearsal turns into magic ✨"
        headline = "Behind the Curtain: The Rehearsal Hours Nobody Sees 🩰🔥"
    elif is_training:
        hook_title = "Chasing higher leaps & cleaner turns every week 🚀"
        headline = "Progress in Motion: Technique, Grit & Flight 💪✨"
    elif is_lyrical:
        hook_title = "When the music breathes, she takes flight 🦢✨"
        headline = "Grace in Every Note: Dancing from the Heart 💫"
    else:
        hook_title = "From studio sweat to soaring under the stage lights ✨"
        headline = "Leaving Her Heart on the Competition Stage 🏆🩰"

    supp_note = ""
    if supplemental_directions and len(supplemental_directions.strip()) > 4:
        supp_note = f"\n\n✨ Special moments in this edit: {supplemental_directions.strip()}"

    primary_caption = (
        f"{headline}\n\n"
        f"Every 8-count tells a story of early mornings, sore muscles, and pure joy when the music drops. "
        f"Watching her hit those {jump_count or 2} peak leaps right on the downbeat and hold her poise "
        f"through every turn never gets old! 🥺💖"
        f"{supp_note}\n\n"
        f"Drop a 🔥 or 🩰 in the comments to cheer her on for the next event!"
    )

    alternatives = [
        {
            "label": "Proud Parent & Heartfelt",
            "text": (
                f"I still remember her very first dance class—and now look at that extension and confidence under the lights! "
                f"So proud of the hard work she puts into every rehearsal and training session. Keep flying high, sweet girl! 🌟🩰💖"
            ),
        },
        {
            "label": "Short & Punchy Hype",
            "text": (
                f"Beat drop = maximum elevation 🚀🔥 {jump_count or 2} apex leaps + razor-sharp turns synced at {bpm_val} BPM. "
                f"She understood the assignment! 💯✨"
            ),
        },
        {
            "label": "Technique & Dedication Focus",
            "text": (
                f"Champions are built in the rehearsal room. Focused on jump elevation, clean spotting on the turns, "
                f"and musicality through the sustained notes. Proud of this progress! 📈🩰"
            ),
        },
    ]

    hashtags = [
        "#DanceMom",
        "#DancerLife",
        "#CompetitionDance",
        "#DanceRehearsal",
        "#ContemporaryDance",
        "#DanceTraining",
        "#YoungDancer",
        "#GrandJete",
        "#Pirouette",
        "#DanceReels",
        "#ProudParent",
        "#StageLights",
    ]

    return InstagramPostCopy(
        hook_title_overlay=hook_title,
        ending_call_to_action="Keep shining on stage ✨",
        post_headline=headline,
        caption_primary=primary_caption,
        caption_alternatives=alternatives,
        hashtags=hashtags,
        music_credit_note=f"Synced to: {audio_cue_map.title}" if audio_cue_map else "Beat-Synced Dance Edit",
    )
