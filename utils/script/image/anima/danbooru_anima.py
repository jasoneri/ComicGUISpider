# -*- coding: utf-8 -*-
"""danbooru → ANIMA 一键出图 skill.

从 danbooru post 提取 tags，按 ComicGUISpider TagPrompt 规则组装 ANIMA prompt，
驱动本地 ComfyUI (ANIMA) HTTP API 出图。自包含，仅标准库。

用法:
  python danbooru_anima.py --post-id 11915581            # 在线拉取 post (safebooru 直连 / danbooru 需代理)
  python danbooru_anima.py --json post.json              # 离线 post JSON
  python danbooru_anima.py --tags "1girl blue_hair"      # 直接给 general tags 字符串
  python danbooru_anima.py --post-id 11915581 --no-drive # 只生成 prompt 不驱动出图
  # 可选: --seed --width --height --model --steps --out --base
后端需在跑: powershell -File comfy_anima.ps1 start (8188)
"""
import argparse, json, os, sys, time, urllib.parse, urllib.request, uuid

# 双形态加载：GUI 进程按包导入，subprocess 直跑脚本时按目录导入(cwd=本目录)。
# 用 __package__ 显式分支而非 try/except，避免把真实导入错误吞掉。
if __package__:
    from . import anima_spec
    from .prompt_doc import split_prompt
else:
    import anima_spec
    from prompt_doc import split_prompt


HOST = "http://127.0.0.1:8188"
HERE = os.path.dirname(os.path.abspath(__file__))
WF = os.path.join(HERE, "anima_turbo_api_workflow.json")
DEFAULT_OUT = os.path.join(HERE, "outputs")

# 本机 ComfyUI 必须绕开代理。CGS 配置里有 HTTP_PROXY=127.0.0.1:10809，urllib 默认
# 读环境代理，会把发往 127.0.0.1:8188 的请求也一并劫走并返回 503 —— 症状伪装成
# 「ComfyUI 挂了」，排查时极易误判。显式声明本连接无代理，而不是在调用处兜住 503。
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

# WD14 图内 tag 补全（custom_nodes/ComfyUI-WD14-Tagger）。OUTPUT_NODE=True，
# 故 tag 可从 /history 读回，无需第二次请求。
WD14_NODE = "WD14Tagger|pysssss"
WD14_DEFAULT_MODEL = "wd-vit-tagger-v3"
WD14_UPLOAD_SUBFOLDER = "cgs_anima"

# --- 主流预设 (grok-search 精选 + 本机验证) ---
# 来源: docs.comfy.org Anima Base v1 教程 / comfy.org Anima workflow / ComfyUI-Anima-NAG repo。
# 本机仅有 3 个 UNET (无 turbo LoRA/lllite/upscale 模型文件)，故预设集合=可真实出图的 txt2img。
# 官方参数: Base 30-50步/CFG4-5, Turbo LoRA 12步/CFG1.0, 采样器 er_sde, 调度器 simple。
# 官方推荐基线见 anima_spec (M5/M6)。aesthetic 按 M7 剔除 score_*。
DEFAULT_QUALITY_PREFIX = anima_spec.OFFICIAL_POSITIVE_PREFIX
DEFAULT_NEGATIVE = anima_spec.OFFICIAL_NEGATIVE
AESTHETIC_QUALITY_PREFIX = "masterpiece, best quality, safe"
AESTHETIC_NEGATIVE = ("worst quality, low quality, artist name, blurry, "
                      "jpeg artifacts, chromatic aberration")

ANIMA_PRESETS = {
    "turbo": {
        "label": "Turbo (fast)",
        "model": "anima-turbo-v1.0.safetensors",
        "steps": 12, "cfg": 1.0, "sampler": "er_sde", "scheduler": "simple", "denoise": 1.0,
        "quality_prefix": DEFAULT_QUALITY_PREFIX, "negative": DEFAULT_NEGATIVE,
        "desc": "官方 Turbo LoRA 档位参数(12步/CFG1)，约15s 出图，速度最快",
    },
    "base": {
        "label": "Base (quality)",
        "model": "anima-base-v1.0.safetensors",
        "steps": 40, "cfg": 4.5, "sampler": "er_sde", "scheduler": "simple", "denoise": 1.0,
        "quality_prefix": DEFAULT_QUALITY_PREFIX, "negative": DEFAULT_NEGATIVE,
        "desc": "官方 Base 档位(40步/CFG4.5)，细节与构图更完整",
    },
    "aesthetic": {
        "label": "Aesthetic (finetune)",
        "model": "anima-aesthetic-v1.1.safetensors",
        "steps": 40, "cfg": 3.5, "sampler": "er_sde", "scheduler": "simple", "denoise": 1.0,
        "quality_prefix": AESTHETIC_QUALITY_PREFIX, "negative": AESTHETIC_NEGATIVE,
        "desc": "Aesthetic 微调版(40步/CFG3.5)，观感更精致",
    },
}
DEFAULT_PRESET = "turbo"

