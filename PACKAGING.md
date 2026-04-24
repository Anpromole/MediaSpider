# MediaSpider - PyAppify 打包指南

## 方案一：使用 GitHub Actions 自动打包（推荐）

### 步骤 1: 将项目推送到 GitHub

```bash
# 初始化 git（如果还没有）
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/你的用户名/MediaSpider.git
git push -u origin main
```

### 步骤 2: 创建版本标签

```bash
git tag v1.0.0
git push origin v1.0.0
```

推送标签后，GitHub Actions 会自动打包并创建 Release。

### 步骤 3: 修改 pyappify.yml

编辑 `pyappify.yml`，将 `git_url` 替换为你的仓库地址：
```yaml
git_url: "https://github.com/你的用户名/MediaSpider.git"
```

---

## 方案二：本地使用 pyappify 启动器测试

如果你已有 `pyappify.exe`：

1. 将 `pyappify.exe` 放到项目根目录
2. 修改 `pyappify.yml` 中的 `git_url`
3. 双击运行 `pyappify.exe`

---

## 打包后的文件结构

```
MediaSpider/
├── pyappify.exe       # 启动器
├── pyappify.yml       # 配置文件
├── icons/             # 应用图标
├── main.py            # 主程序
├── config.py          # 配置
├── threads.py         # 线程模块
├── widgets.py         # UI 组件
├── requirements.txt   # 依赖
└── spider/            # 爬虫模块
```

---

## 注意事项

1. **仓库必须是公开的**，或者配置 SSH 密钥
2. **必须使用 Git tags** 进行版本管理
3. **main.py 必须能独立运行**
4. 首次启动需要下载 Python 和依赖（约 100-200MB）
