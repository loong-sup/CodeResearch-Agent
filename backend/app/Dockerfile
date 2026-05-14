FROM python:3.11.7-slim

# Bookworm 官方 slim 默认用 deb822：/etc/apt/sources.list.d/debian.sources，往往没有 /etc/apt/sources.list；
# 且本镜像是 Debian 不是 Ubuntu，不能对 archive.ubuntu.com 做 sed。
RUN set -eux; \
    f="/etc/apt/sources.list.d/debian.sources"; \
    if [ -f "$f" ]; then \
      sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' "$f"; \
      sed -i 's|security.debian.org|mirrors.tuna.tsinghua.edu.cn|g' "$f"; \
    else \
      printf '%s\n' \
        "deb https://mirrors.tuna.tsinghua.edu.cn/debian/ bookworm main contrib non-free non-free-firmware" \
        "deb https://mirrors.tuna.tsinghua.edu.cn/debian-security bookworm-security main contrib non-free non-free-firmware" \
        "deb https://mirrors.tuna.tsinghua.edu.cn/debian/ bookworm-updates main contrib non-free non-free-firmware" \
        > /etc/apt/sources.list; \
    fi

# 安装必要的构建工具和依赖
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    python3-dev \
    make \
    libgl1 \
    libgl1-mesa-glx \
    libglu1-mesa \
    libglib2.0-0 \
    # PDF 处理相关依赖
    libfontconfig1 \
    libfreetype6 \
    libxrender1 \
    libxext6 \
    libx11-6 \
    # 字体支持
    fonts-dejavu-core \
    fonts-liberation \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

# 更新 pip 并配置镜像源
RUN pip config set global.extra-index-url "https://mirrors.cernet.edu.cn/pypi/web/simple"
RUN pip install --upgrade pip setuptools wheel

# 设置工作目录
WORKDIR /app

# 拷贝依赖文件并安装
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

#下载NLTK数据
# 下载 NLTK 数据
ENV NLTK_DATA=/usr/local/share/nltk_data
RUN python -m nltk.downloader -d /usr/local/share/nltk_data \
    wordnet \
    omw-1.4 \
    punkt \
    punkt_tab

# 拷贝代码
COPY . /app

# 修改文件权限
RUN chmod -R 755 /app