# --- CGS TagPrompt 规则(独立实现, 与 ComicGUISpider/utils/script/image/danbooru/tag_prompt.py 一致) ---
TAG_GROUP_ORDER = ("Character", "Artist", "Copyright", "General", "Meta")
PROMPT_BODY_GROUPS = frozenset({"General"})  # 默认只 General(与CGS TagExport 一致); Meta 需 --include-meta
IDENTITY_GROUPS = ("Character", "Artist", "Copyright")
NOISE_TAG_BLACKLIST = frozenset({
    "highres", "absurdres", "incredibly_absurdres", "translated", "partially_translated",
    "check_translation", "commentary", "commentary_request", "artist_name", "signature",
    "watermark", "username", "twitter_username", "jpeg_artifacts", "scan",
    "image_sample", "duplicate",
})
_GROUP_ATTR = {
    "Character": "tag_string_character", "Artist": "tag_string_artist",
    "Copyright": "tag_string_copyright", "General": "tag_string_general",
    "Meta": "tag_string_meta",
}
_IDENTITY_LABEL = {"Character": "character", "Artist": "artist", "Copyright": "copyright"}


def _split_tags(text):
    return tuple(t for t in str(text or "").split(" ") if t)


def build_anima_prompt(post: dict, quality_prefix: str = DEFAULT_QUALITY_PREFIX,
                       include_meta: bool = False) -> dict:
    """按 ANIMA 官方 M3 段序组装 prompt。返回 {body, identity, prompt}

    段序: [quality/meta/year/safety] [1girl/1boy/1other] [character] [series] [@artist] [general]
    """
    body_groups = PROMPT_BODY_GROUPS | ({"Meta"} if include_meta else set())
    groups = []
    for label in TAG_GROUP_ORDER:
        tags = _split_tags(post.get(_GROUP_ATTR[label]))
        if tags:
            groups.append((label, tags))

    prefix_extra, subjects, body, seen = [], [], [], set()
    for label, tags in groups:
        if label not in body_groups:
            continue
        for raw_tag in tags:
            if raw_tag in NOISE_TAG_BLACKLIST:
                continue
            tag = anima_spec.normalize_tag(raw_tag)
            if tag in seen:
                continue
            seen.add(tag)
            if anima_spec.is_subject_count_tag(tag):
                subjects.append(tag)      # M3 独立槽位，须前置于 character
            elif anima_spec.is_prefix_tag(tag):
                prefix_extra.append(tag)  # 质量/安全/时期/meta 归首槽
            else:
                body.append(tag)

    identity = {}
    for label in IDENTITY_GROUPS:
        tags = [anima_spec.normalize_tag(t) for t in _split_tags(post.get(_GROUP_ATTR[label]))
                if t not in NOISE_TAG_BLACKLIST]
        if tags:
            identity[_IDENTITY_LABEL[label]] = tags
    if "artist" in identity:  # M4: 缺 @ 时模型响应极弱
        identity["artist"] = [t if t.startswith("@") else f"@{t}" for t in identity["artist"]]

    prefix = ", ".join(x for x in [str(quality_prefix or "").strip().rstrip(",")] + prefix_extra if x)
    parts = ([prefix] if prefix else []) + subjects
    for label in ("character", "copyright", "artist"):
        parts.extend(identity.get(label, []))
    parts.extend(body)
    return {"body": ", ".join(body), "identity": identity, "prompt": ", ".join(parts)}


# --- 数据源 ---
def fetch_post(post_id: int, base: str = "safebooru") -> dict:
    """在线拉取 post JSON。safebooru 直连; danbooru.donmai.us 需本机代理。"""
    url = f"https://{base}.donmai.us/posts/{post_id}.json"
    with urllib.request.urlopen(url, timeout=20) as resp:
        return json.loads(resp.read().decode())


