"""
VTuber Engine - Server-authoritative avatar control via Redis backbone.

This package transforms the VTuber avatar from client-side JavaScript control
to server-controlled Python with Redis as the single source of truth.
The browser becomes a "dumb renderer" - Python runs a 24fps loop controlling all animation.
"""

from .redis_backbone import RedisBackbone
from .avatar_controller import AvatarController
from .parameter_blender import ParameterBlender

__all__ = [
    "RedisBackbone",
    "AvatarController",
    "ParameterBlender",
]
