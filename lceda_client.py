"""
立创EDA API 客户端（带重试、限流处理、多域名回退）。
"""

import time
import json
import requests
from typing import Optional


class LCEDAClient:
    """立创EDA API 客户端"""

    BASE_URL = "https://easyeda.com/api"

    SEARCH_URLS = [
        "https://pro.easyeda.com/api/eda/product/search",
        "https://easyeda.com/api/eda/product/search",
        "https://easyeda.com/api/products/search",
    ]

    # 更真实的浏览器 UA
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://easyeda.com/",
        "Origin": "https://easyeda.com",
    }

    API_VERSION = "6.5.44"

    def __init__(self, timeout: int = 60, max_retries: int = 4,
                 min_interval: float = 0.6):
        """
        Args:
            timeout: 单次 HTTP 请求超时（秒）
            max_retries: 最大重试次数
            min_interval: 同一 Client 实例内两次请求之间的最小间隔（秒）
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.min_interval = min_interval
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)
        self._last_request_time = 0.0

    # ============================================================
    # 内部：限流 + 重试
    # ============================================================

    def _wait_if_needed(self):
        """确保两次请求之间有 min_interval 的间隔"""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self.min_interval:
            wait = self.min_interval - elapsed
            time.sleep(wait)
        self._last_request_time = time.time()

    def _request_with_retry(self, method: str, url: str,
                            **kwargs) -> requests.Response:
        """
        带指数退避的 HTTP 请求。

        重试条件：
          - Timeout / ConnectionError
          - 5xx 服务器错误
          - 403 限流（等待更长时间再试）
        """
        kwargs.setdefault("timeout", self.timeout)
        last_error = None

        for attempt in range(self.max_retries):
            self._wait_if_needed()

            try:
                resp = self.session.request(method, url, **kwargs)

                # 200-299：成功
                if 200 <= resp.status_code < 300:
                    return resp

                # 403：限流，等更久再试
                if resp.status_code == 403:
                    last_error = requests.HTTPError(
                        f"HTTP 403 Forbidden (可能触发了限流)"
                    )
                    if attempt < self.max_retries - 1:
                        wait = 5 * (2 ** attempt)  # 5s, 10s, 20s
                        print(f"[LCEDAClient] HTTP 403 限流，"
                              f"{wait}s 后重试 ({attempt + 1}/{self.max_retries})")
                        time.sleep(wait)
                    continue

                # 429：显式限流
                if resp.status_code == 429:
                    last_error = requests.HTTPError(
                        f"HTTP 429 Too Many Requests"
                    )
                    if attempt < self.max_retries - 1:
                        wait = 10 * (2 ** attempt)
                        print(f"[LCEDAClient] HTTP 429 限流，"
                              f"{wait}s 后重试 ({attempt + 1}/{self.max_retries})")
                        time.sleep(wait)
                    continue

                # 5xx：服务器错误，重试
                if 500 <= resp.status_code < 600:
                    last_error = requests.HTTPError(
                        f"HTTP {resp.status_code} from {url}"
                    )
                    if attempt < self.max_retries - 1:
                        wait = 2 * (2 ** attempt)
                        print(f"[LCEDAClient] HTTP {resp.status_code}，"
                              f"{wait}s 后重试 ({attempt + 1}/{self.max_retries})")
                        time.sleep(wait)
                    continue

                # 其他 4xx：不重试，直接失败
                resp.raise_for_status()

            except (requests.Timeout, requests.ConnectionError) as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    wait = 2 ** attempt
                    print(f"[LCEDAClient] 请求失败 ({type(e).__name__})，"
                          f"{wait}s 后重试 ({attempt + 1}/{self.max_retries})")
                    time.sleep(wait)
                continue

            except requests.HTTPError:
                raise

        raise last_error if last_error else RuntimeError("请求失败且无错误信息")

    def _request_first_working_url(self, urls: list, method: str = "GET",
                                    **kwargs) -> requests.Response:
        """依次尝试多个 URL，返回第一个成功的响应"""
        last_error = None
        for url in urls:
            try:
                return self._request_with_retry(method, url, **kwargs)
            except Exception as e:
                last_error = e
                print(f"[LCEDAClient] {url} 不可用: {type(e).__name__}: {e}")
                continue
        raise last_error if last_error else RuntimeError("所有 URL 均不可用")

    # ============================================================
    # 公共 API
    # ============================================================

    def search_components(self, keyword: str, page: int = 1,
                          page_size: int = 10) -> dict:
        """搜索元器件"""
        params = {
            "keyword": keyword,
            "type": 3,
            "page": page,
            "pageSize": page_size,
        }

        try:
            resp = self._request_first_working_url(
                self.SEARCH_URLS, params=params
            )
            return resp.json()
        except requests.RequestException as e:
            raise ConnectionError(
                f"搜索失败：网络连接超时或不可达。\n"
                f"详情: {type(e).__name__}: {e}"
            ) from e

    def get_component_data(self, lcsc_code: str) -> Optional[dict]:
        """获取指定 LCSC 编号的元器件完整数据"""
        if not lcsc_code.upper().startswith("C"):
            lcsc_code = "C" + lcsc_code

        url = f"{self.BASE_URL}/products/{lcsc_code}/components"
        params = {"version": self.API_VERSION}

        try:
            resp = self._request_with_retry("GET", url, params=params)
            data = resp.json()

            if not data.get("success", False):
                print(f"[错误] API返回失败: {data.get('message', '未知错误')}")
                return None

            return data

        except requests.RequestException as e:
            print(f"[错误] 请求失败: {type(e).__name__}: {e}")
            return None
        except json.JSONDecodeError as e:
            print(f"[错误] JSON解析失败: {e}")
            return None

    def get_step_model_url(self, lcsc_code: str) -> Optional[str]:
        return None