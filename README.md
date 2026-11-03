# 本机短信查询

给本机 agent 用的 skill。它从合宙 Air780 收到的短信库里取出原文；用哪一条、取验证码还是别的字段，由调用方自己看正文决定。

## 设备

- 模块：合宙 Air780EHM
- 固件：LuatOS-SoC V2030
- 板端脚本：`uart_sms_forwarder/main.lua`，版本 `1.1.0-volte-rndis`
- 连接：USB 虚拟串口。这台电脑当前配置是 COM5，以 `config.yaml` 的 `Serial.Port` 为准

模块把 JSON 包在 `SMS_START:` 和 `:SMS_END` 之间，从 USB 串口发出。

## 实现

上位机是 [uart_sms_forwarder](https://github.com/dushixiang/uart_sms_forwarder) 的 Windows 构建：

`E:\re_sms\dist\uart_sms_forwarder-windows-amd64\uart_sms_forwarder.exe`

短信写入 sqlite `data\app.db` 的 `text_messages`。网页只监听 `127.0.0.1:8080`，查询脚本不登录网页。

旁边的 `uart_sms_forwarder-windows-amd64-dito` 是停更旧副本，不作为查询源。

## 查询

```powershell
python scripts\query_sms.py
python scripts\query_sms.py --within 15
python scripts\query_sms.py --query 验证码
python scripts\query_sms.py --wait 90 --fresh
```

默认返回最新 20 条入站短信。`--query` 只做调用方给定的正文过滤，脚本里没有省份或平台名单。

例如浙江短信里常见「浙里办」「浙江政务服务网」，国家医保常见「国家医保局」「国家医疗保障局」。这只是例子，实际还可能是其他省或其他业务，调用方看原文判断。

退出码：`0` 有结果，`2` 窗口内没有，`1` 参数或数据库错误。

换电脑时把 `config.example.json` 复制为 `config.local.json`，或设置 `SMS_DB`。不要提交短信库、串口日志和上位机 `config.yaml`。

## 测试

```powershell
python -m unittest tests.test_query_sms
```

测试使用临时库和虚构短信，不读取真实短信。
