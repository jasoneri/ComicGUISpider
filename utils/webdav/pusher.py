# -*- coding: utf-8 -*-
"""推送编排（CGS013 §3）：条目 → 本地收集 → 幂等判定 → 上传 → 远端 size 回读。

无清单、无本地推送记录：**幂等 = 远端同路径同 size ⇒ 跳过**（§3.2），
内容变化（size 变）才重传。单条目失败只标记该条目并继续，不中止整批（§3.4）——
没有需要保护的清单原子性，也就没有「整批撤销」的必要。
"""
import hashlib
import json
import pathlib as p
import traceback
import typing as t

import httpx

from utils.webdav.client import WebDavClient, WebDavError, WebDavAuthError, WebDavLockedError, WebDavNotFoundError


class WebDavSizeMismatchError(WebDavError):
    """写后远端大小与本地不符，允许重传本次目标。"""


def entry_id(local_path: str, remote_relative_path: str) -> str:
    return hashlib.sha1(f"{local_path}\0{remote_relative_path}".encode("utf-8")).hexdigest()


def resolve_page_order(local_dir, names: t.Iterable[str]) -> list[str]:
    """`__sorted_record` 优先，缺失退回文件名字典序。

    记录格式未在项目内钉死，支持两种:JSON 数组(`["003.jpg", ...]` 或带
    `page_order`/`order`/`pages` 键的对象)与每行一个文件名的纯文本。
    记录中不存在的文件名按字典序补在末尾。
    """
    names = sorted(names)
    record = p.Path(local_dir).joinpath("__sorted_record")
    if not record.is_file():
        return names
    try:
        raw = record.read_text(encoding="utf-8").strip()
    except OSError as e:
        raise WebDavError(f"__sorted_record 读取失败: {record} ({e})") from e
    if not raw:
        return names
    order: list = []
    if raw.startswith(("[", "{")):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            raise WebDavError(f"__sorted_record 不是合法 JSON: {record} ({e})") from e
        if isinstance(parsed, dict):
            parsed = next((parsed[k] for k in ("page_order", "order", "pages") if parsed.get(k)), None)
        order = list(parsed or [])
    else:
        order = [line.strip() for line in raw.splitlines() if line.strip()]
    if not order:
        return names
    known = set(names)
    ordered = [str(n) for n in order if str(n) in known]
    rest = [n for n in names if n not in set(ordered)]
    return ordered + rest


def _collect(entry: dict) -> tuple[str, str, list[p.Path], list[str]]:
    """remote_relative_path 在 cbz 条目中是文件，在 dir 条目中是目录。"""
    local = p.Path(entry["local_path"])
    remote = entry["remote_relative_path"]
    if not isinstance(remote, str) or "\\" in remote or any(s in ("", ".", "..") for s in remote.split("/")):
        raise WebDavError("remote_relative_path 必须是非空的相对路径，且不含上级目录")
    kind = entry["kind"]
    if not entry["library_root"]:
        raise WebDavError(f"library_root 不能为空: {local}")
    library_root = p.Path(entry["library_root"]).resolve(strict=True)
    local_root = local.resolve(strict=True)
    if not library_root.is_dir() or not local_root.is_relative_to(library_root):
        raise WebDavError(f"本地路径超出扫描根目录: {local} (根目录: {library_root})")
    if kind == "cbz":
        if not local_root.is_file():
            raise WebDavError(f"本地 CBZ 文件类型已改变: {local}")
        return "cbz", remote, [local], []
    if kind != "dir":
        raise WebDavError(f"不支持的上传类型: {kind}")
    if not local_root.is_dir():
        raise WebDavError(f"本地目录类型已改变: {local}")
    names = []
    for file in local.iterdir():
        if not file.is_file():
            continue
        if not file.resolve(strict=True).is_relative_to(local_root):
            raise WebDavError(f"文件链接超出上传目录: {file}")
        names.append(file.name)
    order = resolve_page_order(local, names)
    return "dir", remote, [local.joinpath(n) for n in order], order


def _emit(on_progress, **info):
    if on_progress:
        on_progress(info)


def _remote_size(client: WebDavClient, remote: str) -> int | None:
    """远端同路径的 size；不存在（404）返回 None。鉴权/服务器错误照常上抛。"""
    try:
        nodes = client.propfind(remote, depth=0)
    except WebDavNotFoundError:
        return None
    return nodes[0].get("size") if nodes else None


def _verify_remote_size(client: WebDavClient, remote: str, size: int) -> None:
    nodes = client.propfind(remote, depth=0)
    if not nodes:
        raise WebDavSizeMismatchError(f"上传后远端文件缺失: {remote}")
    if nodes[0].get("size") != size:
        raise WebDavSizeMismatchError(f"上传后远端大小不符: {remote} ({nodes[0].get('size')} != {size})")


def _relative_to_root(local_path: str, library_root: str) -> str:
    """相对库根的 posix 本地路径——上传历史行唯一锚点 `(relative_path, mode)` 的映射键。

    与 `_collect` 的库根约束同一基准；解析失败（空 root 等）返回空串，由历史层按无键处理。
    """
    try:
        return p.Path(local_path).resolve().relative_to(p.Path(library_root).resolve()).as_posix()
    except (OSError, ValueError):
        return ""


def _fail(result: dict, *, eid: str, book: str, ep: str, title: str, local_path: str,
          relative_path: str, reason: str):
    """CGS013 §3.4：失败项必须带 local_path，UI 才能精确重推同一任务。"""
    result["failed"].append({"id": eid, "book": book, "ep": ep, "title": title, "local_path": local_path,
                             "relative_path": relative_path, "reason": reason})


