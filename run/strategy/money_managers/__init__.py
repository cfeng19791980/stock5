# -*- coding: utf-8 -*-
"""
资金管理模块
"""
from .fixed_ratio import FixedRatioMM
from .kelly import KellyMM

__all__ = ["FixedRatioMM", "KellyMM"]