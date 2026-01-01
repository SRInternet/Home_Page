# 使用 Python 3.10 轻量级镜像
FROM python:3.10-slim

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_APP=app.py \
    FLASK_ENV=production

# 设置工作目录
WORKDIR /app

# 创建非root用户
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# 复制依赖文件
COPY --chown=appuser:appuser requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir --user -r requirements.txt

# 将用户本地 bin 添加到 PATH
ENV PATH=/home/appuser/.local/bin:$PATH

# 复制应用代码
COPY --chown=appuser:appuser . .

# 暴露端口
EXPOSE 5000

# 启动应用
CMD ["python", "app.py"]