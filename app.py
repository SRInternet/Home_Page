import os
import re
import sys
import json
import time
import shutil
import requests
import markdown
import jinja2
import yaml
from datetime import datetime
from flask import Flask, render_template, jsonify, send_from_directory, abort
from markdown.postprocessors import Postprocessor

app = Flask(__name__)

# 内置兜底配置：config.json 缺失、损坏或 default 目录都不可用时使用
BUILTIN_CONFIG = {
    "github_url": "https://github.com/example",
    "dark_mode": "auto",
    "name": "Example User",
    "bio": "Python Developer",
    "introduction_file": "Introduction.md",
    "github_token": "",
    "theme": {
        "primary_color": "#6a11cb",
        "secondary_color": "#2575fc",
        "dark_primary_color": "#a855f7",
        "dark_secondary_color": "#60a5fa"
    },
    "background": {
        "image": "background.png",
        "blur": 8,
        "overlay_opacity": 0.6,
        "overlay_color": "#121212",
        "dark_overlay_color": "#121212"
    },
    "contact": {}
}

config = {}

@app.before_first_request
def load_config():
    global config
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
        if not isinstance(config, dict):
            raise ValueError("config.json 顶层不是JSON对象")
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as e:
        print(f"config.json 不可用（{type(e).__name__}），尝试从 default 目录恢复")
        # 如果config.json不存在，尝试从default文件夹复制
        default_config_path = os.path.join('default', 'default_config.json')
        if os.path.exists(default_config_path):
            print(f"从{default_config_path}复制默认配置")
            shutil.copy2(default_config_path, 'config.json')
            # 读取复制过来的配置
            with open('config.json', 'r', encoding='utf-8') as f:
                config = json.load(f)

            # 同时检查background.jpg是否存在，如果不存在也从default文件夹复制
            if 'background' in config and 'image' in config['background']:
                background_image = config['background']['image']
                if not os.path.exists(background_image) and os.path.exists(os.path.join('default', background_image)):
                    print(f"{background_image}不存在，从default文件夹复制")
                    shutil.copy2(os.path.join('default', background_image), background_image)
        else:
            # 如果default_config.json也不存在，使用内置默认配置
            print("default/default_config.json不存在，使用内置默认配置")
            config = dict(BUILTIN_CONFIG)
            # 保存默认配置
            with open('config.json', 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

    # 补齐缺失的顶层键，避免模板渲染时 KeyError
    for key, value in BUILTIN_CONFIG.items():
        config.setdefault(key, value)
    for key in ('primary_color', 'secondary_color', 'dark_primary_color', 'dark_secondary_color'):
        config.setdefault('theme', {}).setdefault(key, BUILTIN_CONFIG['theme'][key])
    for key in ('blur', 'overlay_opacity', 'overlay_color', 'dark_overlay_color', 'image'):
        config.setdefault('background', {}).setdefault(key, BUILTIN_CONFIG['background'][key])
    config.setdefault('contact', {})

# 读取 GitHub 令牌
def get_github_token():
    token_file = os.path.join(app.root_path, 'github_token.txt')
    if os.path.exists(token_file):
        try:
            with open(token_file, 'r', encoding='utf-8') as f:
                return f.read().strip().replace('"', '').replace("'", '')
        except Exception as e:
            print(f"读取GitHub令牌时出错: {e}")
    return config.get('github_token', '')

# 只对这些域名注入令牌，避免令牌外发到其他主机
TOKEN_HOSTS = ('api.github.com',)

# 创建通用的GitHub API请求函数
def make_github_request(url, timeout=5):
    try:
        # 配置requests不验证SSL证书（解决本地环境中的证书验证问题）
        import ssl
        ssl._create_default_https_context = ssl._create_unverified_context
        
        # 准备请求头
        headers = {'Accept': 'application/vnd.github.v3+json'}
        github_token = get_github_token()
        
        # 如果配置了GitHub令牌，添加到请求头
        if github_token and any(host in url for host in TOKEN_HOSTS):
            headers['Authorization'] = f'token {github_token}'
            print(f"使用GitHub令牌进行认证")
        else:
            print("未使用GitHub令牌，使用匿名访问")
        
        # 发送请求
        response = requests.get(url, headers=headers, timeout=timeout, verify=False)
        print(f"GitHub API请求: {url}, 状态码: {response.status_code}")
        
        # 检查是否达到速率限制
        if response.status_code == 403 and 'rate limit' in response.text.lower():
            print("GitHub API速率限制已达，建议配置GitHub令牌")
        
        return response
    except Exception as e:
        print(f"GitHub API请求异常: {e}")
        # 请求失败时返回模拟响应，调用方按状态码走降级逻辑
        class MockResponse:
            def __init__(self):
                self.status_code = 500
                self.text = "模拟错误响应"

            def json(self):
                return []
        return MockResponse()

# Markdown 渲染配置
MARKDOWN_EXTENSIONS = ['extra', 'codehilite', 'toc', 'tables', 'md_in_html']
MARKDOWN_EXTENSION_CONFIGS = {
    'codehilite': {
        'css_class': 'highlight',
        'linenums': False
    }
}

# 参与合并的行内级标签，出现这些标签的行才会与相邻行拼接
_INLINE_TAGS = {
    'img', 'span', 'a', 'b', 'i', 'em', 'strong', 'small', 'sub', 'sup',
    'br', 'label', 'abbr', 'mark', 'kbd', 'samp', 'var', 'u', 's', 'q', 'cite',
    'time', 'svg', 'picture', 'source', 'iframe',
}

# 这些标签内部的内容禁止参与合并
_VERBATIM_TAGS = {'pre', 'code', 'script', 'style', 'textarea'}

class InlineTagJoinPostprocessor(Postprocessor):
    """把渲染结果中相邻的行内级标签合并到同一行，以空格分隔。"""

    _TAG_RE = re.compile(r'<\s*(/?)\s*([a-zA-Z][a-zA-Z0-9-]*)')
    _VERBATIM_BLOCK_RE = re.compile(
        r'<(pre|script|style|textarea)\b.*?</\1\s*>',
        re.IGNORECASE | re.DOTALL
    )

    def _has_inline_tag(self, line):
        return any(
            match.group(2).lower() in _INLINE_TAGS
            for match in self._TAG_RE.finditer(line)
        )

    def run(self, text):
        # 抠出 <pre>/<script> 等逐字块，占位后再合并，避免破坏代码块内部换行
        verbatim_blocks = []

        def _stash(match):
            verbatim_blocks.append(match.group(0))
            return f'\x00VERBATIM{len(verbatim_blocks) - 1}\x00'

        text = self._VERBATIM_BLOCK_RE.sub(_stash, text)

        lines = text.split('\n')
        result = []
        for line in lines:
            stripped = line.strip()
            if (stripped and result and result[-1].strip()
                    and self._has_inline_tag(result[-1]) and self._has_inline_tag(stripped)):
                result[-1] = f'{result[-1].rstrip()} {stripped}'
            else:
                result.append(line)
        text = '\n'.join(result)

        # 还原逐字块，还原时保持独立成行
        for index, block in enumerate(verbatim_blocks):
            text = text.replace(f'\x00VERBATIM{index}\x00', block)
        return text

class InlineTagJoinExtension(markdown.Extension):
    def extendMarkdown(self, md):
        md.postprocessors.register(
            InlineTagJoinPostprocessor(md),
            'inline_tag_join',
            # 收尾阶段执行，确保拿到的是最终 HTML 行结构
            25
        )

def render_markdown(md_text):
    """统一的 Markdown 转 HTML 入口，新增转换调用必须走此函数。"""
    return markdown.markdown(
        md_text,
        extensions=MARKDOWN_EXTENSIONS + [InlineTagJoinExtension()],
        extension_configs=MARKDOWN_EXTENSION_CONFIGS,
    )

# 从 GitHub API 获取用户信息
def get_github_user_info():
    print("开始获取GitHub用户信息")
    github_url = config.get('github_url', 'https://github.com/example')
    username = github_url.rstrip('/').split('/')[-1]
    print(f"配置的GitHub URL: {github_url}")
    print(f"提取的用户名: {username}")

    try:
        print(f"准备请求GitHub API: https://api.github.com/users/{username}")
        
        # 获取用户信息
        user_response = make_github_request(f'https://api.github.com/users/{username}')
        print(f"GitHub API响应状态码: {user_response.status_code}")

        if user_response.status_code == 200:
            user_data = user_response.json()
            print(f"成功获取用户数据: {user_data.get('name')}, {user_data.get('login')}")

            # 获取用户的仓库信息
            repos_response = make_github_request(f'https://api.github.com/users/{username}/repos?sort=pushed&per_page=100')
            if repos_response.status_code == 200:
                repos = repos_response.json()
                if not isinstance(repos, list):
                    repos = []

                # 获取总仓库数和总 stars 数
                total_repos = len(repos)
                total_stars = sum(repo.get('stargazers_count') or 0 for repo in repos)

                # 获取同名仓库的 README
                readme_content = get_readme_content(username)

                # 获取最近有推送的 5 个仓库
                recent_repos = sorted(
                    repos,
                    key=lambda x: x.get('pushed_at') or '',
                    reverse=True
                )[:5]

                # 获取用户的活动数据（最近12个自然月的贡献统计）
                activity_data, activity_labels = get_github_activity_data(username, repos)

                # 获取 Star 增长历史，复用已获取的repos，无额外API调用
                star_data, star_labels = get_github_star_history(username, repos)

                # 获取用户加入的组织列表
                organizations = get_github_organizations(username)

                # 分析用户的技术栈
                tech_stack = analyze_tech_stack(repos)

                return {
                    "avatar_url": user_data.get('avatar_url'),
                    "name": user_data.get('name') or username,
                    "bio": config.get('bio', 'Python Developer'),  # 使用配置文件中的bio
                    "total_repos": total_repos,
                    "total_stars": total_stars,
                    "readme_content": readme_content,
                    "recent_repos": recent_repos,
                    "activity_data": activity_data,
                    "activity_labels": activity_labels,
                    "star_data": star_data,
                    "star_labels": star_labels,
                    "organizations": organizations,
                    "tech_stack": tech_stack
                }
    except Exception as e:
        print(f"GitHub API调用异常: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
    
    # 如果获取失败，返回默认值
    return {
        "avatar_url": "https://avatars.githubusercontent.com/u/1000000?v=4",
        "name": config.get('name', 'Example User'),
        "bio": config.get('bio', 'Python Developer'),
        "total_repos": 0,
        "total_stars": 0,
        "readme_content": get_local_readme(),
        "recent_repos": [],
        "activity_data": [65, 59, 80, 81, 56, 55, 70, 65, 85, 75, 60, 75],  # 默认数据
        "activity_labels": _activity_month_labels(datetime.now()),
        "star_data": [10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65],  # 默认数据
        "star_labels": _activity_month_labels(datetime.now()),
        "organizations": [],
        "tech_stack": [
            {"name": "Python", "color": "#6a11cb"},
            {"name": "JavaScript", "color": "#2575fc"},
            {"name": "HTML/CSS", "color": "#560bad"},
            {"name": "Flask", "color": "#1e40af"}
        ]
    }

def _parse_github_date(date_str):
    """解析 GitHub API 的 ISO 8601 时间戳，失败返回 None。"""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%SZ')
    except (ValueError, TypeError):
        pass
    try:
        # 兼容带时区偏移的格式，如 2024-01-01T08:00:00+08:00
        return datetime.fromisoformat(date_str.replace('Z', '+00:00')).replace(tzinfo=None)
    except (ValueError, TypeError):
        return None

def _month_index(event_date, now):
    """把事件日期折算成「距当前月的月数」，索引 0 为当前月，11 为 11 个月前。"""
    months_diff = (now.year - event_date.year) * 12 + (now.month - event_date.month)
    if months_diff < 0:
        months_diff = 0
    return months_diff

# 获取用户的GitHub活动数据（最近12个自然月的贡献统计）
def _activity_month_labels(now):
    """生成图表 X 轴标签：最近 12 个自然月，最旧月 → 最新月。"""
    labels = []
    for i in range(11, -1, -1):
        total = (now.year * 12 + now.month - 1) - i
        year, month = divmod(total, 12)
        labels.append(f'{month + 1}月')
    return labels

def _activity_window_start(now):
    """统计窗口起点：11 个月前的 1 号，覆盖 12 个自然月且跨度小于 1 年。"""
    total = (now.year * 12 + now.month - 1) - 11
    year, month = divmod(total, 12)
    return datetime(year, month + 1, 1)

# Star 增长历史
def get_github_star_history(username, repos=None):
    """返回 (star_data, star_labels)：最近 12 个自然月的累计 star 总量。"""
    default_data = [10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65]

    try:
        print(f"开始获取GitHub Star增长数据: {username}")

        now = datetime.now()
        labels = _activity_month_labels(now)

        if not repos:
            print("没有仓库数据，返回默认Star数据")
            return default_data, labels

        # 索引 0 为当前月，11 为 11 个月前；索引越小月份越新
        monthly_totals = [0] * 12
        for repo in repos:
            if not isinstance(repo, dict):
                continue
            stars = repo.get('stargazers_count') or 0
            if stars <= 0:
                continue

            created_date = _parse_github_date(repo.get('created_at'))
            if created_date is None:
                continue

            month_index = _month_index(created_date, now)
            if month_index < 0:
                continue

            # 仓库在创建月之后一直存在，因此填充「当前月 → 创建月」这一段
            last_index = month_index if month_index < 12 else 11
            for index in range(last_index + 1):
                monthly_totals[index] += stars

        # 反转为「最旧月 → 最新月」，与图表标签顺序对齐
        star_data = monthly_totals[::-1]

        if sum(star_data) == 0:
            print("没有获取到Star数据，返回默认数据")
            return default_data, labels

        print(f"Star增长统计完成，当前累计: {star_data[-1]}")
        return star_data, labels
    except Exception as e:
        print(f"获取GitHub Star增长数据异常: {e}")

    return default_data, _activity_month_labels(datetime.now())

# 获取用户加入的 GitHub 组织
def get_github_organizations(username):
    """返回组织列表，每项含 login / avatar_url / url。"""
    try:
        print(f"开始获取GitHub组织列表: {username}")

        orgs_response = make_github_request(
            f'https://api.github.com/users/{username}/orgs?per_page=100'
        )
        if orgs_response.status_code != 200:
            print(f"无法获取组织数据，状态码: {orgs_response.status_code}")
            return []

        orgs = orgs_response.json()
        if not isinstance(orgs, list):
            print("组织响应不是JSON数组")
            return []

        organizations = []
        seen_logins = set()
        for org in orgs:
            if not isinstance(org, dict):
                continue
            login = (org.get('login') or '').strip()
            avatar_url = org.get('avatar_url')
            if not login or not avatar_url:
                continue

            # 按 login 小写去重，避免重复条目
            key = login.lower()
            if key in seen_logins:
                continue
            seen_logins.add(key)

            organizations.append({
                'login': login,
                'avatar_url': avatar_url,
                'url': org.get('url') or f"https://github.com/{login}"
            })

        # 按 login 字母序排序，保证输出稳定
        organizations.sort(key=lambda item: item['login'].lower())
        print(f"组织列表获取完成，共 {len(organizations)} 个")
        return organizations
    except Exception as e:
        print(f"获取GitHub组织列表异常: {e}")
        return []

def get_github_contribution_months(username, token=''):
    """通过 GraphQL contributionsCollection 获取官方贡献日历的月度聚合。"""
    if not token:
        return None, None

    now = datetime.now()
    window_start = _activity_window_start(now)

    query = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          contributionCalendar {
            totalContributions
            weeks {
              contributionDays {
                date
                contributionCount
              }
            }
          }
        }
      }
    }
    """
    variables = {
        'login': username,
        'from': window_start.strftime('%Y-%m-%dT00:00:00Z'),
        'to': now.strftime('%Y-%m-%dT23:59:59Z'),
    }

    try:
        response = requests.post(
            'https://api.github.com/graphql',
            json={'query': query, 'variables': variables},
            headers={'Authorization': f'bearer {token}', 'Accept': 'application/vnd.github+json'},
            timeout=5,
            verify=False,
        )
        print(f"GitHub GraphQL请求: 贡献日历, 状态码: {response.status_code}")
        if response.status_code != 200:
            return None, None

        payload = response.json()
        if not isinstance(payload, dict):
            print("GraphQL响应不是JSON对象")
            return None, None
        if payload.get('errors'):
            print(f"GraphQL贡献日历查询出错: {payload['errors']}")
            return None, None

        collection = (payload.get('data') or {}).get('user') or {}
        calendar = (collection.get('contributionsCollection') or {}).get('contributionCalendar')
        if not calendar:
            print("GraphQL未返回贡献日历数据")
            return None, None

        counts = [0] * 12
        for week in calendar.get('weeks') or []:
            for day in week.get('contributionDays') or []:
                raw_date = day.get('date')
                if not raw_date:
                    continue
                day_date = _parse_github_date(f"{raw_date}T00:00:00Z")
                if day_date is None or day_date < window_start:
                    continue
                month_index = _month_index(day_date, now)
                if 0 <= month_index < 12:
                    counts[month_index] += day.get('contributionCount') or 0

        print(f"贡献日历统计完成，窗口内总贡献: {sum(counts)}")
        return counts, _activity_month_labels(now)
    except Exception as e:
        print(f"获取贡献日历异常: {type(e).__name__}: {e}")
        return None, None

def get_github_activity_data(username, repos=None):
    """返回 (activity_data, activity_labels)。"""
    default_data = [65, 59, 80, 81, 56, 55, 70, 65, 85, 75, 60, 75]

    try:
        print(f"开始获取GitHub活动数据: {username}")

        now = datetime.now()
        labels = _activity_month_labels(now)
        # 窗口：11 个月前的 1 号至当前时刻，覆盖 12 个自然月且不超过 1 年
        window_start = _activity_window_start(now)
        earliest_date = window_start

        # 1. 优先使用 GraphQL 官方贡献日历，口径与 GitHub 个人主页一致
        counts, gql_labels = get_github_contribution_months(username, get_github_token())
        if counts is not None and sum(counts) > 0:
            return counts[::-1], gql_labels

        print("贡献日历不可用，回退到 REST 统计")

        # 按自然月聚合的推送事件数；索引 0 为当前月，11 为 11 个月前
        push_counts = [0] * 12
        # 同一仓库同秒内的多个 PushEvent 视为一次推送，用于去重
        seen_pushes = set()

        # 2. 用户 Events API（GitHub 官方活动时间线），按时间倒序翻页
        page = 1
        max_pages = 3
        while page <= max_pages:
            events_url = f"https://api.github.com/users/{username}/events?page={page}&per_page=100"
            events_response = make_github_request(events_url)

            if events_response.status_code != 200:
                print(f"无法获取事件数据，状态码: {events_response.status_code}")
                break

            events = events_response.json()
            if not isinstance(events, list) or not events:
                break

            reached_window_edge = False
            for event in events:
                if event.get('type') != 'PushEvent':
                    continue

                event_date = _parse_github_date(event.get('created_at'))
                if event_date is None:
                    continue

                if event_date < earliest_date:
                    reached_window_edge = True
                    continue

                # 只统计当前作者本人仓库的推送
                if event.get('actor', {}).get('login', '').lower() != username.lower():
                    continue

                repo_name = event.get('repo', {}).get('name', '')
                if repo_name and not repo_name.lower().startswith(f'{username.lower()}/'):
                    continue

                month_index = _month_index(event_date, now)
                if 0 <= month_index < 12:
                    # 以「仓库 + 推送时间」去重，避免同一推送被重复计数
                    push_key = (repo_name, event_date.strftime('%Y-%m-%dT%H:%M:%SZ'))
                    if push_key in seen_pushes:
                        continue
                    seen_pushes.add(push_key)
                    push_counts[month_index] += 1

            if reached_window_edge:
                break
            page += 1

        # 记录 Events API 已覆盖的「仓库 + 月份」，补齐时跳过，防止重复计数
        events_covered = {
            (repo_name, _month_index(datetime.strptime(push_key[1], '%Y-%m-%dT%H:%M:%SZ'), now))
            for push_key in seen_pushes
        }

        # 3. 用仓库提交历史补齐 Events API 未覆盖的月份
        if repos:
            print("使用仓库提交历史补齐活动数据")
            for repo in repos:
                repo_name = repo.get('name')
                if not repo_name:
                    continue
                try:
                    commits_url = (
                        f"https://api.github.com/repos/{username}/{repo_name}/commits"
                        f"?author={username}&since={earliest_date.strftime('%Y-%m-%dT%H:%M:%SZ')}&per_page=100"
                    )
                    commits_response = make_github_request(commits_url)
                    if commits_response.status_code != 200:
                        continue

                    commits = commits_response.json()
                    if not isinstance(commits, list):
                        continue
                    for commit in commits:
                        commit_date = _parse_github_date(
                            commit.get('commit', {}).get('author', {}).get('date')
                        )
                        if commit_date is None or commit_date < earliest_date:
                            continue

                        month_index = _month_index(commit_date, now)
                        if 0 <= month_index < 12:
                            # Events API 已统计过的「仓库 + 月份」不重复计数
                            if (repo_name, month_index) in events_covered:
                                continue
                            events_covered.add((repo_name, month_index))
                            push_counts[month_index] += 1
                except Exception as e:
                    print(f"获取仓库 {repo_name} 的提交历史时出错: {e}")
                    continue

        # 4. 反转为「最旧月 → 最新月」，与图表标签顺序对齐
        ordered_activity = push_counts[::-1]

        if sum(ordered_activity) == 0:
            print("没有获取到活动数据，返回默认数据")
            return default_data, labels

        # 不做平滑与缩放，直接返回真实统计值
        return ordered_activity, labels
    except Exception as e:
        print(f"获取GitHub活动数据异常: {e}")

    return default_data, _activity_month_labels(datetime.now())

# 分析用户的技术栈
cached_tech_stack = None
cached_timestamp = 0

CACHE_DURATION = 3600  # 缓存1小时
def analyze_tech_stack(repos):
    global cached_tech_stack, cached_timestamp
    
    # 检查缓存是否有效（如果启用了缓存）
    current_time = time.time()
    if cached_tech_stack and (current_time - cached_timestamp < CACHE_DURATION):
        print("使用缓存的技术栈数据")
        return cached_tech_stack
    
    try:
        print("开始分析用户的技术栈")
        
        # 创建语言统计字典
        language_stats = {}
        total_bytes = 0
        
        # 限制处理的仓库数量，只处理最近活跃的前10个仓库
        if len(repos) > 10:
            repos = repos[:10]
        
        # 遍历仓库，统计语言使用情况
        for repo in repos:
            # 获取仓库的语言信息（先尝试从仓库数据中获取，减少API调用）
            if 'language' in repo and repo['language']:
                lang = repo['language']
                if lang not in language_stats:
                    language_stats[lang] = 1  # 给主要语言一个基础分
                else:
                    language_stats[lang] += 1  # 增加主要语言的权重
                    
            # 仅对前几个重要的仓库进行详细的语言统计
            if len(language_stats) < 5 and 'languages_url' in repo:
                try:
                    languages_response = make_github_request(repo['languages_url'])
                    
                    if languages_response.status_code == 200:
                        languages_data = languages_response.json()
                        if not isinstance(languages_data, dict):
                            continue

                        # 更新语言统计
                        for lang, bytes_count in languages_data.items():
                            if not isinstance(bytes_count, (int, float)):
                                continue
                            if lang not in language_stats:
                                language_stats[lang] = 0
                            language_stats[lang] += bytes_count
                            total_bytes += bytes_count
                except Exception as e:
                    print(f"获取仓库 {repo.get('name')} 的语言信息时出错: {e}")
                    continue

        # 如果没有获取到语言数据，返回默认技术栈
        if not language_stats:
            print("没有获取到语言数据，返回默认技术栈")
            # 更新缓存
            cached_tech_stack = [
                {"name": "Python", "color": "#6a11cb"},
                {"name": "JavaScript", "color": "#2575fc"},
                {"name": "HTML/CSS", "color": "#560bad"},
                {"name": "Flask", "color": "#1e40af"}
            ]
            cached_timestamp = time.time()
            return cached_tech_stack
        
        # 计算每种语言的使用比例
        language_ratios = {}
        for lang, bytes_count in language_stats.items():
            # 考虑仓库数量和代码量的权重
            language_ratios[lang] = bytes_count
        
        # 按使用比例排序，取前10种语言
        sorted_languages = sorted(language_ratios.items(), key=lambda x: x[1], reverse=True)[:10]
        
        # 主题色来自全局 config，与模板注入的是同一份
        theme = config.get('theme', {})
        base_light = [
            theme.get('primary_color') or '#6a11cb',
            theme.get('secondary_color') or '#2575fc',
        ]
        base_dark = [
            theme.get('dark_primary_color') or '#a855f7',
            theme.get('dark_secondary_color') or '#60a5fa',
        ]

        def _to_rgb(hex_color):
            """解析 #RRGGBB；3 位缩写展开，非法值回落主色。"""
            value = (hex_color or '').strip().lstrip('#')
            if len(value) == 3:
                value = ''.join(c * 2 for c in value)
            if len(value) != 6:
                value = '6a11cb'
            try:
                return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
            except ValueError:
                return 0x6a, 0x11, 0xcb

        # 根据主题色生成和谐的标签颜色
        def generate_harmonious_color(base_color, index, is_dark=False):
            r, g, b = _to_rgb(base_color)
            
            # 根据索引调整颜色亮度和饱和度
            factor = 1.0 - (index * 0.15)  # 递减因子
            if factor < 0.4:
                factor = 0.4  # 确保颜色不会太暗
                
            # 考虑暗色模式调整
            if is_dark:
                # 在暗色模式下，使用较亮的颜色变体
                factor = 0.6 + (index * 0.1)  # 递增因子，确保至少有一定亮度
                if factor > 0.9:
                    factor = 0.9  # 避免颜色过亮
            
            # 应用调整
            r = int(r * factor)
            g = int(g * factor)
            b = int(b * factor)
            
            # 转换回HEX
            return f'#{r:02x}{g:02x}{b:02x}'
        
        # 检查是否为暗色模式
        is_dark = config.get('dark_mode', 'auto') == 'dark'
        base_colors = base_dark if is_dark else base_light
        color_map = {
            'Python': generate_harmonious_color(base_colors[0], 0, is_dark),
            'JavaScript': generate_harmonious_color(base_colors[1], 0, is_dark),
            'Java': generate_harmonious_color(base_colors[0], 1, is_dark),
            'TypeScript': generate_harmonious_color(base_colors[1], 1, is_dark),
            'Go': generate_harmonious_color(base_colors[0], 2, is_dark),
            'Rust': generate_harmonious_color(base_colors[1], 2, is_dark),
            'PHP': generate_harmonious_color(base_colors[0], 3, is_dark),
            'C++': generate_harmonious_color(base_colors[1], 3, is_dark),
            'C': generate_harmonious_color(base_colors[0], 4, is_dark),
            'C#': generate_harmonious_color(base_colors[1], 4, is_dark),
            'Ruby': generate_harmonious_color(base_colors[0], 5, is_dark),
            'Swift': generate_harmonious_color(base_colors[1], 5, is_dark),
            'Kotlin': generate_harmonious_color(base_colors[0], 6, is_dark),
            'HTML': generate_harmonious_color(base_colors[1], 6, is_dark),
            'CSS': generate_harmonious_color(base_colors[0], 7, is_dark),
            'SCSS': generate_harmonious_color(base_colors[1], 7, is_dark),
            'Less': generate_harmonious_color(base_colors[0], 8, is_dark),
            'Flask': generate_harmonious_color(base_colors[1], 8, is_dark),
            'Django': generate_harmonious_color(base_colors[0], 9, is_dark),
            'React': generate_harmonious_color(base_colors[1], 9, is_dark),
            'Vue': generate_harmonious_color(base_colors[0], 10, is_dark),
            'Angular': generate_harmonious_color(base_colors[1], 10, is_dark),
            'Node.js': generate_harmonious_color(base_colors[0], 11, is_dark)
        }
        
        # 创建技术栈列表
        tech_stack = []
        for lang, _ in sorted_languages:
            # 特殊处理HTML和CSS，合并为HTML/CSS
            if lang == 'HTML' or lang == 'CSS':
                # 检查是否已经添加了HTML/CSS
                html_css_exists = False
                for tech in tech_stack:
                    if tech['name'] == 'HTML/CSS':
                        html_css_exists = True
                        break
                if not html_css_exists:
                    tech_stack.append({
                        "name": "HTML/CSS",
                        "color": color_map.get('HTML', 'orange')
                    })
            else:
                # 添加其他语言
                tech_stack.append({
                    "name": lang,
                    "color": color_map.get(lang, 'gray')  # 默认灰色
                })
        
        # 如果没有HTML/CSS但有SCSS或Less等，也添加HTML/CSS
        html_css_exists = False
        for tech in tech_stack:
            if tech['name'] == 'HTML/CSS':
                html_css_exists = True
                break
        
        if not html_css_exists:
            for lang, _ in sorted_languages:
                if lang in ['SCSS', 'Less', 'Sass']:
                    tech_stack.append({
                        "name": "HTML/CSS",
                        "color": color_map.get('HTML', 'orange')
                    })
                    break
        
        # 确保返回的技术栈不超过10个
        if len(tech_stack) > 10:
            tech_stack = tech_stack[:10]
        
        # 更新缓存
        cached_tech_stack = tech_stack
        cached_timestamp = time.time()
        
        print(f"分析完成的技术栈: {[tech['name'] for tech in tech_stack]}")
        return tech_stack
    except Exception as e:
        print(f"分析技术栈时发生异常: {e}")
        # 发生错误时返回默认技术栈
        return [
            {"name": "Python", "color": "blue"},
            {"name": "JavaScript", "color": "yellow"},
            {"name": "HTML/CSS", "color": "orange"},
            {"name": "Flask", "color": "green"}
        ]

