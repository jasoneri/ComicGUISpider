## 🐞 Fix

### mac相关

✅ ✨兼容`ARM64`架构，即苹果m系芯片，可通过以下命令查看（如m系仍无法打开，请进群反馈）

```bash
python -c "import platform; print(platform.machine())"
```

### wnacg专栏

+ 发布页相关：已恢复墙内访问，无需手设`wnacg_domain.txt`（2025.03.25）
+ 修复图片下载问题，先前错误表现为进度条一动不动，或log报错403
+ 修复预览图片加载不了的问题