def load_post(args) -> dict:
    if args.prompt is not None:
        return {
            "tag_string_general": "",
            "tag_string_character": "",
            "tag_string_artist": "",
            "tag_string_copyright": "",
            "tag_string_meta": "",
        }
    if args.json:
        with open(args.json, encoding="utf-8") as f:
            return json.load(f)
    if args.post_id:
        return fetch_post(args.post_id, base=args.base)
    if args.tags:
        return {"tag_string_general": args.tags, "tag_string_character": "",
                "tag_string_artist": "", "tag_string_copyright": "", "tag_string_meta": ""}
    raise SystemExit("需要 --post-id / --json / --tags 之一")


def resolve_positive(args, post: dict, quality_prefix: str):
    """成品 prompt 优先于 tag 重建。

    GUI 的编辑器允许用户手改 prompt，提交时必须逐字下发；若仍走 build_anima_prompt
    重建，用户的编辑会被静默丢弃。故 --prompt / job.json 的 positive_base 一旦存在，
    即完全跳过 tag 组装链路。
    """
    raw = args.prompt if args.prompt is not None else post.get("positive_base")
    if raw is not None and str(raw).strip():
        return str(raw), None
    built = build_anima_prompt(post, quality_prefix=quality_prefix,
                               include_meta=args.include_meta)
    return built["prompt"], built


# --- 出图驱动 (提取自 drive_anima.py, 已验证) ---
def _resolve_host(host: str | None = None) -> str:
    resolved = str(host or HOST or "").strip().rstrip("/")
    if not resolved:
        raise RuntimeError("Comfy host is empty; configure script conf comfy.host before calling Comfy APIs.")
    return resolved


