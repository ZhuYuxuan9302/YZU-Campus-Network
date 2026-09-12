## Better-YZU-Campus-Network-扬州大学校园网自动登录脚本

* 这是一个用于实现扬州大学校园网自动登录和断线重连的 Python 脚本。断线时会从网关拦截页动态获取实时认证入口，模拟 POST 请求完成认证。
* 本脚本仅是一个.py文件，且大量使用AI-Coding，使用上可能不是那么方便，之后应该会发布适用于windows或者macos的单文件版本。
* 欢迎各位批评指导
* 晚安！


-----

### 1\. 功能概述

  * **自动登录：** 无需手动操作，自动完成校园网认证。
  * **断线重连：** 每隔 10 秒主动检测一次外网连通性（默认使用小米官方检测接口），仅在连接异常时才尝试重新登录，确保网络持续在线。
  * **详细日志：** 检测与登录全过程均打印带时间戳的日志，方便随时排障。
  * **配置外置：** 账号、密码、服务、检测地址等均可通过环境变量导入或覆盖，无需修改源码。
  * **单文件发行：** 可通过 PyInstaller 打包成独立的可执行文件（`.exe`）。

### 2\. 环境要求

#### 依赖库安装

本脚本依赖 `httpx` 库。请在命令行中安装：

```bash
pip install httpx
```

#### 配置环境变量（必需）

在使用前，请通过环境变量导入以下信息（无需修改源码）：

| 环境变量 | 描述 | 必填 |
| :--- | :--- | :--- |
| **`YZU_USER_ID`** | 您的学号或用户名。 | 是 |
| **`YZU_PASSWORD`** | 您的校园网密码。 | 是 |
| **`YZU_SERVICE_INDEX`** | 选择的网络服务，取值为 **1 到 5** 之间的整数，默认 `1`。 | 否 |
| **`YZU_CHECK_URL`** | 外网连通性检测地址，默认小米官方接口 `http://connect.rom.miui.com/generate_204`。 | 否 |

> **`YZU_SERVICE_INDEX`** 对应服务：`1: 学校互联网, 2: 联通, 3: 移动, 4: 电信, 5: 校内免费`。

> **关于 `YZU_CHECK_URL`（外网连通性检测）：** 脚本每隔 10 秒请求一次检测地址来判断外网是否可达：返回 **204** 视为在线（跳过登录）；其它状态（包括被认证页劫持返回的 200 / 302 页面）、超时、连接失败均视为断线，才会触发重新登录。默认使用小米官方连通性检测接口；如需更换，请使用能稳定返回 204 空响应的检测地址。

**Windows（PowerShell）示例：**

```powershell
# 临时设置（仅对当前窗口有效）
$env:YZU_USER_ID = "你的学工号"
$env:YZU_PASSWORD = "你的密码"
$env:YZU_SERVICE_INDEX = "4"

python main.py
```

*如需永久保存，可对每个变量执行一次 `[Environment]::SetEnvironmentVariable("YZU_USER_ID", "你的学工号", "User")`，重开终端后生效。*

**macOS / Linux 示例：**

```bash
export YZU_USER_ID="你的学工号"
export YZU_PASSWORD="你的密码"
export YZU_SERVICE_INDEX="4"

python3 main.py
```

-----

### 3\. 使用方法

#### 方法一：直接运行脚本

在命令行中导航到脚本所在目录，使用 Python 解释器运行：

```bash
python main.py
```

#### 方法二：打包为独立软件 (PyInstaller)

1.  **安装 PyInstaller：** `pip install pyinstaller`
2.  **执行打包命令：**
    ```bash
    pyinstaller --onefile main.py
    ```
    *若需隐藏命令行窗口在后台运行，请使用：`pyinstaller --onefile --noconsole main.py`*
3.  打包完成后，在 **`dist`** 文件夹中找到生成的可执行文件（`main.exe`）运行。

#### 方法三：使用 Docker（适用于服务器 / NAS 等长期运行场景）

镜像由 GitHub Actions 自动构建并发布至 GHCR，无需在本地安装 Python：

```bash
docker run -d \
  --name yzu-campus-network \
  --restart unless-stopped \
  -e YZU_USER_ID="你的学工号" \
  -e YZU_PASSWORD="你的密码" \
  -e YZU_SERVICE_INDEX="4" \
  ghcr.io/<owner>/<repo>:latest
```

> 提示：`<owner>` 与 `<repo>` 均为小写，分别对应 GitHub 用户名与仓库名（例如 `GUMOUXUAN/YZU-Campus-Network` → `ghcr.io/gumouxuan/yzu-campus-network`）。首次发布后，可在仓库的 **Packages** 页面将镜像可见性设为 Public。

查看运行日志：

```bash
docker logs -f yzu-campus-network
```

*也可以手动构建本地镜像：`docker build -t yzu-campus-network .`*

-----

### 4\. 故障排除

  * **`ModuleNotFoundError`：** 缺少依赖库。请运行 `pip install httpx`。
  * **登录失败：** 请检查 **`YZU_USER_ID`** 和 **`YZU_PASSWORD`** 环境变量是否准确无误。
  * **提示缺少环境变量：** 按上文「配置环境变量」一节设置对应变量后重新运行。
  * **误判导致频繁重登：** 若连通性检测地址不可用，可能将在线状态误判为离线；可通过 `YZU_CHECK_URL` 更换为其它能稳定返回 204 的检测地址。
  * **服务器响应格式错误：** 脚本在断网或半连接状态下可能无法获得标准的 JSON 响应。脚本已添加错误处理，会自动重试。
  * **其他错误：** 可以带着截图联系我，虽然我可能也解决不了
