from __future__ import annotations

import html
from pathlib import Path
from typing import Dict, List, Optional

from backend.config import EXPORTS_DIR
from backend.models.schemas import (
    AudioCueMap,
    InstagramPostCopy,
    MediaItem,
    TimelineClip,
)


def _sec_to_fcpxml_rational(sec: float, fps: int = 30) -> str:
    frames = int(round(sec * fps))
    return f"{frames * 100}/{fps * 100}s"


def export_fcpxml_project(
    session_id: str,
    project_title: str,
    timeline_clips: List[TimelineClip],
    media_lookup: Dict[str, MediaItem],
    audio_cue_map: Optional[AudioCueMap],
    post_copy: Optional[InstagramPostCopy],
) -> Path:
    """
    Exports a standard FCPXML v1.9 file compatible with Final Cut Pro, DaVinci Resolve, and Premiere Pro,
    complete with asset references, timeline offsets, and markers for downbeats, jump peaks, and photo cues.
    """
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    xml_path = EXPORTS_DIR / f"{session_id}_timeline.fcpxml"
    total_dur = max((c.timeline_end_sec for c in timeline_clips), default=15.0)

    assets_xml: List[str] = []
    added_ids = set()
    for clip in timeline_clips:
        if clip.media_id in added_ids:
            continue
        added_ids.add(clip.media_id)
        m = media_lookup.get(clip.media_id)
        fpath = Path(m.filepath).resolve().as_uri() if m else f"file:///media/{clip.filename}"
        dur_s = _sec_to_fcpxml_rational(m.duration_sec if (m and m.duration_sec > 0) else 10.0)
        assets_xml.append(
            f'    <asset id="r_{html.escape(clip.media_id)}" name="{html.escape(clip.filename)}" '
            f'src="{html.escape(fpath)}" start="0s" duration="{dur_s}" hasVideo="1" format="r1"/>'
        )

    if audio_cue_map:
        afpath = Path(audio_cue_map.filepath).resolve().as_uri()
        adur_s = _sec_to_fcpxml_rational(audio_cue_map.duration_sec)
        assets_xml.append(
            f'    <asset id="r_audio_main" name="{html.escape(audio_cue_map.title)}" '
            f'src="{html.escape(afpath)}" start="0s" duration="{adur_s}" hasAudio="1"/>'
        )

    spine_xml: List[str] = []
    for clip in timeline_clips:
        offset_s = _sec_to_fcpxml_rational(clip.timeline_start_sec)
        start_s = _sec_to_fcpxml_rational(clip.source_in_sec)
        dur_s = _sec_to_fcpxml_rational(clip.duration_sec)
        marker_label = html.escape(
            f"{clip.synced_cue_type}: {clip.sync_explanation}"
        )
        spine_xml.append(
            f'            <asset-clip name="{html.escape(clip.filename)}" ref="r_{html.escape(clip.media_id)}" '
            f'offset="{offset_s}" start="{start_s}" duration="{dur_s}">\n'
            f'              <marker start="{start_s}" duration="100/3000s" value="{marker_label}"/>\n'
            f"            </asset-clip>"
        )

    if audio_cue_map:
        spine_xml.append(
            f'            <asset-clip name="{html.escape(audio_cue_map.title)}" ref="r_audio_main" '
            f'lane="-1" offset="0s" start="0s" duration="{_sec_to_fcpxml_rational(total_dur)}"/>'
        )

    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE fcpxml>
<fcpxml version="1.9">
  <resources>
    <format id="r1" name="FFVideoFormat1080x1920p30" frameDuration="100/3000s" width="1080" height="1920"/>
{chr(10).join(assets_xml)}
  </resources>
  <library>
    <event name="InsCreator Dance Reels">
      <project name="{html.escape(project_title)}">
        <sequence format="r1" duration="{_sec_to_fcpxml_rational(total_dur)}" tcStart="0s" tcFormat="NDF">
          <spine>
{chr(10).join(spine_xml)}
          </spine>
        </sequence>
      </project>
    </event>
  </library>
</fcpxml>
"""
    xml_path.write_text(content, encoding="utf-8")
    return xml_path