def _req(path, data=None, timeout=60, host: str | None = None):
    url = _resolve_host(host) + path
    if data is not None:
        body = json.dumps(data).encode()
        r = urllib.request.Request(url, data=body, method="POST",
                                   headers={"Content-Type": "application/json"})
    else:
        r = urllib.request.Request(url)
    with _OPENER.open(r, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def wd14_status(timeout: float = 2.0, host: str | None = None) -> tuple[bool, str]:
    """(可用, 不可用的原因)。

    ComfyUI 未启动是**常态而非异常**：导出面板同时服务 Copy / imgPalace，
    不该因为出图后端没开就构造失败。但原因必须随结果一起返回并展示到 UI，
    不能只回一个 False 让调用方猜。
    """
    try:
        base = _resolve_host(host)
    except RuntimeError as exc:
        return False, str(exc)
    try:
        registered = bool(_req(
            "/object_info/" + urllib.parse.quote(WD14_NODE, safe=""),
            timeout=timeout,
            host=base,
        ))
    except OSError as exc:  # URLError / timeout 均为 OSError 子类
        return False, f"ComfyUI 未响应（{base}）：{exc}"
    if not registered:
        return False, f"ComfyUI 未注册 {WD14_NODE}，请安装 ComfyUI-WD14-Tagger 后重启"
    return True, ""


def upload_image(image_path: str, subfolder: str = WD14_UPLOAD_SUBFOLDER, host: str | None = None) -> str:
    """上传图片到 ComfyUI input 区，返回 LoadImage 的 image 入参。

    走上传而非本地路径：待补全的 post 未必已下载到本地，ComfyUI 也未必与 CGS
    共享同一文件系统视图。上传是唯一不依赖这两个前提的通道。
    """
    payload = open(image_path, "rb").read()
    boundary = "----cgsAnima" + uuid.uuid4().hex
    chunks = []
    for key, value in (("subfolder", subfolder), ("overwrite", "true")):
        chunks.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode()
        )
    chunks.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="image"; '
        f'filename="{os.path.basename(image_path)}"\r\n'
        f'Content-Type: application/octet-stream\r\n\r\n'.encode()
    )
    chunks.append(payload)
    chunks.append(f"\r\n--{boundary}--\r\n".encode())
    request = urllib.request.Request(
        _resolve_host(host) + "/upload/image", data=b"".join(chunks), method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with _OPENER.open(request, timeout=120) as resp:
        info = json.loads(resp.read().decode())
    return f"{info['subfolder']}/{info['name']}" if info.get("subfolder") else info["name"]


def wd14_exclude_form(prompt: str) -> str:
    """把 CGS prompt 转成 WD14 的 `exclude_tags` 形态。

    不做排除，补全就会把 prompt 里已有的 tag 原样重复一遍。扩散模型里重复即加权，
    等于偷偷改了用户的构图意图 —— 「补全」应当只补缺口。

    形态要求来自 wd14tagger.py：排除比对在**转义括号之前**执行
    （`remove` 过滤先于 `replace("(", "\\(")`），故须给未转义形态；
    `@` 是 ANIMA 的 artist 记法，WD14 词表里没有。下划线已由
    `replace_underscore=True` 在比对前替换成空格，与本函数输出一致。
    """
    tokens = (token.lstrip("@").replace("\\(", "(").replace("\\)", ")")
              for token in split_prompt(prompt))
    return ", ".join(token for token in tokens if token)


def attach_wd14(wf: dict, image_ref: str, model: str = WD14_DEFAULT_MODEL,
                threshold: float = 0.35, character_threshold: float = 0.85,
                exclude_tags: str = "") -> dict:
    """把 WD14 补全支路接进图：11 LoadImage → 12 WD14Tagger → 13 与节点 14 拼接。

    只在补全开启时注入。关闭时整张图退回 Stage A 形态（4.text 直取 14），
    而不是留三个空转节点靠参数关掉 —— 后者会在 /history 里留下误导性的输出槽。
    """
    wf["11"] = {"class_type": "LoadImage", "inputs": {"image": image_ref}}
    wf["12"] = {
        "class_type": WD14_NODE,
        "inputs": {
            "image": ["11", 0],
            "model": model,
            "threshold": threshold,
            "character_threshold": character_threshold,
            # ANIMA 用空格分词，且 WD14 在此开关下同样输出转义括号，与 normalize_tag 同构
            "replace_underscore": True,
            "trailing_comma": False,
            "exclude_tags": exclude_tags,
        },
    }
    wf["13"] = {
        "class_type": "StringConcatenate",
        "inputs": {"string_a": ["14", 0], "string_b": ["12", 0], "delimiter": ", "},
    }
    wf["4"]["inputs"]["text"] = ["13", 0]
    return wf


def attach_img2img(wf: dict) -> dict:
    """把起始 latent 从空白换成源图编码（denoise<1.0 即重绘）。

    复用 `attach_wd14` 建的同一个节点 11 —— 一次出图只有一张源图，
    分开上传会得到两个 input 文件与两个 LoadImage，「补 tag 读的图」
    与「重绘起始的图」就可能不是同一张。

    直接删掉节点 7 而非留着空转：起始 latent 已由源图提供，空 latent 不再是
    任何节点的输入。用 del 不用 pop(default)，7 缺失意味着 workflow 被改坏，
    该当场炸而不是继续出一张构图错误的图。
    """
    wf["16"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["11", 0], "vae": ["6", 0]}}
    wf["8"]["inputs"]["latent_image"] = ["16", 0]
    del wf["7"]
    return wf


