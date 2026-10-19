"""人格档案版本管理 —— 人格学习是漫长的过程，每一步都要能回头。

三个月、半年、一年……侧写会一遍遍重跑，档案会一遍遍更新。
但每次更新都可能改砸（新数据质量差、意向写错了、算法退步了），
所以：每次覆盖前自动存档旧版，随时列出、随时回滚。

某开源项目 用实践验证过这个机制的价值，思念把它做成核心能力。
"""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path


class PersonaVault:
    """人格档案的保险柜：自动存档 + 回滚。"""

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self.archive_dir = self.data_dir / "versions"
        self.live_path = self.data_dir / "persona.json"

    def snapshot(self, reason: str = "") -> str | None:
        """把当前生效的档案存一份带时间戳的副本。返回版本名。"""
        if not self.live_path.exists():
            return None
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        suffix = f"-{reason}" if reason else ""
        name = f"persona-{stamp}{suffix}.json"
        shutil.copy2(self.live_path, self.archive_dir / name)
        return name

    def list_versions(self) -> list[str]:
        if not self.archive_dir.exists():
            return []
        return sorted(p.name for p in self.archive_dir.glob("persona-*.json"))

    def rollback(self, version: str) -> None:
        """回滚到某个历史版本。当前版本也会先存档，回滚本身也可回头。"""
        src = self.archive_dir / version
        if not src.exists():
            raise FileNotFoundError(
                f"版本 '{version}' 不存在。现有版本：{self.list_versions()}")
        self.snapshot(reason="before-rollback")
        shutil.copy2(src, self.live_path)
