from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel
from eos_client import eos_client, BoardState

router = APIRouter()


class ChannelLevel(BaseModel):
    id: int
    level: int  # 0–100


class BoardStateResponse(BaseModel):
    show_name:        Optional[str]
    active_cue:       Optional[str]
    active_cue_list:  Optional[str]
    active_cue_label: Optional[str]
    next_cue:         Optional[str]
    next_cue_list:    Optional[str]
    mode:             str
    connected:        bool
    last_updated:     Optional[float]
    cue_count:        Optional[int]
    channels:         list[ChannelLevel]


def _to_response(bs: BoardState) -> BoardStateResponse:
    ch_list = sorted(
        [ChannelLevel(id=k, level=v) for k, v in bs.channels.items()],
        key=lambda c: c.id,
    )
    return BoardStateResponse(
        show_name=bs.show_name,
        active_cue=bs.active_cue,
        active_cue_list=bs.active_cue_list,
        active_cue_label=bs.active_cue_label,
        next_cue=bs.next_cue,
        next_cue_list=bs.next_cue_list,
        mode=bs.mode,
        connected=bs.connected,
        last_updated=bs.last_updated,
        cue_count=bs.cue_count,
        channels=ch_list,
    )


@router.get("/api/board-state", response_model=BoardStateResponse)
async def board_state() -> BoardStateResponse:
    return _to_response(eos_client.board_state)
