"""Compatibility alias for the renamed sibling-packing topology."""

from .sibling import SiblingTopologyMixin

RecursiveTopologyMixin = SiblingTopologyMixin

__all__ = ["RecursiveTopologyMixin"]
