# MediaSpider - PyAppify 打包指南

## 当前配置

已创建 `pyappify.yml` 配置文件，包含：
- 应用名称：MediaSpider
- 主脚本：main.py
- Python 版本：3.10
- 依赖：requirements.txt
- 图标：icons/icon.ico

## 打包步骤

### 步骤 1: 获取 pyappify.exe 启动器

从 GitHub Releases 下载：
```
https://github.com/ok-oldking/pyappify/releases
```

下载后放到项目根目录。

### 步骤 2: 修改配置文件

编辑 `pyappify.yml`，将 `git_url` 替换为你的仓库地址：
```yaml
git_url: "https://github.com/你的用户名/MediaSpider.git"
```

### 步骤 3: 测试启动器

双击 `pyappify.exe`，它会自动：
1. 克隆你的代码仓库
2. 下载 Python 3.10 环境
3. 安装依赖
4. 启动 MediaSpider

### 步骤 4: 完整打包（可选）

使用 GitHub Actions 生成离线包：

在 `.github/workflows/build.yml` 中添加：
```yaml
name: Build PyAppify Package
on: [push, workflow_dispatch]
jobs:
  build:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: ok-oldking/pyappify-action@main
```

## 注意事项

1. **仓库必须公开**或有正确的 SSH 密钥配置
2. **必须使用 Git tags** 进行版本管理（推荐使用语义化版本如 v1.0.0）
3. **main.py 必须能独立运行**
4. 首次启动需要下载 Python 和依赖，约 100-200MB

## 打包后的文件结构

```
MediaSpider/
├── pyappify.exe       # 启动器（可重命名为 MediaSpider.exe）
├── pyappify.yml       # 配置文件
├── icons/             # 图标目录
├── data/              # 自动生成的 Python 环境
├── cache/             # pip 缓存
└── logs/              # 日志文件
```
