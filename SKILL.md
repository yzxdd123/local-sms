---
name: local-sms
description: 读取本机合宙 Air780 收到的短信原文并交给当前 agent。agent 自己判断要用哪一条、取验证码还是别的内容。需要本机短信、验证码或 OTP 时使用。只读 sqlite，不发送短信。
---

# 本机短信

本机 SIM 插在合宙 Air780 上。短信进入本地 sqlite 后，用本目录脚本把原文交给当前 agent。脚本不做平台分类，也不决定哪一条有用。

## 何时使用

当前任务需要这张卡刚收到的短信时使用，例如登录验证码、注册码、通知原文。脚本不区分来源，由 agent 看正文决定。

不要用这个 skill 发短信，也不要读取 `properties`、网页后台或串口日志。那里有通知密钥和登录配置。

## 设备与链路

1. 模块是合宙 Air780EHM，固件 LuatOS-SoC V2030。板端脚本 `E:\re_sms\uart_sms_forwarder\main.lua`（版本 `1.1.0-volte-rndis`）把短信打成 `SMS_START:{json}:SMS_END`，从 USB 虚拟串口送出。
2. Windows 上位机是 [uart_sms_forwarder](https://github.com/dushixiang/uart_sms_forwarder)，目录 `E:\re_sms\dist\uart_sms_forwarder-windows-amd64\`。`uart_sms_forwarder.exe` 按 `config.yaml` 的 `Serial.Port`（当前 COM5）收短信，写入 `data\app.db` 的 `text_messages`，网页在 `127.0.0.1:8080`。
3. 本 skill 只读 `text_messages`。

`uart_sms_forwarder-windows-amd64-dito` 是停更旧副本，不要查。新短信依赖上位机进程还在运行。

## 命令

```powershell
python scripts\query_sms.py
python scripts\query_sms.py --within 15
python scripts\query_sms.py --recent 50
python scripts\query_sms.py --query 验证码
python scripts\query_sms.py --wait 90 --fresh
python scripts\query_sms.py --status
```

默认返回最新 20 条入站短信的原文。`--query` 只是调用方自己给出的正文子串，脚本不内置省份或平台名单。`--within` 的单位是分钟，`0` 表示不限时间。`--wait 90 --fresh` 在刚触发发送后使用，只返回这条命令启动之后写入的短信。

退出码 `0` 有短信，`2` 这个窗口里没有，`1` 是参数或数据库错误。数据库打不开时先跑 `--status`。

路径顺序：`--db`、环境变量 `SMS_DB`、`config.local.json`、脚本里的本机默认库。`config.local.json` 不要提交。

## 交给 agent 判断

读 `messages[].content`、`created_at` 和 `from`，自己决定：

- 哪一条对应当前这次操作
- 要用正文里的哪一段
- 时间是否还对得上页面提示的有效期

没有对得上的短信就说没有，不要编。验证码字样和位数以短信原文为准。不要把查询结果写进仓库、日志或 webhook。

## 虚构例子

下面的平台和正文都是编的，只演示怎么读原文。真实短信的名称和句子不会一样，技能里也不列举真实来源。

- `【星港通行证】您正在登录，验证码为：482913，5分钟内有效。`
- `【北桥办事】本次操作所需的验证码为：730261。有效时间5分钟。`
- `【云页通知】您的预约已确认，无需回复。`

如果当前要完成星港通行证登录，只用第一条里的 `482913`。北桥办事和云页通知即使同时在结果里，也不要拿。时间对不上页面提示，就当没有。