# 获取同名仓库的 README
def get_readme_content(username):
    try:
        print(f"尝试获取GitHub同名仓库README: {username}/{username}")

        # 依次尝试 main / master 分支
        for branch in ('main', 'master'):
            readme_url = f'https://raw.githubusercontent.com/{username}/{username}/{branch}/README.md'
            readme_response = make_github_request(readme_url)
            print(f"README响应状态码 ({branch}): {readme_response.status_code}")

            if readme_response.status_code == 200:
                print(f"成功获取{branch}分支的README")
                return render_markdown(readme_response.text)

        print(f"GitHub README获取失败，状态码: {readme_response.status_code}")
    except Exception as e:
        print(f"GitHub README获取异常: {type(e).__name__}: {str(e)}")

    # 如果获取失败，读取本地文件
    print("使用本地README文件")
    return get_local_readme()

# 读取本地 README 文件
def get_local_readme():
    try:
        introduction_file = config.get('introduction_file', 'Introduction.md')
        if os.path.exists(introduction_file):
            with open(introduction_file, 'r', encoding='utf-8') as f:
                # 使用多个扩展来增强 Markdown 转换
                md_text = f.read()
                return render_markdown(md_text)
    except Exception:
        pass
    
    # 如果都没有，返回默认信息
    return "<p>这个人很懒，什么都没有留下～</p>"

