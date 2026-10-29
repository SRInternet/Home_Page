FROM python:3.13-alpine

WORKDIR /app

ENV TZ=Asia/Shanghai \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=5000

# alpine 基础镜像不含时区数据库，ENV TZ 需要它才能生效
RUN apk add --no-cache tzdata

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:5000/', timeout=3).status == 200 else 1)"

ENTRYPOINT ["python", "app.py"]
