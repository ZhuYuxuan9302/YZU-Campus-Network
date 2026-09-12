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

# ==================== 配置信息（全部通过环境变量导入） ====================
# 必需环境变量：
#   YZU_USER_ID        学工号 / 用户名
#   YZU_PASSWORD       校园网密码
#   YZU_INITIAL_URL    SSO 认证入口 URL（从浏览器地址栏完整复制）
# 可选环境变量：
#   YZU_SERVICE_INDEX  网络服务索引，取值 1-5，默认 1
#                      1=学校互联网服务, 2=联通互联网服务, 3=移动互联网服务,
#                      4=电信互联网服务, 5=校内免费服务
#   YZU_CHECK_URL      外网连通性检测地址，默认小米连通性检测接口：
#                      http://connect.rom.miui.com/generate_204
#                      亦可换成其它稳定返回 2xx 的地址（如 http://www.baidu.com）
ENV_USER_ID = "YZU_USER_ID"
ENV_PASSWORD = "YZU_PASSWORD"
ENV_INITIAL_URL = "YZU_INITIAL_URL"
ENV_SERVICE_INDEX = "YZU_SERVICE_INDEX"
ENV_CHECK_URL = "YZU_CHECK_URL"
DEFAULT_SERVICE_INDEX = 1
DEFAULT_CHECK_URL = "http://connect.rom.miui.com/generate_204"  # 小米连通性检测接口（返回 204 空响应）
CHECK_TIMEOUT = 5    # 单次连通性检测的超时时间（秒）
CHECK_INTERVAL = 10  # 外网连通性检测的时间间隔（秒）


def show_msg(msg: str, duration: int = 5):
    print(f"[通知] {msg}")


def load_config() -> tuple[str, str, int, str, str]:
    """从环境变量读取配置信息，缺失或非法时提示并退出。"""
    missing = [
        key
        for key in (ENV_USER_ID, ENV_PASSWORD, ENV_INITIAL_URL)
        if not os.environ.get(key, "").strip()
    ]
    if missing:
        show_msg(
            "以下必需的环境变量未设置：" + ", ".join(missing) + "。请先设置，再重新运行（详见 README）。"
        )
        sys.exit(1)

    user_id = os.environ[ENV_USER_ID].strip()
    password = os.environ[ENV_PASSWORD]
    initial_url = os.environ[ENV_INITIAL_URL].strip()

    if not initial_url.startswith(("http://", "https://")):
        show_msg(f"环境变量 {ENV_INITIAL_URL} 需要是以 http:// 或 https:// 开头的完整 URL。")
        sys.exit(1)

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

    return user_id, password, service_index, initial_url, check_url


def get_redirect_info(client: httpx.Client, initial_sso_url: str) -> tuple[str, str, str]:
    show_msg("正在解析认证服务器信息...", 2)

    parsed_url = urllib.parse.urlparse(initial_sso_url)
    query_params = urllib.parse.parse_qs(parsed_url.query)

    if 'service' not in query_params:
        raise ConnectionError("意外错误，请联系原作者github:https://github.com/GUMOUXUAN")

    new_url = query_params['service'][0]

    show_msg(f"正在获取参数desuwa...", 2)

    parsed_new_url = urllib.parse.urlparse(new_url)

    ip = parsed_new_url.netloc.split(':')[0]

    match_query = re.search(r"\?(.*)", new_url)

    if not ip or not match_query:
        raise ConnectionError(f"无法从解析出的 URL 中提取 IP 或 QueryString。当前URL: {new_url}")

    query_string = match_query.group(1)

    login_url = f"http://{ip}/eportal/InterFace.do?method=login"

    client.get(new_url, timeout=5)

    client.headers.update({"Referer": new_url})

    return login_url, ip, query_string


def check_online(client: httpx.Client, check_url: str) -> bool:
    """主动探测外网连通性：返回 2xx 视为在线（True）；超时、连接失败或被重定向（如被认证页劫持）视为断线（False）。"""
    try:
        res = client.get(check_url, timeout=CHECK_TIMEOUT, follow_redirects=False)
    except (httpx.HTTPError, httpx.InvalidURL):
        return False
    return 200 <= res.status_code < 300


def login_attempt(client: httpx.Client, user_id: str, password: str, service_index: int, initial_url: str):
    try:
        login_url, _, query_string = get_redirect_info(client, initial_url)

        show_msg("正在尝试登录...", 2)

        data = {
            "userId": user_id,
            "password": password,
            "service": SERVICE_LIST[service_index - 1],
            "queryString": query_string,
            "operatorPwd": "",
            "operatorUserId": "",
            "validcode": "",
            "passwordEncrypt": "",
        }

        res = client.post(login_url, data=data, timeout=10)

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
    user_id, password, service_index, initial_url, check_url = load_config()

    show_msg("启动了喵...困困困喵", 1)
    show_msg(f"将每隔 {CHECK_INTERVAL} 秒检查一次外网连通性，仅在连接异常时尝试重新登录。", 3)

    with httpx.Client(verify=False) as client:
        client.headers.update({
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Referrer-Policy": "strict-origin-when-cross-origin"
        })

        while True:
            # 主动检查外网连通性：正常时保持安静，仅在连接异常时尝试重新登录
            if not check_online(client, check_url):
                show_msg("检测到外网连接异常，正在尝试重新登录...", 3)
                login_attempt(client, user_id, password, service_index, initial_url)

            time.sleep(CHECK_INTERVAL)
