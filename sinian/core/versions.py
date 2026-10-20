"""人格档案版本管理 —— 人格学习是漫长的过程，每一步都要能回头。

三个月、半年、一年……侧写会一遍遍重跑，档案会一遍遍更新。
但每次更新都可能改砸（新数据质量差、意向写错了、算法退步了），
所以：每次覆盖前自动存档旧版，随时列出、随时回滚。

版本管理是人格学习的必备能力：每一次覆盖前都自动存档，随时能回滚。
"""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path


def payload_sha256(path: str | Path) -> str:
    """档案指纹（payload_sha256 防篡改）：
    改一个字指纹就变，谁动过人格一目了然。
    """
    raw = Path(path).read_bytes()
    return hashlib.sha256(raw).hexdigest()


class PersonaVault:
    """人格档案的保险柜：自动存档 + 指纹登记 + 可校验回滚。"""

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self.archive_dir = self.data_dir / "versions"
        self.live_path = self.data_dir / "persona.json"
        self.index_path = self.archive_dir / "index.json"

    def _index(self) -> dict:
        if self.index_path.exists():
            return json.loads(self.index_path.read_text(encoding="utf-8"))
        return {}

    def _put_index(self, data: dict) -> None:
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    def snapshot(self, reason: str = "") -> str | None:
        """把当前生效的档案存一份带时间戳的副本，并登记指纹。返回版本名。"""
        if not self.live_path.exists():
            return None
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        suffix = f"-{reason}" if reason else ""
        name = f"persona-{stamp}{suffix}.json"
        dest = self.archive_dir / name
        shutil.copy2(self.live_path, dest)
        idx = self._index()
        idx[name] = {"sha256": payload_sha256(dest),
                     "at": datetime.now().isoformat(timespec="seconds")}
        self._put_index(idx)
        return name

    def list_versions(self) -> list[str]:
        if not self.archive_dir.exists():
            return []
        return sorted(p.name for p in self.archive_dir.glob("persona-*.json"))

    def verify(self, version: str) -> bool:
        """校验某个历史版本是否被改动过。"""
        idx = self._index()
        if version not in idx:
            return False
        return payload_sha256(self.archive_dir / version) == idx[version]["sha256"]

    def rollback(self, version: str) -> None:
        """回滚到某个历史版本。

        回滚前先验指纹——被改动过的存档不配用来覆盖现在的人格。
        当前版本也会先存档，回滚本身也可回头。
        """
        src = self.archive_dir / version
        if not src.exists():
            raise FileNotFoundError(
                f"版本 '{version}' 不存在。现有版本：{self.list_versions()}")
        if version in self._index() and not self.verify(version):
            raise ValueError(
                f"版本 '{version}' 的指纹对不上，存档被改动过，拒绝回滚。"
                "如果确实要用，请手动复制该文件。")
        self.snapshot(reason="before-rollback")
        shutil.copy2(src, self.live_path)
