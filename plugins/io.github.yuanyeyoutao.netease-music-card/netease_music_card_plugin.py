"""Search NetEase Music through MCP and send QQ music or album cards."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from typing import cast

from pydantic import BaseModel, Field, model_validator

from yuki_plugin_sdk.context import PluginContext
from yuki_plugin_sdk.models import JsonValue, PermissionLevel, RiskClass, StrictModel, TurnOrigin
from yuki_plugin_sdk.registrar import PluginRegistrar, ToolMetadata, ToolRegistration
from yuki_plugin_sdk.results import ToolResult

_SERVER_ID = "netease_music"
_ID_PATTERN = re.compile(r"^[1-9][0-9]{0,19}$")
_QUOTED_TITLE_PATTERN = re.compile(r"[《「『]([^》」』]{1,200})[》」』]")
_MAX_SENT_EVENT_CACHE = 512


class ShareMusicInput(StrictModel):
    """A title/artist search or a previously selected NetEase song ID."""

    query: str = Field(default="", max_length=200)
    artist: str = Field(default="", max_length=100)
    song_id: str = Field(default="", max_length=20)

    @model_validator(mode="after")
    def _valid_request(self) -> ShareMusicInput:
        query = self.query.strip()
        artist = self.artist.strip()
        song_id = self.song_id.strip()
        if bool(query) == bool(song_id):
            raise ValueError("provide exactly one of query or song_id")
        if song_id and _ID_PATTERN.fullmatch(song_id) is None:
            raise ValueError("song_id must be a positive NetEase numeric ID")
        if artist and not query:
            raise ValueError("artist can only be used with query")
        return self


class ShareAlbumInput(StrictModel):
    """An album/artist search or a previously selected NetEase album ID."""

    query: str = Field(default="", max_length=200)
    artist: str = Field(default="", max_length=100)
    album_id: str = Field(default="", max_length=20)

    @model_validator(mode="after")
    def _valid_request(self) -> ShareAlbumInput:
        query = self.query.strip()
        artist = self.artist.strip()
        album_id = self.album_id.strip()
        if bool(query) == bool(album_id):
            raise ValueError("provide exactly one of query or album_id")
        if album_id and _ID_PATTERN.fullmatch(album_id) is None:
            raise ValueError("album_id must be a positive NetEase numeric ID")
        if artist and not query:
            raise ValueError("artist can only be used with query")
        return self


class SongCandidate(StrictModel):
    song_id: str
    title: str
    artists: tuple[str, ...] = ()


class AlbumCandidate(StrictModel):
    album_id: str
    title: str
    artists: tuple[str, ...] = ()
    cover_url: str = ""
    publish_date: str = ""


class AlbumTrack(StrictModel):
    song_id: str
    title: str
    artists: tuple[str, ...] = ()


class ShareMusicOutput(StrictModel):
    status: str = Field(pattern=r"^(sent|selection_required|not_found)$")
    message: str
    selected: SongCandidate | None = None
    candidates: tuple[SongCandidate, ...] = ()


class ShareAlbumOutput(StrictModel):
    status: str = Field(pattern=r"^(sent|selection_required|not_found)$")
    message: str
    selected: AlbumCandidate | None = None
    candidates: tuple[AlbumCandidate, ...] = ()
    tracks: tuple[AlbumTrack, ...] = ()
    track_count: int = Field(default=0, ge=0)


class NetEaseMusicCardPlugin:
    """Focused current-scene share tools without a second Agent route."""

    def __init__(self) -> None:
        self._context: PluginContext | None = None
        self._sent_album_events: dict[str, ShareAlbumOutput] = {}

    async def register(self, registrar: PluginRegistrar) -> None:
        registrar.register_tool(
            ToolRegistration(
                metadata=ToolMetadata(
                    name="share_netease_music",
                    description=(
                        "仅当用户明确要求发送、分享或点一首网易云歌曲到当前 QQ 会话时调用。"
                        "可按歌曲名和歌手搜索，也可用上次候选中的 song_id 精确发送。"
                        "用户要求从刚才的专辑中‘抽一首’、‘发第一首’或发送某条曲目时，"
                        "应使用专辑曲目结果里的歌曲名或 song_id 调用本工具。"
                        "重名时会返回带 ID 的候选而不擅自发送；只查询歌曲信息时不要调用。"
                    ),
                    permission=PermissionLevel.USER,
                    risk=RiskClass.SEND,
                    allowed_origins=frozenset(
                        {TurnOrigin.USER_MESSAGE, TurnOrigin.SCHEDULED_AUTOMATION}
                    ),
                    timeout_seconds=30,
                ),
                input_model=ShareMusicInput,
                output_model=ShareMusicOutput,
                handler=self._share_music,
            )
        )
        registrar.register_tool(
            ToolRegistration(
                metadata=ToolMetadata(
                    name="share_netease_album",
                    description=(
                        "仅当用户明确要求发送或分享网易云专辑卡片到当前 QQ 会话时调用。"
                        "工具会自行搜索专辑、保留 album_id、继续读取专辑详情和曲目，再发送卡片；"
                        "不要用本工具发送、抽取或播放专辑中的单曲，那应调用单曲分享工具。"
                        "不要要求用户手动提供网易云链接。重名时返回带 ID 的候选供用户选择。"
                    ),
                    permission=PermissionLevel.USER,
                    risk=RiskClass.SEND,
                    allowed_origins=frozenset(
                        {TurnOrigin.USER_MESSAGE, TurnOrigin.SCHEDULED_AUTOMATION}
                    ),
                    timeout_seconds=45,
                ),
                input_model=ShareAlbumInput,
                output_model=ShareAlbumOutput,
                handler=self._share_album,
            )
        )

    async def start(self, context: PluginContext) -> None:
        self._context = context

    async def stop(self) -> None:
        self._context = None
        self._sent_album_events.clear()

    async def _share_music(self, raw_request: BaseModel) -> ShareMusicOutput | ToolResult:
        request = ShareMusicInput.model_validate(raw_request.model_dump())
        context = self._running_context()
        if request.song_id.strip():
            candidates_or_error = await self._get_song(context, request.song_id.strip())
            if isinstance(candidates_or_error, ToolResult):
                return candidates_or_error
            candidates = candidates_or_error
            if not candidates:
                return _intermediate_result(
                    ShareMusicOutput(
                        status="not_found",
                        message="没有找到这个网易云歌曲 ID，请重新搜索后再选择",
                    )
                )
            selected = candidates[0]
        else:
            search_query = _combined_query(request.query, request.artist)
            candidates_or_error = await self._search_songs(context, search_query)
            if isinstance(candidates_or_error, ToolResult):
                return candidates_or_error
            candidates = candidates_or_error
            if not candidates:
                return _intermediate_result(
                    ShareMusicOutput(
                        status="not_found",
                        message="没有搜索到匹配的网易云歌曲，请更换歌曲名或补充歌手",
                    )
                )
            selected = _select_unambiguous(
                query=request.query,
                artist=request.artist,
                candidates=candidates,
            )
            if selected is None:
                return _intermediate_result(
                    ShareMusicOutput(
                        status="selection_required",
                        message="结果不够明确，请列出候选歌曲、歌手和 song_id 供用户选择",
                        candidates=candidates,
                    )
                )

        sent = await context.onebot.send_music_card(
            provider="netease",
            resource_id=selected.song_id,
        )
        if not sent.ok:
            return ToolResult(
                ok=False,
                error_code="music_card.send_failed",
                detail=sent.detail or "NapCat 未能发送网易云音乐卡片",
                data={"song": selected.model_dump(mode="json")},
            )
        return ShareMusicOutput(
            status="sent",
            message="网易云音乐卡片已发送到当前会话，不要再重复发送链接",
            selected=selected,
        )

    async def _share_album(self, raw_request: BaseModel) -> ShareAlbumOutput | ToolResult:
        request = ShareAlbumInput.model_validate(raw_request.model_dump())
        context = self._running_context()
        current = await context.messages.get_current()
        current_message_id = current.message_id if current is not None else ""
        if current_message_id:
            already_sent = self._sent_album_events.get(current_message_id)
            if already_sent is not None:
                return already_sent.model_copy(
                    update={
                        "message": (
                            "这条用户消息对应的网易云专辑卡片已经发送成功，"
                            "不要再次调用任何搜索或发送工具"
                        )
                    }
                )
        current_title = _quoted_album_title(current.text if current is not None else "")
        if current_title:
            # The current real message is authoritative for the requested title.
            # A model-supplied historical ID or fuzzy query must not override it.
            current_text_key = _search_key(current.text) if current is not None else ""
            requested_artist = request.artist.strip()
            if requested_artist and _search_key(requested_artist) not in current_text_key:
                requested_artist = ""
            request = ShareAlbumInput(query=current_title, artist=requested_artist)
        selected: AlbumCandidate | None = None

        if request.album_id.strip():
            album_id = request.album_id.strip()
        else:
            candidates_or_error = await self._search_albums(
                context,
                _combined_query(request.query, request.artist),
            )
            if isinstance(candidates_or_error, ToolResult):
                return candidates_or_error
            candidates = candidates_or_error
            if not candidates:
                return _album_intermediate(
                    ShareAlbumOutput(
                        status="not_found",
                        message="没有搜索到匹配的网易云专辑，请更换专辑名或补充歌手",
                    )
                )
            selected = _select_album(
                query=request.query,
                artist=request.artist,
                candidates=candidates,
            )
            if selected is None:
                return _album_intermediate(
                    ShareAlbumOutput(
                        status="selection_required",
                        message="结果不够明确，请列出候选专辑、歌手和 album_id 供用户选择",
                        candidates=candidates,
                    )
                )
            album_id = selected.album_id

        detail_or_error = await self._get_album(context, album_id)
        if isinstance(detail_or_error, ToolResult):
            return detail_or_error
        detail, tracks, track_count = detail_or_error
        if detail is None:
            return _album_intermediate(
                ShareAlbumOutput(
                    status="not_found",
                    message="没有找到这个网易云专辑 ID，请重新搜索后再选择",
                )
            )
        selected = _merge_album(selected, detail)
        if current_title and _search_key(selected.title) != _search_key(current_title):
            return ToolResult(
                ok=False,
                error_code="music_card.album_mismatch",
                detail=(
                    f"搜索结果《{selected.title}》与用户明确要求的"
                    f"《{current_title}》不一致，已拒绝发送"
                ),
                data={"album": selected.model_dump(mode="json")},
                mutation_committed=False,
            )
        if not selected.cover_url:
            return ToolResult(
                ok=False,
                error_code="music_card.album_cover_missing",
                detail="专辑详情没有可用封面，无法生成 QQ 专辑卡片",
                data={"album": selected.model_dump(mode="json")},
            )

        artist_text = " / ".join(selected.artists)
        details = [f"网易云专辑 · {track_count} 首"]
        if selected.publish_date:
            details.append(selected.publish_date)
        sent = await context.onebot.send_custom_music_card(
            url=f"https://y.music.163.com/m/album?id={selected.album_id}",
            image=selected.cover_url,
            title=selected.title,
            singer=artist_text,
            content=" · ".join(details),
        )
        if not sent.ok:
            return ToolResult(
                ok=False,
                error_code="music_card.send_failed",
                detail="QQ 未能发送这张专辑音乐卡片，请稍后重试",
                data={"album": selected.model_dump(mode="json")},
            )
        output = ShareAlbumOutput(
            status="sent",
            message=(
                "专辑音乐卡片已发送到当前会话；曲目也已返回。"
                "本轮发送已经完成，必须停止调用搜索或发送工具"
            ),
            selected=selected,
            tracks=tracks,
            track_count=track_count,
        )
        if current_message_id:
            if len(self._sent_album_events) >= _MAX_SENT_EVENT_CACHE:
                self._sent_album_events.pop(next(iter(self._sent_album_events)))
            self._sent_album_events[current_message_id] = output
        return output

    async def _search_songs(
        self,
        context: PluginContext,
        query: str,
    ) -> tuple[SongCandidate, ...] | ToolResult:
        result = await context.mcp.call(
            _SERVER_ID,
            "music_search",
            {
                "query": query,
                "category": "song",
                "page": 1,
                "page_size": 5,
                "detail_level": "summary",
            },
        )
        if not result.ok:
            return _mcp_failure(result, "搜索网易云歌曲失败")
        data = _structured_data(result)
        return _song_candidates(data.get("items")) if data is not None else ()

    async def _get_song(
        self,
        context: PluginContext,
        song_id: str,
    ) -> tuple[SongCandidate, ...] | ToolResult:
        result = await context.mcp.call(
            _SERVER_ID,
            "get_songs",
            {"song_ids": [song_id], "detail_level": "summary"},
        )
        if not result.ok:
            return _mcp_failure(result, "读取网易云歌曲失败")
        data = _structured_data(result)
        return _song_candidates(data.get("songs")) if data is not None else ()

    async def _search_albums(
        self,
        context: PluginContext,
        query: str,
    ) -> tuple[AlbumCandidate, ...] | ToolResult:
        result = await context.mcp.call(
            _SERVER_ID,
            "music_search",
            {
                "query": query,
                "category": "album",
                "page": 1,
                "page_size": 10,
                "detail_level": "summary",
            },
        )
        if not result.ok:
            return _mcp_failure(result, "搜索网易云专辑失败")
        data = _structured_data(result)
        return _album_candidates(data.get("items")) if data is not None else ()

    async def _get_album(
        self,
        context: PluginContext,
        album_id: str,
    ) -> tuple[AlbumCandidate | None, tuple[AlbumTrack, ...], int] | ToolResult:
        result = await context.mcp.call(
            _SERVER_ID,
            "get_album",
            {
                "album_id": album_id,
                "include_tracks": True,
                "track_page": 1,
                "track_page_size": 50,
            },
        )
        if not result.ok:
            return _mcp_failure(result, "读取网易云专辑失败")
        data = _structured_data(result)
        if data is None:
            return None, (), 0
        detail = _album_detail(data)
        tracks = _album_tracks(data.get("tracks"))
        track_count = _non_negative_int(data.get("size"), fallback=len(tracks))
        return detail, tracks, track_count

    def _running_context(self) -> PluginContext:
        if self._context is None:
            raise RuntimeError("NetEase music card plugin is not running")
        return self._context


def _combined_query(query: str, artist: str) -> str:
    return " ".join(value for value in (query.strip(), artist.strip()) if value)


def _structured_data(result: ToolResult | object) -> Mapping[str, JsonValue] | None:
    data = getattr(result, "data", None)
    if not isinstance(data, dict):
        return None
    envelope = data.get("result")
    if not isinstance(envelope, dict):
        return None
    structured = envelope.get("data")
    return cast(Mapping[str, JsonValue], structured) if isinstance(structured, dict) else None


def _song_candidates(value: JsonValue | None) -> tuple[SongCandidate, ...]:
    if not isinstance(value, list):
        return ()
    candidates: list[SongCandidate] = []
    seen: set[str] = set()
    for raw in value[:10]:
        if not isinstance(raw, dict):
            continue
        song_id = str(raw.get("id", "")).strip()
        title = str(raw.get("title", "")).strip()
        if _ID_PATTERN.fullmatch(song_id) is None or not title or song_id in seen:
            continue
        candidates.append(
            SongCandidate(
                song_id=song_id,
                title=title[:200],
                artists=_artist_names(raw.get("artists")),
            )
        )
        seen.add(song_id)
    return tuple(candidates)


def _album_candidates(value: JsonValue | None) -> tuple[AlbumCandidate, ...]:
    if not isinstance(value, list):
        return ()
    candidates: list[AlbumCandidate] = []
    seen: set[str] = set()
    for raw in value[:10]:
        if not isinstance(raw, dict):
            continue
        candidate = _album_from_mapping(raw)
        if candidate is None or candidate.album_id in seen:
            continue
        candidates.append(candidate)
        seen.add(candidate.album_id)
    return tuple(candidates)


def _album_detail(value: Mapping[str, JsonValue]) -> AlbumCandidate | None:
    return _album_from_mapping(value)


def _album_from_mapping(raw: Mapping[str, JsonValue]) -> AlbumCandidate | None:
    album_id = str(raw.get("id", "")).strip()
    title = str(raw.get("name", raw.get("title", ""))).strip()
    if _ID_PATTERN.fullmatch(album_id) is None or not title:
        return None
    cover_url = str(raw.get("cover_url", "") or "").strip()
    publish_date = str(raw.get("publish_date", "") or "").strip()
    return AlbumCandidate(
        album_id=album_id,
        title=title[:200],
        artists=_artist_names(raw.get("artists")),
        cover_url=cover_url[:2_000],
        publish_date=publish_date[:32],
    )


def _album_tracks(value: JsonValue | None) -> tuple[AlbumTrack, ...]:
    if not isinstance(value, list):
        return ()
    tracks: list[AlbumTrack] = []
    seen: set[str] = set()
    for raw in value[:50]:
        if not isinstance(raw, dict):
            continue
        song_id = str(raw.get("id", "")).strip()
        title = str(raw.get("title", "")).strip()
        if _ID_PATTERN.fullmatch(song_id) is None or not title or song_id in seen:
            continue
        tracks.append(
            AlbumTrack(
                song_id=song_id,
                title=title[:200],
                artists=_artist_names(raw.get("artists")),
            )
        )
        seen.add(song_id)
    return tuple(tracks)


def _artist_names(value: JsonValue | None) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    names: list[str] = []
    for raw in value[:10]:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name", "")).strip()
        if name:
            names.append(name[:100])
    return tuple(names)


def _select_unambiguous(
    *,
    query: str,
    artist: str,
    candidates: Sequence[SongCandidate],
) -> SongCandidate | None:
    if len(candidates) == 1:
        return candidates[0]
    query_key = _search_key(query)
    artist_key = _search_key(artist)
    exact_titles = [item for item in candidates if _search_key(item.title) == query_key]
    if artist_key:
        matches = [
            item
            for item in exact_titles
            if any(artist_key in _search_key(name) for name in item.artists)
        ]
        return matches[0] if len(matches) == 1 else None
    if len(exact_titles) == 1:
        return exact_titles[0]
    artist_query_matches = [
        item for item in candidates if any(_search_key(name) == query_key for name in item.artists)
    ]
    if artist_query_matches:
        return artist_query_matches[0]
    combined = [
        item
        for item in candidates
        if _search_key(item.title) in query_key
        and any(_search_key(name) in query_key for name in item.artists)
    ]
    return combined[0] if len(combined) == 1 else None


def _select_album(
    *,
    query: str,
    artist: str,
    candidates: Sequence[AlbumCandidate],
) -> AlbumCandidate | None:
    query_key = _search_key(query)
    artist_key = _search_key(artist)
    exact_titles = [item for item in candidates if _search_key(item.title) == query_key]
    if artist_key:
        matches = [
            item
            for item in exact_titles
            if any(artist_key in _search_key(name) for name in item.artists)
        ]
        return matches[0] if len(matches) == 1 else None
    return exact_titles[0] if len(exact_titles) == 1 else None


def _quoted_album_title(value: str) -> str:
    match = _QUOTED_TITLE_PATTERN.search(value)
    return match.group(1).strip() if match is not None else ""


def _merge_album(
    search_candidate: AlbumCandidate | None,
    detail: AlbumCandidate,
) -> AlbumCandidate:
    if search_candidate is None:
        return detail
    return AlbumCandidate(
        album_id=detail.album_id,
        title=detail.title or search_candidate.title,
        artists=detail.artists or search_candidate.artists,
        cover_url=detail.cover_url or search_candidate.cover_url,
        publish_date=detail.publish_date or search_candidate.publish_date,
    )


def _non_negative_int(value: JsonValue | None, *, fallback: int) -> int:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        return fallback
    return max(parsed, 0)


def _search_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


def _mcp_failure(result: object, fallback: str) -> ToolResult:
    detail = str(getattr(result, "detail", "")).strip() or fallback
    return ToolResult(
        ok=False,
        error_code="music_card.mcp_failed",
        detail=detail[:1_000],
    )


def _intermediate_result(output: ShareMusicOutput) -> ToolResult:
    return ToolResult(
        data={"result": output.model_dump(mode="json")},
        mutation_committed=False,
    )


def _album_intermediate(output: ShareAlbumOutput) -> ToolResult:
    return ToolResult(
        data={"result": output.model_dump(mode="json")},
        mutation_committed=False,
    )
