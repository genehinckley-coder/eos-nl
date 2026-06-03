import dataclasses
from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel
from eos_client import eos_client

router = APIRouter()


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


@router.get("/api/board-state", response_model=BoardStateResponse)
async def board_state() -> BoardStateResponse:
    return BoardStateResponse(**dataclasses.asdict(eos_client.board_state))
