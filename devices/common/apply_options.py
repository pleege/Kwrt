#!/usr/bin/env python3
"""把页面提交的编译参数落到 openwrt 源码树。

用法（在 openwrt/ 目录下运行）:
  apply_options.py apply    读 $OPTIONS_JSON，校验后追加 .config 并生成 files/etc/uci-defaults/zz-user-options
  apply_options.py verify   在 make defconfig 之后运行，确认请求的包真的被选中（缺失则失败，避免白编几小时）

所有取值都按 docs/catalog.json 白名单校验；不接受任何密码类参数。
"""
import ipaddress
import json
import os
import re
import sys
from pathlib import Path

WORKSPACE = Path(os.environ.get("GITHUB_WORKSPACE", "."))
CATALOG = json.loads((WORKSPACE / "docs/catalog.json").read_text())
STATE = Path(".user-options.packages")
UCI = Path("files/etc/uci-defaults/zz-user-options")

HOST_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9-]{0,30}[A-Za-z0-9])?$")


def die(msg):
    print(f"::error::{msg}")
    sys.exit(1)


def load_options():
    raw = os.environ.get("OPTIONS_JSON", "").strip()
    if not raw or raw == "null":
        return {}
    try:
        o = json.loads(raw)
    except json.JSONDecodeError as e:
        die(f"OPTIONS_JSON 不是合法 JSON: {e}")
    if not isinstance(o, dict):
        die("OPTIONS_JSON 必须是对象")
    return o


def allowed_packages():
    items = {}
    for g in CATALOG["groups"]:
        for it in g["items"]:
            items[it["id"]] = it.get("requires", [])
    return items


def apply():
    o = load_options()
    if not o:
        print("未提供自定义参数，跳过")
        return
    d = CATALOG["defaults"]
    unknown = set(o) - {"packages", "theme", "hostname", "lan_ip", "netmask", "ipv6", "partsize", "kernel_wireguard"}
    if unknown:
        die(f"不认识的参数: {sorted(unknown)}")

    cfg = []
    wanted = []  # 需要在 defconfig 后确认被选中的包

    # ---- 软件包 ----
    allowed = allowed_packages()
    pkgs = o.get("packages", [])
    if not isinstance(pkgs, list) or not all(isinstance(p, str) for p in pkgs):
        die("packages 必须是字符串数组")
    for p in pkgs:
        if p not in allowed:
            die(f"软件包不在白名单内: {p!r}")
    for p in dict.fromkeys(pkgs):
        for q in [p, *allowed[p]]:
            cfg.append(f"CONFIG_PACKAGE_{q}=y")
            wanted.append(q)

    # ---- 主题 ----
    theme_id = o.get("theme", d["theme"])
    themes = {t["id"]: t for t in CATALOG["themes"]}
    if theme_id not in themes:
        die(f"不支持的主题: {theme_id!r}")
    cfg.append(f"CONFIG_PACKAGE_{theme_id}=y")
    wanted.append(theme_id)
    theme_path = themes[theme_id]["path"]

    # ---- 内核态 WireGuard ----
    if o.get("kernel_wireguard", d["kernel_wireguard"]) is True:
        for q in ("kmod-wireguard", "wireguard-tools", "luci-proto-wireguard"):
            cfg.append(f"CONFIG_PACKAGE_{q}=y")
            wanted.append(q)

    # ---- 分区大小 ----
    size = o.get("partsize", d["partsize"])
    lim = CATALOG["partsize"]
    if not isinstance(size, int) or isinstance(size, bool) or not lim["min"] <= size <= lim["max"]:
        die(f"partsize 须为 {lim['min']}~{lim['max']} 的整数")
    cfg.append(f"CONFIG_TARGET_ROOTFS_PARTSIZE={size}")

    # ---- 网络与系统（写入首次启动脚本）----
    hostname = o.get("hostname", d["hostname"])
    if not isinstance(hostname, str) or not HOST_RE.match(hostname):
        die("hostname 只允许字母、数字、连字符，且不能以连字符开头或结尾")
    lan_ip = o.get("lan_ip", d["lan_ip"])
    netmask = o.get("netmask", d["netmask"])
    if netmask not in CATALOG["netmasks"]:
        die(f"不支持的子网掩码: {netmask!r}")
    try:
        ip = ipaddress.IPv4Address(lan_ip)
        net = ipaddress.IPv4Network(f"{lan_ip}/{netmask}", strict=False)
    except (ipaddress.AddressValueError, ValueError, TypeError):
        die(f"LAN IP 不合法: {lan_ip!r}")
    if ip in (net.network_address, net.broadcast_address) or ip.is_loopback or ip.is_multicast or ip.is_link_local:
        die(f"LAN IP 不能是网络地址/广播/回环/组播/链路本地: {lan_ip}")
    ipv6 = o.get("ipv6", d["ipv6"])
    if not isinstance(ipv6, bool):
        die("ipv6 必须是 true/false")

    lines = [
        "#!/bin/sh",
        "# 由 apply_options.py 生成：页面提交的非敏感参数",
        f"uci set network.lan.ipaddr='{lan_ip}'",
        f"uci set network.lan.netmask='{netmask}'",
        f"uci set system.@system[0].hostname='{hostname}'",
        f"uci set luci.main.mediaurlbase='/luci-static/{theme_path}'",
    ]
    if not ipv6:
        lines += [
            "uci -q delete network.globals.ula_prefix",
            "uci -q delete network.wan6",
            "uci -q set dhcp.lan.ra='disabled'",
            "uci -q set dhcp.lan.dhcpv6='disabled'",
            "uci -q set dhcp.lan.ndp='disabled'",
        ]
    lines += ["uci commit network", "uci commit system", "uci commit luci", "uci commit dhcp", "exit 0", ""]
    UCI.parent.mkdir(parents=True, exist_ok=True)
    UCI.write_text("\n".join(lines))
    UCI.chmod(0o755)

    with open(".config", "a") as f:
        f.write("\n# ===== 页面提交的自定义参数 =====\n" + "\n".join(cfg) + "\n")
    STATE.write_text("\n".join(dict.fromkeys(wanted)) + "\n")
    print(f"已应用: 软件包 {len(set(wanted))} 个, 主题 {theme_id}, LAN {lan_ip}/{netmask}, "
          f"主机名 {hostname}, IPv6 {'开' if ipv6 else '关'}, 分区 {size}MB")


def verify():
    if not STATE.exists():
        print("无自定义参数，跳过核对")
        return
    final = Path(".config").read_text()
    missing = [p for p in STATE.read_text().split() if not re.search(rf"^CONFIG_PACKAGE_{re.escape(p)}=[ym]$", final, re.M)]
    if missing:
        die("以下软件包 defconfig 后未被选中（包不存在或依赖不满足）: " + ", ".join(missing))
    print("核对通过：所请求的软件包均已选中")


if __name__ == "__main__":
    {"apply": apply, "verify": verify}.get(sys.argv[1] if len(sys.argv) > 1 else "", lambda: die("用法: apply|verify"))()
