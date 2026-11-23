#!/bin/bash

SHELL_FOLDER=$(dirname $(readlink -f "$0"))

#bash $SHELL_FOLDER/../common/kernel_6.6.sh

git_clone_path master https://github.com/coolsnowwolf/lede target/linux/x86/files target/linux/x86/patches-6.12

wget -N https://raw.githubusercontent.com/coolsnowwolf/lede/master/target/linux/x86/base-files/etc/board.d/02_network -P target/linux/x86/base-files/etc/board.d/
wget -N https://github.com/coolsnowwolf/lede/raw/refs/heads/master/target/linux/x86/Makefile -P target/linux/x86/
sed -i -e "s/ autocore-x86//" \
	   -e "s/kmod-usb-net-rtl8152-vendor/kmod-usb-net-rtl8152/" \
	   -e "s/kmod-usb-audio/kmod-usb-audio luci-app-diskman/" \
	   -e "/=7.3/d" \
	   -e "s/6.18/6.12/" target/linux/x86/Makefile

sed -i 's/kmod-r8169/kmod-r8168/' target/linux/x86/image/64.mk

sed -i 's/256/1024/g' target/linux/x86/image/Makefile

# op-packages 的 dockerd 包 Makefile 与 files/ 目录不同步（2026-11-23 编译实测报错）：
# Makefile 要安装 16_docker-netifd-migrate2，目录里只有 16_docker-netifd-migrate。
# 上游修复后文件会存在，此处自动跳过。
_ud=feeds/kiddin9/dockerd/files/etc/uci-defaults
if [ -d "$_ud" ] && [ ! -f "$_ud/16_docker-netifd-migrate2" ] && [ -f "$_ud/16_docker-netifd-migrate" ]; then
  cp "$_ud/16_docker-netifd-migrate" "$_ud/16_docker-netifd-migrate2"
  echo "dockerd: 已补 16_docker-netifd-migrate2"
fi