def build_workflow(prompt: str, seed: int, width: int, height: int, model: str,
                   steps: int, cfg: float = 1.0, sampler: str = "er_sde",
                   scheduler: str = "simple", denoise: float = 1.0,
                   negative: str = DEFAULT_NEGATIVE,
                   source_image: str | None = None, wd14: bool = False,
                   wd14_model: str = WD14_DEFAULT_MODEL,
                   wd14_threshold: float = 0.35,
                   host: str | None = None) -> dict:
    """组装 API 格式 workflow，不提交、不轮询。

    从 drive() 里析出的原因：GUI 侧改走常驻 ComfyUI 客户端（PRD Q9）后，
    「组装」与「提交+轮询」必须能拆开用；若 GUI 另写一份组装逻辑，
    两份 workflow 定义必然漂移，用户会看到 CLI 与 GUI 出的图不一样（R22）。
    上传源图是组装的一部分——节点里要填的是上传后的引用名，不是本地路径。
    host 为空时走模块 HOST（CLI 默认）；GUI 必须传入 conf 中的 host。
    """
    comfy_host = _resolve_host(host)
    wf = json.load(open(WF, encoding="utf-8"))
    wf["1"]["inputs"]["unet_name"] = model
    wf["14"]["inputs"]["value"] = prompt    # 正向经节点 14 注入
    wf["15"]["inputs"]["value"] = negative  # 负向经节点 15 注入(按预设下发)
    wf["7"]["inputs"]["width"] = width
    wf["7"]["inputs"]["height"] = height
    wf["8"]["inputs"]["seed"] = seed
    wf["8"]["inputs"]["steps"] = steps
    wf["8"]["inputs"]["cfg"] = cfg
    wf["8"]["inputs"]["sampler_name"] = sampler
    wf["8"]["inputs"]["scheduler"] = scheduler
    wf["8"]["inputs"]["denoise"] = denoise

    # 一张源图，两种用途：读 tag（WD14）与作起始 latent（img2img）。只上传一次。
    needs_source = wd14 or denoise < 1.0
    if needs_source and not source_image:
        raise RuntimeError(
            f"需要源图：wd14={wd14} denoise={denoise}；未给 source_image 就出图会静默退化成纯文生图。"
        )
    source_ref = upload_image(source_image, host=comfy_host) if needs_source else None
    if wd14:
        ok, reason = wd14_status(host=comfy_host)
        if not ok:
            raise RuntimeError(f"WD14 tag 补全已开启但不可用：{reason}。拒绝静默降级出图。")
        attach_wd14(wf, source_ref, model=wd14_model, threshold=wd14_threshold,
                    exclude_tags=wd14_exclude_form(prompt))
    if denoise < 1.0:
        wf.setdefault("11", {"class_type": "LoadImage", "inputs": {"image": source_ref}})
        attach_img2img(wf)
    return wf


def drive(prompt: str, seed: int, width: int, height: int, model: str,
          steps: int, cfg: float = 1.0, sampler: str = "er_sde",
          scheduler: str = "simple", denoise: float = 1.0,
          out_dir: str = DEFAULT_OUT, negative: str = DEFAULT_NEGATIVE,
          source_image: str | None = None, wd14: bool = False,
          wd14_model: str = WD14_DEFAULT_MODEL,
          wd14_threshold: float = 0.35) -> dict:
    wf = build_workflow(prompt, seed, width, height, model, steps, cfg=cfg,
                        sampler=sampler, scheduler=scheduler, denoise=denoise,
                        negative=negative, source_image=source_image, wd14=wd14,
                        wd14_model=wd14_model, wd14_threshold=wd14_threshold)
    pid = _req("/prompt", {"prompt": wf})["prompt_id"]
    print("enqueued:", pid)
    for i in range(600):
        time.sleep(1)
        h = _req(f"/history/{pid}").get(pid)
        if not h:
            continue
        st = h.get("status", {})
        if st.get("completed"):
            outputs = h["outputs"]
            files = [img for o in outputs.values() for img in o.get("images", [])]
            print(f"COMPLETED in {i+1}s, {len(files)} image(s)")
            os.makedirs(out_dir, exist_ok=True)
            saved = []
            for f in files:
                url = HOST + "/view?" + urllib.parse.urlencode(
                    {"filename": f["filename"], "subfolder": f.get("subfolder", ""),
                     "type": f.get("type", "output")})
                img = _OPENER.open(url, timeout=60).read()
                sp = os.path.join(out_dir, f["filename"])
                with open(sp, "wb") as fh:
                    fh.write(img)
                saved.append(sp)
            for s in saved:
                print("saved:", s)
            tags = outputs.get("12", {}).get("tags") or []
            return {"images": saved, "wd14_tags": tags[0] if tags else ""}
        if st.get("status_str") == "error":
            print("ERROR:", json.dumps(st, ensure_ascii=False)[:800])
            return {"images": [], "wd14_tags": ""}
    print("TIMEOUT")
    return {"images": [], "wd14_tags": ""}


