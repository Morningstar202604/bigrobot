# 手机远程控制

BigRobot 的手机远控参考了 [ZCode Remote Control](https://zcode.z.ai/cn/docs/remote-control) 的边界：桌面端生成二维码/链接，手机接入的是**整个控制台**，不是只读截图；命令、文件、浏览器仍在这台机器上执行。

## 怎么用

1. 电脑左侧栏点「远程控制」。
2. 选连接方式：
   - **自动**：有 `BIGROBOT_PUBLIC_URL` 用该域名；否则尝试 localhost.run 公网隧道；失败回退局域网直连。
   - **仅直连**：使用 `BIGROBOT_PUBLIC_URL`、反向代理 Host 或本机局域网 IP。
   - **强制公网隧道**：只走 localhost.run，失败直接报错。
3. 点「生成连接二维码」，手机扫码或复制链接打开。
4. 配对成功后手机进入完整控制台。关弹窗不会断开，必须点「停止远控」。

## 安全模型

- 二维码链接里是 **一次性配对串**，放在 URL fragment（`/remote#t=...`），不会进服务端访问日志或 Referer；5 分钟有效，用一次即焚。
- 配对成功换成 12 小时临时令牌；令牌等价管理员权限，只保存在手机浏览器 localStorage。
- 同一时间只允许一台手机；重新生成二维码或刷新会立即踢掉旧手机。
- 「停止远控」清空配对串和所有临时令牌，旧手机下一次请求就是 401。
- 链接就是临时钥匙，不要发群、不要公开。怀疑泄露就点刷新。
- 公网隧道由 localhost.run 终止 TLS，该服务能看到经过它的 HTTP 内容；只建议临时用。长期使用请配自己的域名 + HTTPS 反代，并设置 `BIGROBOT_PUBLIC_URL`。

## 服务端接口

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| `POST` | `/api/remote/start` | 管理员 | 生成新配对串；同时吊销旧手机 |
| `GET` | `/api/remote/status` | 管理员 | 等待扫码 / 已连接手机 / 隧道状态 |
| `POST` | `/api/remote/pair` | 公开（凭一次性串） | 换临时令牌 |
| `POST` | `/api/remote/stop` | 管理员 | 停止远控，吊销全部令牌 |

临时令牌通过 `X-Admin-Token` 使用，和本机 `ADMIN_TOKEN` 走同一套管理接口。

## 环境变量

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `BIGROBOT_PUBLIC_URL` | 空 | 对外域名，例如 `https://robot.example.com`；设置后自动模式不再开隧道 |
| `BIGROBOT_REMOTE_TUNNEL` | `1` | 设为 `0` 禁止 localhost.run |
| `BIGROBOT_REMOTE_SCHEME` | `http` | 直连链接协议；反代 HTTPS 时设为 `https` |

## 已知限制

- 临时令牌保存在进程内存，程序重启后手机需要重新扫码。
- localhost.run 免费域名会轮换，长任务建议用自己的域名或内网穿透。
- 手机端仍运行同一套 React 控制台，窄屏下部分表格会横向滚动，不是原生 App。
