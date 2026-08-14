# -*- coding: utf-8 -*-
"""
统一请求层：随机 UA、指数退避重试、限速、编码处理、robots.txt 检查、probe 探测。
"""
import random
import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests

import config


class HttpClient:
    """带限速、重试、UA 轮换、robots 检查的 HTTP 客户端。"""

    def __init__(self, interval=None, retries=None, timeout=None, probe=False,
                 max_requests=None):
        self.interval = interval if interval is not None else config.REQUEST_INTERVAL
        self.retries = retries if retries is not None else config.REQUEST_RETRIES
        self.timeout = timeout if timeout is not None else config.REQUEST_TIMEOUT
        self.max_requests = max_requests if max_requests is not None \
            else config.MAX_REQUESTS_PER_RUN
        self.probe = probe
        self._request_count = 0
        self._last_request_time = 0.0
        self.session = requests.Session()
        self._robots_cache = {}

    # -------------------- 对外接口 --------------------
    def get(self, url, *, params=None, headers=None):
        return self._request("GET", url, params=params, headers=headers)

    def post(self, url, *, json=None, data=None, headers=None):
        return self._request("POST", url, json=json, data=data, headers=headers)

    def download(self, url, dest_path, *, headers=None):
        """下载二进制文件到 dest_path，返回文件大小（字节）。

        注意：跳过 robots.txt 检查 —— 这里下载的是带签名/授权的临时 URL
        （如 flk 的 OSS 签名链接），robots 检测会误伤且签名有有效期。
        """
        self._pace_only(url)
        with self.session.get(
                url, headers=self._headers(headers), timeout=self.timeout,
                stream=True) as resp:
            resp.raise_for_status()
            size = 0
            with open(dest_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        size += len(chunk)
            self._after_request(resp)
            return size

    def robots_allowed(self, url):
        """检查 robots.txt 是否允许抓取；读不到 robots 时默认放行。"""
        parsed = urlparse(url)
        host = f"{parsed.scheme}://{parsed.netloc}"
        if host not in self._robots_cache:
            rp = RobotFileParser()
            rp.set_url(f"{host}/robots.txt")
            try:
                rp.read()
            except Exception:
                # 读不到 robots.txt 或超时 → 放行
                self._robots_cache[host] = None
            else:
                self._robots_cache[host] = rp
        rp = self._robots_cache[host]
        return True if rp is None else rp.can_fetch("*", url)

    # -------------------- 内部实现 --------------------
    def _request(self, method, url, **kw):
        self._before_request(url)
        last_err = None
        for attempt in range(self.retries):
            try:
                resp = self.session.request(
                    method, url, headers=self._headers(kw.pop("headers", None)),
                    timeout=self.timeout, **kw)
                resp.raise_for_status()
                self._after_request(resp)
                self._probe_log(f"{method} {url}", resp)
                return resp
            except (requests.RequestException, OSError) as e:
                last_err = e
                if attempt < self.retries - 1:
                    backoff = 2 ** attempt
                    if self.probe:
                        print(f"  ⏳ 请求失败，{backoff}s 后重试 ({attempt+1}/{self.retries})：{url}")
                    time.sleep(backoff)
        raise last_err

    def _pace_only(self, url):
        """仅限速 + 计数，不查 robots（用于签名/授权下载链接）。"""
        wait = self._last_request_time + self.interval - time.time()
        if wait > 0:
            time.sleep(wait)
        self._request_count += 1
        if self._request_count > self.max_requests:
            raise RuntimeError(
                f"已达单次运行请求上限 {self.max_requests}，请分批运行或调大 "
                f"config.MAX_REQUESTS_PER_RUN")

    def _before_request(self, url):
        """限速 + 请求计数 + robots 检查。"""
        self._pace_only(url)
        # robots 检查：被禁止则抛错（调用方决定是否忽略）
        if not self.robots_allowed(url):
            raise RuntimeError(f"robots.txt 禁止抓取: {url}")

    def _after_request(self, resp):
        self._last_request_time = time.time()
        # 处理编码：优先响应头编码，兼容 GBK/GB2312。
        # 注意：流式响应(stream=True)已被 iter_content 消费后，访问
        # apparent_encoding 会触发 "content already consumed"，需防护。
        try:
            if resp.encoding is None or resp.encoding.lower() == "iso-8859-1":
                resp.encoding = resp.apparent_encoding
        except Exception:
            pass  # 二进制/已消费响应不设编码

    def _headers(self, extra=None):
        h = {"User-Agent": random.choice(config.UA_POOL),
             "Accept": "*/*",
             "Accept-Language": "zh-CN,zh;q=0.9"}
        if extra:
            h.update(extra)
        return h

    def _probe_log(self, tag, resp):
        """probe 模式打印响应摘要（帮助验证接口/页面结构）。"""
        if not self.probe:
            return
        text = resp.text
        print(f"  ── probe [{tag}] status={resp.status_code} len={len(text)}")
        # 打印前 400 字符，去换行
        snippet = " ".join(text.split())[:400]
        print(f"     {snippet}")
