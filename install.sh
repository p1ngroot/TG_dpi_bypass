#!/bin/bash
# Telegram Unblock - Installation Script for Linux

set -e

echo "=================================="
echo "Telegram Unblock - Установка"
echo "=================================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "[!] Пожалуйста, запустите с правами root (sudo)"
    exit 1
fi

# Check Python version
echo "[*] Проверка Python..."
if ! command -v python3 &> /dev/null; then
    echo "[!] Python 3 не найден. Установите Python 3.7+"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
echo "[+] Python $PYTHON_VERSION найден"

# Check iptables
echo "[*] Проверка iptables..."
if ! command -v iptables &> /dev/null; then
    echo "[!] iptables не найден. Установите iptables"
    exit 1
fi
echo "[+] iptables найден"

# Check ip command
echo "[*] Проверка iproute2..."
if ! command -v ip &> /dev/null; then
    echo "[!] ip команда не найдена. Установите iproute2"
    exit 1
fi
echo "[+] iproute2 найден"

# Make script executable
echo "[*] Настройка прав доступа..."
chmod +x telegram_unblock.py

# Create symlink (optional)
read -p "Создать символическую ссылку в /usr/local/bin? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    ln -sf "$(pwd)/telegram_unblock.py" /usr/local/bin/telegram-unblock
    echo "[+] Символическая ссылка создана: /usr/local/bin/telegram-unblock"
fi

echo ""
echo "=================================="
echo "[+] Установка завершена!"
echo "=================================="
echo ""
echo "Запуск:"
echo "  sudo python3 telegram_unblock.py"
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "  или: sudo telegram-unblock"
fi
echo ""