def _plan_files(entry: dict) -> int:
    """纯本地预扫描：该条目计划上传的文件数。预扫描失败按 0 计，不中止批次。"""
    try:
        _kind, _remote, files, _order = _collect(entry)
    except (OSError, WebDavError):
        return 0
    return len(files)


def push_entries(client: WebDavClient, entries: list[dict], on_progress: t.Callable[[dict], None] | None = None) -> dict:
    """推送条目并返回 {"pushed": [...], "failed": [...], "skipped": [...]}。

    `on_progress(info: dict)` 事件：`plan` / `entry` / `file`（phase=start|progress|skip|verify|done）/ `abort`。
    `plan` 先给出本批总文件数；此后离散事件都带 `progress`（已完成的文件格数），
    只有 `skip` / `done` 推进它，逐分片的 `progress` phase 不推进。

    落地行（pushed/skipped）额外带 `size`（上传时本地字节和：cbz=单文件，dir=文件累加）
    与 `relative_path`（相对 library_root 的 posix 路径）；失败行也带 `relative_path`
    但不带 `size`。两个键是上传历史（utils/webdav/history.py）的映射信息输入，
    幂等判定与远端交互零改动。

    幂等（CGS013 §3.2）：上传前 PROPFIND 远端同路径，size 相同 ⇒ 跳过该文件，
    不开 PUT。整条目的文件全部已存在且 size 一致 ⇒ 该条目记 `skipped`。
    失败不中止：单条目失败入 `failed` 后继续下一条（§3.4）。
    """
    result: dict[str, list] = {"pushed": [], "failed": [], "skipped": []}
    total = len(entries)
    plan = [_plan_files(entry) for entry in entries]
    done_files = 0
    _emit(on_progress, event="plan", files=sum(plan), entries=total)
    for index, entry in enumerate(entries, 1):
        book, ep = entry["book"], entry["ep"]
        title = entry["title"]
        local_path = str(entry["local_path"])
        relative_path = _relative_to_root(local_path, entry["library_root"])
        eid = entry_id(local_path, entry["remote_relative_path"])
        settled = 0
        entry_bytes = 0
        _emit(on_progress, event="entry", index=index, total=total, id=eid, local_path=local_path, progress=done_files)
        try:
            kind, remote_path, files, _page_order = _collect(entry)
        except (OSError, WebDavError):
            _fail(result, eid=eid, book=book, ep=ep, title=title, local_path=local_path,
                  relative_path=relative_path, reason=traceback.format_exc())
            done_files += plan[index - 1]
            _emit(on_progress, event="abort", id=eid, reason="本地收集失败", progress=done_files)
            continue
        if not files:
            _fail(result, eid=eid, book=book, ep=ep, title=title, local_path=local_path,
                  relative_path=relative_path, reason="本地文件为空")
            done_files += plan[index - 1]
            _emit(on_progress, event="abort", id=eid, reason="本地文件为空", progress=done_files)
            continue
        uploaded_any = False
        try:
            remote_dir = remote_path.rpartition("/")[0] if kind == "cbz" else remote_path
            client.mkdir_p(remote_dir)
            for f_index, f in enumerate(files, 1):
                remote = remote_path if kind == "cbz" else f"{remote_dir}/{f.name}"
                size = f.stat().st_size
                entry_bytes += size
                if _remote_size(client, remote) == size:
                    settled += 1
                    done_files += 1
                    _emit(on_progress, event="file", phase="skip", index=f_index, total=len(files), name=f.name, size=size,
                          remote=remote, progress=done_files)
                    continue
                _emit(on_progress, event="file", phase="start", index=f_index, total=len(files), name=f.name, size=size, remote=remote)

                def _byte_progress(sent, total_bytes, _name=f.name, _remote=remote, _i=f_index):
                    _emit(on_progress, event="file", phase="progress", index=_i, total=len(files),
                          name=_name, remote=_remote, sent=sent, size=total_bytes)

                client.put_file(f, remote, on_progress=_byte_progress)
                _emit(on_progress, event="file", phase="verify", index=f_index, total=len(files), name=f.name, size=size, remote=remote)
                try:
                    _verify_remote_size(client, remote, size)
                except WebDavSizeMismatchError:
                    client.delete(remote, missing_ok=True)
                    client.put_file(f, remote, on_progress=_byte_progress)
                    _emit(on_progress, event="file", phase="verify", index=f_index, total=len(files), name=f.name, size=size, remote=remote)
                    _verify_remote_size(client, remote, size)
                settled += 1
                done_files += 1
                _emit(on_progress, event="file", phase="done", index=f_index, total=len(files), name=f.name, size=size,
                      remote=remote, progress=done_files)
                uploaded_any = True
        except (WebDavAuthError, WebDavLockedError):
            raise
        except (OSError, WebDavError, httpx.TransportError) as e:
            _fail(result, eid=eid, book=book, ep=ep, title=title, local_path=local_path,
                  relative_path=relative_path, reason=traceback.format_exc())
            done_files += plan[index - 1] - settled
            _emit(on_progress, event="abort", id=eid, reason=str(e), progress=done_files)
            continue
        result["pushed" if uploaded_any else "skipped"].append(
            {"id": eid, "book": book, "ep": ep, "title": title, "kind": kind, "local_path": local_path,
             "size": entry_bytes, "relative_path": relative_path}
        )
    return result
