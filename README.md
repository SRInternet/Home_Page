# 个人主页

一个基于 Flask 的现代化个人主页应用，可展示您的 GitHub 个人信息、项目和技术栈，并支持多种部署方式。

<img width="1280" height="700" alt="image" src="https://github.com/user-attachments/assets/7d394bbd-c4ed-4398-a551-104237f90c4e" />


## 🚀 功能特点

- ✨ **美观界面设计**：采用二次元+科技+渐变风格，支持自适应深色/浅色模式切换
- 📱 **完全响应式**：完美适配从手机到桌面的各种屏幕尺寸
- 🎨 **精美动画效果**：平滑的过渡和交互动画，提升用户体验
- 🔧 **快速详细配置**：通过简洁的 JSON 配置文件自定义个人信息和网页设置
- 📊 **GitHub 信息集成**：自动展示头像、名称、仓库数量、Stars 数量
- 📈 **活动数据可视化**：直观展示 GitHub 活动轨迹和趋势
- 📝 **技术栈展示**：自动分析并展示您常用的编程语言和技术
- 🔄 **最近项目展示**：自动获取并展示您最近有更新的 GitHub 项目
- 📜 **个性化介绍**：灵活的个人介绍内容配置方式

## 🛠️ 技术栈

- **后端**：Python 3.6+, Flask
- **前端**：HTML5, Tailwind CSS, JavaScript
- **数据可视化**：Chart.js
- **第三方集成**：GitHub API
- **部署选项**：GitHub Pages, Vercel, Netlify, PythonAnywhere, Heroku, Docker 等

## 📋 前提条件

- Python 3.6 或更高版本
- Git 版本控制系统
- GitHub 账号（可选，用于展示 GitHub 信息）
- 推荐使用虚拟环境进行开发
- Docker（可选，用于容器化部署）

## 🚀 快速开始

### 1. 克隆仓库

```bash
# 克隆仓库到本地
git clone https://github.com/SRInternet/Home_Page.git
cd Home_Page
```

### 2. 安装依赖

```bash
# 使用 pip 安装所需依赖
pip install -r requirements.txt

# 或使用提供的部署脚本
bash deploy.sh install
```

### 3. 配置个人信息

编辑 `config.json` 文件，根据您的需求修改以下配置：

```json
{
  "github_url": "https://github.com/your-username",
  "dark_mode": "auto",
  "name": "Your Name",
  "bio": "Your Bio",
  "introduction_file": "Introduction.md",
  "theme": {
    "primary_color": "#6a11cb",
    "secondary_color": "#2575fc"
  }
}
```

### 4. 本地运行

```bash
# 直接运行
python app.py

# 或使用部署脚本
bash deploy.sh run
```

然后访问 http://localhost:5000 查看效果。

## 🎨 自定义个人介绍

有三种灵活的方式可以自定义个人介绍内容：

1. **GitHub README（推荐）**：在您的 GitHub 账号下创建一个与用户名同名的仓库，并在其中添加 README.md 文件
2. **本地 Introduction.md**：直接修改项目根目录下的 Introduction.md 文件
3. **配置文件指定**：在 config.json 中修改 `introduction_file` 字段，指向您自定义的 Markdown 文件

## 🚢 部署指南

### 方法一：使用 Vercel/Netlify 部署

1. 将代码推送到 GitHub 仓库
2. 注册 Vercel 或 Netlify 账号
3. 连接您的 GitHub 仓库
4. 按照平台指引完成部署配置

### 方法二：生成静态文件部署

```bash
# 直接运行构建脚本生成静态文件（HTML将直接生成在项目根目录）
python build_static.py

# 添加生成的文件并提交

git add index.html background.jpg

git commit -m 'Update static website'

# 将文件推送到 GitHub Pages 的 gh-pages 分支
git push origin master:gh-pages
```

### 方法三：使用支持 Flask 的平台

您也可以选择支持 Flask 的平台进行部署：
- PythonAnywhere
- Heroku
- Railway
- DigitalOcean App Platform

### 方法四：使用 Docker 部署

#### 使用 Docker CLI

1. **构建 Docker 镜像**：
   ```bash
   docker build -t home-page .
   ```

2. **运行容器**：
   ```bash
   docker run -p 5000:5000 home-page
   ```

#### 使用 Docker Compose

1. **启动服务**：
   ```bash
   docker-compose up
   ```

2. **后台运行**：
   ```bash
   docker-compose up -d
   ```

3. **查看日志**：
   ```bash
   docker-compose logs
   ```

4. **停止服务**：
   ```bash
   docker-compose down
   ```

访问 http://localhost:5000 查看应用。

## 💻 命令行工具

项目提供了便捷的命令行工具 `deploy.sh` 来管理项目：

```bash
# 安装项目依赖
bash deploy.sh install

# 运行开发服务器
bash deploy.sh run

# 构建静态文件
# 注意：build_static.py 已更新，静态HTML直接生成在项目根目录
bash deploy.sh build

# 查看部署指南
bash deploy.sh deploy

# 查看帮助信息
bash deploy.sh help
```

## 🤖 自动编译配置

项目支持配置 GitHub Actions 自动编译功能，提供两种自动构建方式：

### 静态文件自动构建
- 每天 UTC 时间 0 点（北京时间 8 点）自动运行编译脚本
- 自动将生成的静态文件提交到当前分支
- 支持在 GitHub 仓库的 Actions 页面手动触发运行

GitHub Actions 配置文件可参考[个人项目主页](https://github.com/SRInternet/SRInternet.github.io/blob/master/.github/workflows/build-deploy.yml)

### Docker 镜像自动构建和推送
当您推送 Git 标签（tag）时，自动触发 Docker 镜像构建并推送到 GitHub Container Registry (GHCR)。

**功能特点：**
- 自动构建 Docker 镜像
- 推送镜像到 GHCR，使用小写用户名确保兼容性
- 镜像标签与 Git 标签一致
- 同时推送 `latest` 标签

**使用方法：**
1. 创建并推送一个 Git 标签：
   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```
2. 工作流自动执行，构建镜像并推送到 `ghcr.io/<您的用户名>/<仓库名>:<标签>`
   - 例如：如果您的仓库名为 `Home_Page`，标签为 `v1.0.0`，镜像将推送到 `ghcr.io/<您的用户名>/home_page:v1.0.0`

**镜像名称格式：** `ghcr.io/<owner>/<repository-name>:<tag>`

工作流配置文件位于 `.github/workflows/docker-build-push.yml`

## ⚙️ 配置详解

### config.json 字段说明

- `github_url`：您的 GitHub 个人主页 URL，用于获取您的公开信息
- `dark_mode`：深色模式设置（可选值：`auto` 跟随系统、`dark` 强制深色、`light` 强制浅色）
- `name`：您的名称（GitHub API 调用失败时的备选显示）
- `bio`：您的简介（GitHub API 调用失败时的备选显示）
- `introduction_file`：本地介绍文件路径
- `theme`：主题配色方案配置
  - `primary_color`：主色调（用于按钮、重点内容等）
  - `secondary_color`：辅助色调（用于渐变、次要强调等）

## 🔧 开发指南

- **修改页面样式**：编辑 `templates/index.html` 文件中的 Tailwind CSS 配置
- **添加新功能**：修改 `app.py` 文件中的 Flask 路由和逻辑
- **调整前端交互**：编辑 `templates/index.html` 中的 JavaScript 代码或 `index.js` 文件
- **自定义主题**：在 `config.json` 中调整主题颜色配置

## 📝 License

[MIT](LICENSE)
