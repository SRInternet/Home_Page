# -*- coding: utf-8 -*-
"""
自定义静态文件构建脚本
这个脚本将直接使用Flask测试客户端来生成静态HTML文件
"""
import os
import sys
import shutil
import importlib.util
import json  # 导入json模块

# 设置工作目录
here = os.path.dirname(os.path.abspath(__file__))
os.chdir(here)

# 设置静态文件目录为项目根目录
static_dir = here
print(f"将在项目根目录 {static_dir} 生成静态文件")

print("正在准备生成静态文件...")

# 读取config.json配置文件，如不存在则从default文件夹复制
config_path = os.path.join(here, 'config.json')
default_config_path = os.path.join(here, 'default', 'default_config.json')

if os.path.exists(config_path):
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    # 从配置中获取背景图片文件名
    background_image = config.get('background', {}).get('image', 'background.jpg')
else:
    print("警告：未找到config.json文件")
    # 尝试从default文件夹复制默认配置
    if os.path.exists(default_config_path):
        print(f"从{default_config_path}复制默认配置到{config_path}")
        shutil.copy2(default_config_path, config_path)
        # 读取复制过来的配置
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        background_image = config.get('background', {}).get('image', 'background.jpg')
        
        # 同时检查背景图片是否存在，如果不存在也从default文件夹复制
        if background_image and not os.path.exists(background_image) and os.path.exists(os.path.join('default', background_image)):
            print(f"{background_image}不存在，从default文件夹复制")
            shutil.copy2(os.path.join('default', background_image), background_image)
    else:
        print("警告：default/default_config.json也不存在，使用默认背景图片")
        background_image = 'background.jpg'

# 导入app.py并使用Flask测试客户端
try:
    # 动态导入app.py
    spec = importlib.util.spec_from_file_location("app", os.path.join(here, "app.py"))
    app_module = importlib.util.module_from_spec(spec)
    sys.modules["app"] = app_module
    spec.loader.exec_module(app_module)
    
    # 直接使用Flask测试客户端方法（根据用户反馈，generate_static_html函数有问题）
    if hasattr(app_module, 'app'):
        print("使用Flask测试客户端获取页面内容...")
        
        # 使用Flask测试客户端
        client = app_module.app.test_client()
        response = client.get('/')
        
        if response.status_code == 200:
            # 保存HTML内容到根目录
            html_path = os.path.join(static_dir, 'index.html')
            
            # 确认是否已有index.html文件，如果有则备份
            if os.path.exists(html_path):
                backup_path = os.path.join(static_dir, 'index.html.bak')
                # 检查源文件和目标文件是否相同
                if os.path.normpath(html_path) != os.path.normpath(backup_path):
                    shutil.copy(html_path, backup_path)
                    print(f"已备份现有index.html文件到: {backup_path}")
            
            with open(html_path, 'wb') as f:
                f.write(response.data)
            
            print(f"静态HTML文件已保存到项目根目录: {html_path}")
        else:
            print(f"错误：无法获取首页内容，状态码: {response.status_code}")
            sys.exit(1)
    else:
        print("错误：app.py中未找到app实例")
        sys.exit(1)

except Exception as e:
    print(f"错误：生成静态文件时出现异常: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 复制其他必要的静态资源到根目录
print("正在复制其他静态资源...")
for file in [background_image]:  # 使用从配置中读取的背景图片文件名
    src = os.path.join(here, 'static_build', file)
    if not os.path.exists(src):
        # 如果在static_build目录中找不到，则尝试在当前目录查找
        src = os.path.join(here, file)
    
    if os.path.exists(src):
        dst = os.path.join(static_dir, file)
        
        # 检查源文件和目标文件是否为同一个文件
        try:
            # 首先确认是否已有该资源文件，如果有则备份
            if os.path.exists(dst):
                backup_path = f"{dst}.bak"
                shutil.copy(dst, backup_path)
                print(f"已备份现有资源文件到: {backup_path}")
            
            # 检查是否为同一个文件
            if not os.path.samefile(src, dst):
                shutil.copy(src, dst)
                print(f"已复制资源文件: {file}")
            else:
                print(f"源文件和目标文件是同一个文件，跳过复制: {file}")
        except shutil.SameFileError:
            print(f"源文件和目标文件是同一个文件，跳过复制: {file}")

print("\n静态文件构建完成！")
print(f"\n静态HTML文件已生成在项目根目录: {os.path.join(static_dir, 'index.html')}")
print(f"\n如何部署到GitHub Pages:")
print("方式一：自动部署（已配置GitHub Pages Actions）")
print("1. 当您推送到main或master分支时，GitHub Actions会自动运行")
print("2. GitHub Actions也会在每天UTC时间0点（北京时间8点）自动运行")
print("3. 您也可以通过GitHub仓库的Actions页面手动触发运行")
print("4. 构建产物会直接部署到GitHub Pages，无需额外配置GitHub Token")
print("\n方式二：手动部署")
print("1. 确保您已经在项目根目录")
print("2. 直接将生成的index.html和background.jpg文件部署到您的Web服务器")
print("\n注意：")
print("1. 使用GitHub Pages部署方式不需要配置GitHub Token")
print("2. 部署不会在仓库中产生额外的提交记录")
print("3. 确保GitHub仓库启用了GitHub Pages功能")
print("4. 访问路径通常为 https://YOUR_USERNAME.github.io/YOUR_REPO/")