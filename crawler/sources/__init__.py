# -*- coding: utf-8 -*-
"""来源注册表：统一 search/fetch 接口，main.py 按名称分发。"""
from .dept import DeptSource
from .flk import FlkSource
from .moj import MojSource
from .sichuan import SichuanSource

SOURCES = {
    "flk": FlkSource,        # 国家法律法规库（全国人大）
    "moj": MojSource,        # 国家行政法规库（司法部）
    "dept": DeptSource,      # 部门规章（政策文件库/部委官网）
    "sichuan": SichuanSource,  # 四川省法规规章数据库（playwright）
}