@app.route('/')
def index():
    github_info = get_github_user_info()
    
    # 检查背景图片是否存在
    background_image = config.get('background', {}).get('image', 'background.png')
    
    # 构建完整的背景图片路径 - 检查多个可能的位置
    possible_paths = [
        os.path.join(os.getcwd(), background_image),  # 当前目录
        os.path.join(os.getcwd(), 'static', background_image)  # static目录
    ]
    
    background_exists = False
    background_path = background_image  # 默认使用配置中的路径
    
    # 检查哪个路径是有效的
    for path in possible_paths:
        if os.path.exists(path):
            background_exists = True
            # 如果找到图片，使用相对路径供模板使用
            if 'static' in path:
                background_path = f'/static/{background_image}'
            break
    
    print(f"背景图片配置: {background_image}")
    print(f"背景图片存在: {background_exists}")
    print(f"使用的背景图片路径: {background_path}")
    
    return render_template('index.html', 
                          github_info=github_info, 
                          config=config,
                          now=datetime.now(),
                          background_exists=background_exists,
                          background_path=background_path)

@app.route('/api/config')
def get_config():
    return jsonify(config)

# 提供根目录下的静态文件访问
@app.route('/<path:filename>')
def serve_root_file(filename):
    # 只允许访问特定的文件类型
    allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.svg', '.css', '.js'}
    file_ext = os.path.splitext(filename)[1].lower()
    
    if file_ext in allowed_extensions:
        try:
            return send_from_directory(os.getcwd(), filename)
        except FileNotFoundError:
            abort(404)
    
    # 对于不允许的文件类型，返回404
    abort(404)

