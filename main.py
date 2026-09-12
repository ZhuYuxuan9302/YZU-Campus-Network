import httpx
import json
import os
import re
import sys
import time
import urllib.parse

SERVICE_LIST: list = [
    "学校互联网服务",
    "联通互联网服务",
    "移动互联网服务",
    "电信互联网服务",
    "校内免费服务"
]

# ==================== 配置信息（通过环境变量导入） ====================
# 说明：认证入口无需配置——断线时会自动访问网关拦截页动态获取（参数实时有效）
# 必需环境变量：
#   YZU_USER_ID        学工号 / 用户名
#   YZU_PASSWORD       校园网密码
# 可选环境变量（未设置时使用内置默认值）：
#   YZU_SERVICE_INDEX  网络服务索引，取值 1-5，默认 1
#                      1=学校互联网服务, 2=联通互联网服务, 3=移动互联网服务,
#                      4=电信互联网服务, 5=校内免费服务
#   YZU_CHECK_URL      外网连通性检测地址，默认小米官方连通性检测接口：
#                      http://connect.rom.miui.com/generate_204
#                      （返回 204 空响应视为在线；其它状态、超时、连接失败均视为断线）
ENV_USER_ID = "YZU_USER_ID"
ENV_PASSWORD = "YZU_PASSWORD"
ENV_SERVICE_INDEX = "YZU_SERVICE_INDEX"
ENV_CHECK_URL = "YZU_CHECK_URL"
DEFAULT_SERVICE_INDEX = 1
DEFAULT_CHECK_URL = "http://connect.rom.miui.com/generate_204"  # 小米官方连通性检测接口（返回 204 空响应）
CHECK_TIMEOUT = 5    # 单次连通性检测的超时时间（秒）
CHECK_INTERVAL = 10  # 外网连通性检测的时间间隔（秒）
PORTAL_DETECT_URL = "http://123.123.123.123"  # 触发网关拦截以动态获取认证入口的探测地址
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:60.0) Gecko/20100101 Firefox/60.0"


def show_msg(msg: str, duration: int = 5):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [通知] {msg}")


def load_config() -> tuple[str, str, int, str]:
    """从环境变量读取配置信息，缺失或非法时提示并退出。"""
    missing = [
        key
        for key in (ENV_USER_ID, ENV_PASSWORD)
        if not os.environ.get(key, "").strip()
    ]
    if missing:
        show_msg(
            "以下必需的环境变量未设置：" + ", ".join(missing) + "。请先设置，再重新运行（详见 README）。"
        )
        sys.exit(1)

    user_id = os.environ[ENV_USER_ID].strip()
    password = os.environ[ENV_PASSWORD]

    raw_index = os.environ.get(ENV_SERVICE_INDEX, "").strip() or str(DEFAULT_SERVICE_INDEX)
    try:
        service_index = int(raw_index)
    except ValueError:
        show_msg(f"环境变量 {ENV_SERVICE_INDEX} 必须是 1-{len(SERVICE_LIST)} 之间的整数，当前值：{raw_index}")
        sys.exit(1)

    if not 1 <= service_index <= len(SERVICE_LIST):
        show_msg(f"环境变量 {ENV_SERVICE_INDEX} 超出范围（应为 1-{len(SERVICE_LIST)}），当前值：{service_index}")
        sys.exit(1)

    check_url = os.environ.get(ENV_CHECK_URL, "").strip() or DEFAULT_CHECK_URL
    if not check_url.startswith(("http://", "https://")):
        show_msg(f"环境变量 {ENV_CHECK_URL} 需要是以 http:// 或 https:// 开头的完整 URL。")
        sys.exit(1)

    return user_id, password, service_index, check_url


def check_online(client: httpx.Client, check_url: str) -> tuple[bool, str]:
    """主动探测外网连通性：返回 204 视为在线（True）；其它状态、超时、连接失败均视为断线（False）。

    返回值第二项为本次检测详情（如 HTTP 204 / HTTP 302 / ConnectTimeout），用于日志排障。
    """
    try:
        res = client.get(check_url, timeout=CHECK_TIMEOUT, follow_redirects=True)
    except (httpx.HTTPError, httpx.InvalidURL) as e:
        return False, type(e).__name__
    return (res.status_code == 204), f"HTTP {res.status_code}"


