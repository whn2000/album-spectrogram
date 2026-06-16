# Album Spectrogram Generator

Album Spectrogram Generator 是一款专为音乐爱好者和 PT 站发种者设计的工具，可自动批量生成无损音乐（FLAC/WAV/APE 等）的频谱图和频响分析图，并支持直接对接图床接口，极大地简化了发帖附带频谱图的繁琐流程。

## 🌟 核心特性
- 🎵 **自动生成频谱**：自动读取音乐文件并生成高质量的频谱图。
- 🖼️ **图床集成**：一键上传生成的频谱图至图床（如 IMGBB 等），直接输出 BBCode 代码，完美适配各类 PT 论坛。
- 🐳 **开箱即用**：提供 Docker 和 Docker Compose 部署方式，轻松部署在 NAS 或个人服务器上。
- ⚡ **高效批量处理**：支持整轨专辑或多文件的快速批量生成。

## 🚀 部署指南

我们推荐使用 Docker Compose 进行部署，这是最简单和最干净的方式。

### 1. 准备配置文件

克隆本仓库或下载 `docker-compose.yml` 与 `.env.example`，并将 `.env.example` 重命名为 `.env`。

```bash
cp .env.example .env
```

在 `.env` 文件中填入您的图床 API Key（例如 IMGBB 的 API 密钥）。

### 2. 修改目录映射

编辑 `docker-compose.yml` 文件，将您的本地音乐目录映射到容器内的 `/music` 目录：

```yaml
    volumes:
      # 将您 NAS 或服务器上的实际音乐路径映射进容器
      - /您的/本地/音乐文件夹:/music:ro
      # 输出目录保存位置
      - spectrogram-output:/app/output
```

### 3. 一键启动

在包含 `docker-compose.yml` 的目录下执行：

```bash
docker compose up -d
```

启动后，访问 `http://您的IP地址:5000` 即可使用。

## 💡 使用方法

1. 在浏览器中打开 Web 界面。
2. 从映射的目录中选择需要分析的音乐文件或整个文件夹。
3. 点击生成，等待处理完成。
4. 一键复制生成的 BBCode 链接，直接粘贴到 PT 站的发布页面中即可！

## 🤝 贡献与反馈

欢迎提交 Pull Request 或者创建 Issue 来帮助完善这个项目。

## 📄 开源协议

本项目采用 [MIT License](LICENSE) 开源协议。