def build_parser():
    """独立出来供契约测试使用：GUI 拼的 argv 必须能被本解析器接受。

    GUI 与本脚本靠一串命令行字符串耦合，改了这边的参数名而那边没跟，
    表现是「点了没反应」——GUI 侧的假进程测试永远发现不了。
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("--post-id", type=int)
    ap.add_argument("--json")
    ap.add_argument("--tags")
    ap.add_argument("--base", default="safebooru", choices=["safebooru", "danbooru"])
    ap.add_argument("--quality-prefix", default=None,
                    help="覆盖预设的正向前缀(默认取预设值)")
    ap.add_argument("--prompt", default=None,
                    help="直接下发成品正向 prompt，逐字使用，跳过 tag 组装(GUI 编辑器提交用)")
    ap.add_argument("--negative", default=None,
                    help="覆盖预设的负向 prompt")
    ap.add_argument("--include-meta", action="store_true", help="Meta 标签也进 body(默认只 General)")
    ap.add_argument("--no-drive", action="store_true", help="只生成 prompt 不出图")
    ap.add_argument("--preset", choices=list(ANIMA_PRESETS),
                    help="主流预设 turbo/base/aesthetic(覆盖 model/steps/cfg/sampler/scheduler/denoise)")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--width", type=int, default=896)
    ap.add_argument("--height", type=int, default=1152)
    ap.add_argument("--model", default=None,
                    choices=[p["model"] for p in ANIMA_PRESETS.values()])
    ap.add_argument("--steps", type=int, default=None)
    ap.add_argument("--cfg", type=float, default=None)
    ap.add_argument("--sampler", default=None)
    ap.add_argument("--scheduler", default=None)
    ap.add_argument("--denoise", type=float, default=None)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--source-image", default=None,
                    help="源图本地路径。一张图两种用途：--wd14 读 tag、--denoise<1 作重绘起始 latent")
    ap.add_argument("--wd14", action="store_true", help="开启 WD14 图内 tag 补全（需 --source-image）")
    ap.add_argument("--wd14-model", default=WD14_DEFAULT_MODEL)
    ap.add_argument("--wd14-threshold", type=float, default=0.35)
    ap.add_argument("--emit-json", default=None,
                    help="把结果(出图路径 + WD14 tags)写入该 JSON，供 GUI 回读")
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.preset:
        p = ANIMA_PRESETS[args.preset]
        args.model = args.model or p["model"]
        args.steps = args.steps or p["steps"]
        args.cfg = p["cfg"] if args.cfg is None else args.cfg
        args.sampler = args.sampler or p["sampler"]
        args.scheduler = args.scheduler or p["scheduler"]
        args.denoise = p["denoise"] if args.denoise is None else args.denoise
        quality_prefix = p["quality_prefix"] if args.quality_prefix is None else args.quality_prefix
        negative = p["negative"]
        print(f"preset[{args.preset}] {p['label']}: {p['desc']}")
    else:  # 无预设的旧用法: 显式参数或 turbo 默认
        args.model = args.model or ANIMA_PRESETS[DEFAULT_PRESET]["model"]
        args.steps = args.steps or 10
        args.cfg = 1.0 if args.cfg is None else args.cfg
        args.sampler = args.sampler or "er_sde"
        args.scheduler = args.scheduler or "simple"
        args.denoise = 1.0 if args.denoise is None else args.denoise
        quality_prefix = DEFAULT_QUALITY_PREFIX if args.quality_prefix is None else args.quality_prefix
        negative = DEFAULT_NEGATIVE
    args.seed = 42 if args.seed is None else args.seed

    if args.prompt is not None and not str(args.prompt).strip():
        raise SystemExit("--prompt 不能为空")
    post = load_post(args)
    if args.negative is not None:
        negative = args.negative
    negative = post.get("negative") or negative
    positive, built = resolve_positive(args, post, quality_prefix)
    print("=== ANIMA prompt ===")
    print(positive)
    print("=== negative ===")
    print(negative)
    if built is not None:
        print(f"\nbody({len(built['body'].split(', '))}):", built["body"][:120], "...")
        print("identity:", built["identity"])
    else:
        print("\n(成品 prompt 直传，未走 tag 组装)")

    if args.no_drive:
        return 0
    result = drive(positive, args.seed, args.width, args.height, args.model,
                   args.steps, cfg=args.cfg, sampler=args.sampler, scheduler=args.scheduler,
                   denoise=args.denoise, negative=negative, out_dir=args.out,
                   source_image=args.source_image, wd14=args.wd14,
                   wd14_model=args.wd14_model, wd14_threshold=args.wd14_threshold)
    if result["wd14_tags"]:
        print("=== WD14 tags ===")
        print(result["wd14_tags"])
    if args.emit_json:
        with open(args.emit_json, "w", encoding="utf-8") as fh:
            json.dump({"prompt": positive, **result}, fh, ensure_ascii=False, indent=2)
    return 0 if result["images"] else 2


if __name__ == "__main__":
    sys.exit(main())