def discover_portal_url(client: httpx.Client) -> str:
    """访问探测地址触发网关拦截页，从中解析出实时有效的认证入口 URL。"""
    show_msg(f"正在访问 {PORTAL_DETECT_URL} 触发网关拦截页...")
    res = client.get(PORTAL_DETECT_URL, timeout=CHECK_TIMEOUT, follow_redirects=True)
    show_msg(f"网关拦截页响应：HTTP {res.status_code}")

    match = re.search(r"href='([^']+)'", res.text)
    if not match:
        print(f"拦截页内容预览: {res.text[:300] if res.text else '<EMPTY RESPONSE>'}")
        raise ConnectionError("未能从网关拦截页中解析出认证入口 URL")
    return match.group(1)


def parse_portal_url(portal_url: str) -> tuple[str, str]:
    """从认证入口 URL 中解析出网关 host 与 queryString。"""
    match = re.match(r"https?://(.+?)/.*?\?(.+)", portal_url)
    if not match:
        raise ConnectionError(f"无法从认证入口 URL 中提取 host 与 queryString。当前URL: {portal_url}")
    return match.group(1), match.group(2)


def login_attempt(client: httpx.Client, user_id: str, password: str, service_index: int):
    try:
        portal_url = discover_portal_url(client)
        show_msg(f"已获取认证入口：{portal_url}")
        host, query_string = parse_portal_url(portal_url)

        show_msg(f"正在尝试登录（host={host}，服务：{SERVICE_LIST[service_index - 1]}）...")

        data = {
            "userId": user_id,
            "password": password,
            "service": urllib.parse.quote(SERVICE_LIST[service_index - 1], safe=""),
            "queryString": query_string,
            "validcode": "",
            "passwordEncrypt": "false",
        }

        login_url = f"http://{host}/eportal/InterFace.do?method=login"
        res = client.post(login_url, data=data, timeout=10)
        show_msg(f"登录接口响应：HTTP {res.status_code}")

        # --- 针对断网/无效响应的修改 ---
        try:
            res_json = res.json()
        except json.JSONDecodeError:
            # 当服务器返回空内容或非JSON内容时捕获此错误
            show_msg("登录失败：服务器响应格式错误。可能原因：您正处于断网状态，且网关返回了非标准错误页面。", 5)
            # 打印响应文本帮助调试，如果是空字符串则打印 <EMPTY RESPONSE>
            print(f"原始响应文本: {res.text if res.text else '<EMPTY RESPONSE>'}")
            return
        # --- 针对断网/无效响应的修改结束 ---

        if res_json.get("result") == "success":
            show_msg("校园网成功连接了，Ciallo～(∠・ω< )～", 5)
        elif res_json.get("result") == "fail":
            show_msg(f"登录失败: {res_json.get('message', '未知错误')}", 5)
        else:
            show_msg(f"登录响应异常: {res.text}", 5)

    except (httpx.ConnectTimeout, httpx.ConnectError):
        show_msg("网络连接错误：可能未联网或服务器无响应。", 5)
    except ConnectionError as e:
        show_msg(f"流程错误: {e}", 5)
    except Exception as e:
        print(f"发生意外错误: {e}")
        show_msg("发生意外错误，请检查控制台。", 5)


if __name__ == "__main__":
    user_id, password, service_index, check_url = load_config()

    masked_user_id = (user_id[:3] + "***" + user_id[-3:]) if len(user_id) > 6 else "***"
    show_msg("启动了喵...困困困喵", 1)
    show_msg(f"配置确认——账号：{masked_user_id}，服务：{SERVICE_LIST[service_index - 1]}，检测地址：{check_url}")
    show_msg(f"将每隔 {CHECK_INTERVAL} 秒检测一次外网连通性，断线时自动重新登录。", 3)

    with httpx.Client(verify=False) as client:
        client.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Referrer-Policy": "strict-origin-when-cross-origin"
        })

        while True:
            online, detail = check_online(client, check_url)
            if online:
                show_msg(f"外网连通正常（{detail}），无需操作。")
            else:
                show_msg(f"检测到外网连接异常（{detail}），正在尝试重新登录...")
                login_attempt(client, user_id, password, service_index)

            time.sleep(CHECK_INTERVAL)
