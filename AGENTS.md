# AGENTS.md

This file provides guidance to agents when working with code in this repository.

Flask 单页应用，渲染 `templates/index.html`，数据来自 GitHub API。无测试、无 lint 配置。

版本号维护在根目录 `VERSION` 文件（当前 `2.0`），README 顶部展示同一版本。

## 命令

- 开发服务器：`python app.py`（Flask debug 模式，`0.0.0.0:5000`，reload 会重跑 `before_first_request`）
- 静态构建：`python build_static.py`（生成根目录 `index.html`，供 GitHub Pages；该产物被 `.gitignore` 忽略）
- Docker：`docker build -t home-page .` 后 `docker run -p 5000:5000 home-page`
- 监听地址与端口由环境变量 `HOST`/`PORT` 决定，默认 `0.0.0.0:5000`（容器内可达）；Dockerfile 已预设这两个变量并安装 `tzdata`（`ENV TZ` 依赖它）。
- `.dockerignore` 排除 `venv/`、`.tmp/`、`.roo/`、`github_token.txt`、`config.json`；容器首次启动时 `load_config()` 会从 `default/default_config.json` 重建 `config.json` 与背景图。

## 非显而易见的约定

- Markdown 转换统一走 `render_markdown()`，内含 `InlineTagJoinPostprocessor`：把上下行相邻的行内级标签（img/span/a 等）合并为同行并以空格分隔，`<pre>`/`<script>` 等逐字块会被抠出占位、还原，代码块内部换行不受影响。新增转换调用禁止直接调 `markdown.markdown()`。
- 活动数据统计口径：主数据源为 GraphQL `contributionsCollection`（与 GitHub 个人主页贡献日历同口径），窗口取「11 个月前 1 号」至当前时刻（跨度必须 < 1 年，否则 GitHub 返回 VALIDATION 错误）；不可用（无 token / 查询失败 / 全零）时回退到 Events API + 仓库提交历史的 REST 统计。按自然月分桶，输出顺序为「最旧月 → 最新月」，不做平滑与缩放。
- `get_github_activity_data()` 返回 `(activity_data, activity_labels)` 二元组，`activity_labels` 由 `_activity_month_labels()` 按当前日期生成，末位恒为当前月；新增 `github_info` 键时需同步 `index()` 的 render 参数与 `generate_static_html()` 的 `render_args`。
- 主题切换按钮图标显隐由 CSS 类 `.theme-icon-light` / `.dark .theme-icon-dark` 控制，不依赖 Tailwind 的 `dark:hidden` 变体；深浅色类名仍挂在 `documentElement`。
- `app.py` 用 `@app.before_first_request` 加载全局 `config`：读 `config.json`，缺失/损坏/顶层非对象时从 `default/default_config.json` 复制，两者都不可用则回落 `BUILTIN_CONFIG`。该装饰器在新版 Flask 已废弃，本地起服务前需先有一次请求触发加载。
- 入口顺序敏感：`build_static.py` 用 `importlib` 动态加载 `app.py` 并调用 `app.test_client()` 拿 `/`，不走 `generate_static_html()`（该函数用独立 Jinja 环境、无 GitHub 数据，仅作历史保留）。
- 所有 GitHub 请求必须经 `make_github_request()`：全局禁用 SSL 校验、5s 超时、异常返回 `MockResponse(status_code=500)`，禁止裸用 `requests.get`。
- GitHub token 优先级：`app.root_path/github_token.txt`（在 `.gitignore` 中）> `config.json` 的 `github_token`。
- 令牌只注入 `TOKEN_HOSTS`（`api.github.com`）内的 URL，避免外发到 `raw.githubusercontent.com` 等 CDN 域名。
- 令牌来源优先级：环境变量 `GITHUB_TOKEN` > `github_token.txt` > `config.json` 的 `github_token`。前两者都在 `.gitignore` 中，CI 检出后不存在，因此 workflow 必须显式传 `secrets.GITHUB_TOKEN`，否则 GraphQL 贡献日历直接放弃、REST 回退在匿名下命中 403，最终返回全零。
- 取不到活动/star 数据时返回全零而非编造数值：假数据会让采集故障被静默掩盖（本地有 token 正常、CI 无 token 显示一组看似合理的曲线）。
- `config.json` 缺失、损坏或顶层非对象时，依次回退 `default/default_config.json` → `BUILTIN_CONFIG`，并按 `BUILTIN_CONFIG` 补齐 `theme`/`background`/`contact` 缺失键；模块级 `config = {}` 保证 `import app` 不会 NameError。
- 模板内 `tech_stack`/`activity_data` 的颜色与数值由 Python 端预计算（`analyze_tech_stack` 带 1 小时模块级缓存），前端只消费；图表数据用 `{{ github_info.activity_data | tojson }}` 注入。
- `Introduction.md` 的渲染链路是：GitHub 同名仓库 README（main→master）失败时回退本地 `config['introduction_file']` 指定文件，Markdown 用固定扩展集转换。
- 新增 `templates/index.html` 变量时同步 `index()` 的 render 参数与 `generate_static_html()` 的 `render_args`。
- 路由 `/<path:filename>` 只放行 `.jpg/.jpeg/.png/.gif/.svg/.css/.js`，新增静态类型需改 `allowed_extensions`。
- Tailwind 走 CDN 并在模板内联 `tailwind.config`，主题色（`config.theme` 含 `dark_*` 字段）通过 Jinja 注入；`dark_mode: "class"`，深浅色类名挂在 `documentElement`。
- 贡献图表配色不硬编码：模板在 `:root` 与 `.dark` 下注入 `--chart-*` CSS 变量，JS 用 `getComputedStyle` 读取，并通过 `MutationObserver` 监听 `documentElement` 的 class 变化实时重绘。改图表配色只改这两处 CSS 变量。
- 图表由 `chartSpecs` 数组驱动（canvasId / type / labels / data / label / seriesKey），新增图表只需往数组里加一项，`redrawCharts()` 会自动覆盖；折线图用 `--chart-line`/`--chart-fill`，柱状图用 `--chart-bar`/`--chart-bar-fill`。
- Star 历史口径：GitHub 不向个人令牌开放 stargazer 时间戳（REST `star+json` 与 GraphQL `starredAt` 均返回 `Resource not accessible by personal access token`），因此 `get_github_star_history()` 用仓库 `created_at` 作为 star 累积起点，输出「截至每月底的累计 star 总量」，曲线单调不减；复用 `get_github_user_info()` 已拉取的 repos，无额外 API 调用。
- `get_github_star_history()` 与 `get_github_activity_data()` 一样返回 `(data, labels)` 二元组；`_month_index()` 索引 0 为当前月、11 为 11 个月前，累加方向是「当前月 → 创建月」（即 `range(last_index + 1)`），改分桶逻辑时注意索引语义与最终输出（已反转为最旧月→最新月）的差异。
- 组织列表走 `get_github_organizations()`：`GET /users/{u}/orgs?per_page=100`，按 login 小写去重并字母序排序，空列表返回 `[]`（模板渲染占位文案，不留空白板块）。
- 组织板块的数据边界：该接口只返回用户的**公开**组织成员身份，成员身份设为私有时稳定返回 `[]`（`totalCount: 0`），这不是代码缺陷。占位文案需说明「或未公开身份」并附 GitHub 公开身份设置帮助链接；不要改用解析个人主页 HTML 或 Company 字段的方案（Company 是用户自定义文本，不可验证）。
- 所有 `glass-panel` 板块都必须带 `card-hover`，否则 `.card-hover:hover { transform: translateY(-5px) }` 不生效。
- **`.card-hover:hover` / `.repo-item:hover` 必须包在 `@media (hover: hover) and (pointer: fine)` 内**：触屏的点击会在移动端浏览器留下常驻 `:hover`，导致板块无故上浮、点空白处先回落再上浮。桌面端鼠标设备不受影响。
- **不要在 `@layer utilities` 内的 `.glass-panel` 上声明 `transform`**：它与同层 `.card-hover:hover` 特异性相同，凭源顺序会压过 hover 的 `translateY(-5px)`，导致悬停上移失效（症状：仅入场动画播放期间能动）。极简模式的位移改由未分层 `<style>` 中的 `.glass-panel.section-hidden` 承载。
- **`backdrop-filter` 不能进 `transition`**：浏览器无法平滑插值该属性，过渡起始会直接丢弃 blur，板块先变纯透明再恢复。极简模式只过渡 `opacity` 与 `transform`，blur 通过类切换瞬时生效。
- 极简模式的选择器必须是 `.glass-panel`（板块本体）。选外层列容器（如 `div.lg:col-span-1`）套不到 `.glass-panel.section-hidden` 规则，退场动画会完全失效。
- 入场动画不做 resize 重播：窗口尺寸变化不需要板块重新淡入，且 `playEntrance` 式的强制重排会在动画期间抢占 `transform`，让悬停上移间歇失效。
- 入场动画会占用 `transform` 从而压制 hover 上移：`fadeIn` 关键帧写了 `transform`，而 `.card-hover:hover` 定义在 `<style type="text/tailwindcss">` 的 `@layer utilities` 内，优先级低于未分层的 `.animate-fade-in`。因此动画播完后要显式释放 `animation`：JS 在 `animationend`（且 `animationName` 属于 `['fadeIn', 'slideIn']`，并校验 `event.target === currentTarget` 以忽略子元素与伪元素冒泡）时补 `entrance-done` 类，由未分层 `<style>` 中的 `.entrance-done { animation: none }` 关掉动画；另有 `ENTRANCE_FALLBACK_MS`（1.6s）兜底，防止 `animationend` 丢失导致 `transform` 永久被占。
- **不要在 `animationend` 里 `classList.remove('animate-fade-in')`**：活动概览 / Star 增长 / 所属组织 / 最近项目带静态 `animate-fade-in`，页面加载即播放；类被移除后，IntersectionObserver 仍观察着这些板块，用户首次滚动时 `isIntersecting` 变真又把类加回去，入场动画会整体重播。正确做法是只补 `entrance-done`、不动静态类，且 IntersectionObserver 只观察没有静态 `animate-fade-in` 的板块（`entrancePlayed` WeakSet 去重）。
- `index.js` 与模板内的主题逻辑是两份等价实现，改主题行为需同时改两处；`index.js` 仅服务于静态部署场景。
- `.readme-content` 的 `slideIn` 是静态类（模板上常驻），靠 `animation-fill-mode: none` 让动画结束不保留关键帧值，`entrance-done` 再补一道 `animation: none` 双保险。`animation-fill-mode: none` 声明不能删。
- 新增 `github_info` 键（`star_data`/`star_labels`/`organizations`）需同步 `index()` 的 render 参数与 `generate_static_html()` 的 `render_args`。
- `index.js` 仅服务于静态部署场景（主题持久化），模板内另有一套等价逻辑，改主题行为需同时改两处。
- 深浅色切换的涟漪用 View Transitions 实现（`document.startViewTransition`）：伪元素树里 `::view-transition-new(root)` 天然排在 `::view-transition-old(root)` 之上，因此旧快照留底 `animation: none`、新快照置顶 `clip-path: circle()` 自点击点展开即得扩散效果。不用 `@property` / 伪元素叠加 / Canvas：那些方案只能覆盖背景层，正文、玻璃面板与导航栏的颜色仍会瞬间切换。不支持该 API 的浏览器（Firefox）直接切换，退回 `body` 的 `background-color` 过渡。
- 涟漪原点由 JS 写入 `--ripple-x/y`（`event.clientX || 按钮中心`，键盘触发时 clientX/Y 为 0），未注入时 CSS 侧回落 `50%`。`themeRippleRunning` 锁防连点叠加多个过渡；`startViewTransition` 包在 `try/catch 内，异常时解锁并直改`；解锁挂 `transition.finished.then(unlock, unlock)`（`skipTransition` 也会 settle），`transition.ready.catch()` 吞掉可能的 reject。
- 涟漪只由主题切换按钮发起；系统主题 `change` 监听保持直改不起涟漪。`prefers-reduced-motion: reduce`、`document.hidden`、不支持 VT 三者任一命中即跳过；CSS 侧另有 `@media (prefers-reduced-motion: reduce)` 关掉两个过渡伪元素的 `animation` 作兜底。
- 涟漪关键帧必须叫 `theme-ripple-expand`：入场动画的 `animationend` 白名单只认 `['fadeIn', 'slideIn']`，且过渡伪元素树不向文档冒泡 `animationend`，`entrance-done` 逻辑无需改动。