def generate_static_html():
    """生成静态HTML文件，用于部署到GitHub Pages"""
    print("开始生成静态HTML文件...")
    
    # 创建静态文件目录
    static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static_build')
    if not os.path.exists(static_dir):
        os.makedirs(static_dir)
    else:
        # 清空目录中的所有文件
        for file in os.listdir(static_dir):
            file_path = os.path.join(static_dir, file)
            if os.path.isfile(file_path):
                os.remove(file_path)
    
    try:
        # 确保配置已加载
        if 'config' not in globals():
            print("加载配置文件...")
            try:
                with open('config.json', 'r', encoding='utf-8') as f:
                    config = json.load(f)
            except FileNotFoundError:
                # 默认配置
                config = {
                    "github_url": "https://github.com/example",
                    "dark_mode": "auto",
                    "name": "Example User",
                    "bio": "Python Developer",
                    "introduction_file": "Introduction.md",
                    "github_token": "",
                    "theme": {
                        "primary_color": "#6a11cb",
                        "secondary_color": "#2575fc"
                    },
                    "background": {
                        "image": "background.png",
                        "blur": 8,
                        "overlay_opacity": 0.6,
                        "overlay_color": "#121212"
                    }
                }
        
        # 读取介绍内容
        introduction_content = ""
        if 'introduction_file' in config and os.path.exists(config['introduction_file']):
            try:
                with open(config['introduction_file'], 'r', encoding='utf-8') as f:
                    introduction_content = f.read()
                # 转换Markdown为HTML
                introduction_content = render_markdown(introduction_content)
            except Exception as e:
                print(f"警告：无法读取或解析介绍文件: {e}")
        
        # 创建一个临时的Jinja2环境来渲染模板
        template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(template_dir),
            autoescape=jinja2.select_autoescape(['html', 'xml'])
        )
        
        # 获取模板
        template = env.get_template('index.html')
        
        # 准备渲染参数
        render_args = {
            'config': config,
            'introduction_content': introduction_content,
            'tech_stack': [],  # 由于没有GitHub数据，这里使用空列表
            'activity_data': [],  # 由于没有GitHub数据，这里使用空列表
            'activity_labels': _activity_month_labels(datetime.now()),
            'star_data': [],
            'star_labels': _activity_month_labels(datetime.now()),
            'error_message': None,
            'github_info': {
                'name': config.get('name', 'Example User'),
                'bio': config.get('bio', ''),
                'avatar_url': 'https://avatars.githubusercontent.com/u/10000000?v=4',  # 默认头像
                'html_url': config.get('github_url', 'https://github.com/example'),
                'public_repos': 0,
                'followers': 0,
                'activity_data': [],  # 添加可序列化的activity_data键
                'activity_labels': _activity_month_labels(datetime.now()),
                'star_data': [],
                'star_labels': _activity_month_labels(datetime.now()),
                'organizations': []
            },
            'now': datetime.now()  # 添加当前时间对象，用于显示年份
        }
        
        # 渲染模板
        print("渲染HTML模板...")
        html_content = template.render(**render_args)
        
        # 保存HTML文件
        html_path = os.path.join(static_dir, 'index.html')
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"静态HTML文件已保存到: {html_path}")
        
        # 复制必要的静态资源
        resources_to_copy = []
        # 检查是否有背景图片
        if 'background' in config and 'image' in config['background']:
            background_image = config['background']['image']
            if os.path.exists(background_image):
                resources_to_copy.append(background_image)
        
        # 检查一些常见的资源文件
        for file in ['background.jpg', '1background.jpg', 'favicon.ico']:
            if os.path.exists(file):
                resources_to_copy.append(file)
        
        # 复制资源文件
        for resource in resources_to_copy:
            try:
                dst = os.path.join(static_dir, os.path.basename(resource))
                shutil.copy(resource, dst)
                print(f"已复制资源文件: {resource}")
            except Exception as e:
                print(f"警告：无法复制资源文件 {resource}: {e}")
        
        print("\n静态文件生成成功！")
        print(f"\n如何部署到GitHub Pages:")
        print("1. 进入static_build目录")
        print("2. 初始化git仓库（如果尚未初始化）")
        print("3. 添加并提交所有文件")
        print("4. 将文件推送到GitHub仓库的gh-pages分支")
        print("\n示例命令：")
        print("cd static_build")
        print("git init")
        print("git add .")
        print("git commit -m 'Deploy to GitHub Pages'")
        print("git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git")
        print("git push -f origin master:gh-pages")
        print("\n注意：您需要替换YOUR_USERNAME和YOUR_REPO为您的GitHub用户名和仓库名。")
        
    except Exception as e:
        print(f"错误：生成静态文件失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == '__main__':
    # 检查是否需要生成静态HTML
    if len(sys.argv) > 1 and sys.argv[1] == 'generate_static':
        generate_static_html()
    else:
        # 设置环境变量，使得 GitHub Pages 能够正确运行
        os.environ['FLASK_APP'] = 'app.py'
        # 监听地址与端口可由环境变量覆盖；默认 0.0.0.0 以便容器内可达
        app.run(
            debug=True,
            host=os.environ.get('HOST', '0.0.0.0'),
            port=int(os.environ.get('PORT', 5000)),
        )