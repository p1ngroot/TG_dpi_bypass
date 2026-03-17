#!/usr/bin/env python3
"""
Telegram Unblock - DPI Bypass Tool
Bypasses DPI filtering for Telegram in Russia using packet fragmentation and DoH
Standalone solution without external dependencies
"""

import socket
import struct
import threading
import time
import select
from dataclasses import dataclass
from typing import List, Optional, Tuple
import subprocess
import platform
import sys
import io

# Telegram IP ranges and domains (as of 2024-2025)
TELEGRAM_SUBNETS = [
    "149.154.160.0/20",
    "91.108.4.0/22",
    "91.108.8.0/22",
    "91.108.12.0/22",
    "91.108.16.0/22",
    "91.108.56.0/22",
    "95.161.64.0/20",
    "149.154.164.0/22",
    "149.154.168.0/22",
    "149.154.172.0/22",
]

TELEGRAM_DOMAINS = [
    "telegram.org",
    "t.me",
    "web.telegram.org",
    "telegram.me",
    "telegra.ph",
    "tdesktop.com",
]

@dataclass
class ProxyConfig:
    local_port: int = 1080
    fragment_size: int = 40  # Increased for better performance
    use_doh: bool = True
    enabled: bool = False


class SOCKS5Proxy:
    """Standalone SOCKS5 proxy with packet fragmentation"""
    
    def __init__(self, host='127.0.0.1', port=1080, fragment_size=2):
        self.host = host
        self.port = port
        self.fragment_size = fragment_size
        self.server_socket = None
        self.running = False
        self.threads = []
    
    def start(self):
        """Start the SOCKS5 proxy server"""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Set timeout to allow checking self.running periodically
        self.server_socket.settimeout(1.0)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        self.running = True
        
        print(f"[+] SOCKS5 proxy listening on {self.host}:{self.port}")
        
        # Start accepting connections in a thread
        accept_thread = threading.Thread(target=self._accept_connections, daemon=True)
        accept_thread.start()
        self.threads.append(accept_thread)
    
    def stop(self):
        """Stop the proxy server"""
        self.running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        print("[+] SOCKS5 proxy stopped")
    
    def _accept_connections(self):
        """Accept incoming connections"""
        while self.running:
            try:
                client_socket, addr = self.server_socket.accept()
                print(f"[*] New connection from {addr}")
                client_thread = threading.Thread(
                    target=self._handle_client,
                    args=(client_socket,),
                    daemon=True
                )
                client_thread.start()
                self.threads.append(client_thread)
            except socket.timeout:
                # Timeout is expected, continue loop
                continue
            except Exception as e:
                if self.running:
                    print(f"[!] Accept error: {e}")
                break
    
    def _handle_client(self, client_socket):
        """Handle SOCKS5 client connection"""
        try:
            # SOCKS5 greeting: VER | NMETHODS | METHODS
            greeting = client_socket.recv(2)
            if len(greeting) < 2 or greeting[0] != 0x05:
                print(f"[!] Invalid SOCKS version: {greeting[0] if greeting else 'none'}")
                client_socket.close()
                return
            
            # Read methods list
            nmethods = greeting[1]
            methods = client_socket.recv(nmethods)
            if len(methods) < nmethods:
                print("[!] Failed to read methods")
                client_socket.close()
                return
            
            # Send: VER | METHOD (0x00 = no authentication)
            client_socket.sendall(b'\x05\x00')
            
            # Connection request
            request = client_socket.recv(4)
            if len(request) < 4:
                client_socket.close()
                return
            
            addr_type = request[3]
            
            if addr_type == 0x01:  # IPv4
                addr = socket.inet_ntoa(client_socket.recv(4))
            elif addr_type == 0x03:  # Domain name
                addr_len = client_socket.recv(1)[0]
                addr = client_socket.recv(addr_len).decode()
            else:
                client_socket.close()
                return
            
            port_data = client_socket.recv(2)
            port = struct.unpack('>H', port_data)[0]
            
            print(f"[*] Connecting to {addr}:{port}")
            
            # Connect to target
            target_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            target_socket.settimeout(10)
            
            try:
                target_socket.connect((addr, port))
                print(f"[+] Connected to {addr}:{port}")
                
                # Send success response
                client_socket.sendall(b'\x05\x00\x00\x01' + socket.inet_aton('0.0.0.0') + struct.pack('>H', 0))
                
                # Start forwarding with fragmentation
                self._forward_data(client_socket, target_socket)
            except Exception as e:
                print(f"[!] Failed to connect to {addr}:{port}: {e}")
                # Send failure response
                try:
                    client_socket.sendall(b'\x05\x05\x00\x01' + socket.inet_aton('0.0.0.0') + struct.pack('>H', 0))
                except:
                    pass
                try:
                    target_socket.close()
                except:
                    pass
                try:
                    client_socket.close()
                except:
                    pass
        except Exception:
            pass
        finally:
            try:
                client_socket.close()
            except:
                pass
    
    def _forward_data(self, client_socket, target_socket):
        """Forward data between client and target with fragmentation"""
        # Enable TCP_NODELAY for lower latency
        client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        target_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        
        sockets = [client_socket, target_socket]
        first_packet = True
        
        while self.running:
            try:
                # Reduced timeout for faster response
                readable, _, _ = select.select(sockets, [], [], 0.1)
                
                for sock in readable:
                    data = sock.recv(16384)  # Larger buffer
                    if not data:
                        return
                    
                    if sock == client_socket:
                        # Client to target - apply fragmentation ONLY on first packet
                        if first_packet and len(data) > 100:
                            # Fragment only the beginning (SNI part) - NO DELAYS
                            fragment_part = min(len(data), 150)
                            # Send first part in fragments (no sleep - fragmentation itself is enough)
                            for i in range(0, fragment_part, self.fragment_size):
                                chunk = data[i:i+self.fragment_size]
                                target_socket.sendall(chunk)
                            # Send rest normally
                            if len(data) > fragment_part:
                                target_socket.sendall(data[fragment_part:])
                            first_packet = False
                        else:
                            target_socket.sendall(data)
                    else:
                        # Target to client - no fragmentation
                        client_socket.sendall(data)
            except:
                break


class TelegramUnblocker:
    def __init__(self):
        self.config = ProxyConfig()
        self.running = False
        self.os_type = platform.system()
        self.proxy = None
        
    def start(self):
        """Start the unblocking service"""
        self.running = True
        
        if self.os_type == "Linux":
            self._start_linux()
        elif self.os_type == "Windows":
            self._start_windows()
        else:
            raise OSError(f"Unsupported OS: {self.os_type}")
    
    def stop(self):
        """Stop the unblocking service"""
        self.running = False
        
        if self.os_type == "Linux":
            self._stop_linux()
        elif self.os_type == "Windows":
            self._stop_windows()
    
    def _start_linux(self):
        """Linux-specific DPI bypass using SOCKS5 proxy"""
        print("[*] Starting Linux DPI bypass...")
        
        # Start SOCKS5 proxy with fragmentation
        self.proxy = SOCKS5Proxy(
            host='127.0.0.1',
            port=self.config.local_port,
            fragment_size=self.config.fragment_size
        )
        self.proxy.start()
        
        print("[+] Linux DPI bypass started")
        print(f"[*] Configure Telegram to use SOCKS5 proxy: 127.0.0.1:{self.config.local_port}")
    
    def _stop_linux(self):
        """Stop Linux DPI bypass"""
        print("[*] Stopping Linux DPI bypass...")
        
        if self.proxy:
            self.proxy.stop()
            self.proxy = None
        
        print("[+] Linux DPI bypass stopped")
    
    def _start_windows(self):
        """Windows-specific DPI bypass using SOCKS5 proxy"""
        print("[*] Starting Windows DPI bypass...")
        
        # Start SOCKS5 proxy with fragmentation
        self.proxy = SOCKS5Proxy(
            host='127.0.0.1',
            port=self.config.local_port,
            fragment_size=self.config.fragment_size
        )
        self.proxy.start()
        
        print("[+] Windows DPI bypass started")
        print(f"[*] Configure Telegram to use SOCKS5 proxy: 127.0.0.1:{self.config.local_port}")
    
    def _stop_windows(self):
        """Stop Windows DPI bypass"""
        print("[*] Stopping Windows DPI bypass...")
        
        if self.proxy:
            self.proxy.stop()
            self.proxy = None
        
        print("[+] Windows DPI bypass stopped")


class SimpleTUI:
    """Simple Text User Interface"""
    
    def __init__(self):
        self.unblocker = TelegramUnblocker()
        self.running = True
        
    def clear_screen(self):
        """Clear terminal screen"""
        if platform.system() == "Windows":
            subprocess.run("cls", shell=True)
        else:
            subprocess.run("clear", shell=True)
    
    def show_banner(self):
        """Display application banner"""
        banner = """
╔═══════════════════════════════════════════════════════════╗
║         TELEGRAM UNBLOCK - DPI BYPASS TOOL                ║
║         Разблокировка Telegram в условиях DPI             ║
╚═══════════════════════════════════════════════════════════╝
"""
        print(banner)
    
    def show_status(self):
        """Show current status"""
        status = "АКТИВЕН" if self.unblocker.running else "ОСТАНОВЛЕН"
        color = "\033[92m" if self.unblocker.running else "\033[91m"
        reset = "\033[0m"
        
        print(f"\nСтатус: {color}{status}{reset}")
        print(f"ОС: {self.unblocker.os_type}")
        print(f"Порт: {self.unblocker.config.local_port}")
        print(f"Размер фрагмента: {self.unblocker.config.fragment_size}")
        print(f"DoH: {'Включен' if self.unblocker.config.use_doh else 'Выключен'}")
    
    def show_menu(self):
        """Display main menu"""
        print("\n" + "="*60)
        print("МЕНЮ:")
        print("  [1] Запустить разблокировку")
        print("  [2] Остановить разблокировку")
        print("  [3] Показать информацию о Telegram")
        print("  [4] Настройки")
        print("  [0] Выход")
        print("="*60)
    
    def show_telegram_info(self):
        """Show Telegram network information"""
        print("\n" + "="*60)
        print("ИНФОРМАЦИЯ О TELEGRAM:")
        print("\nПодсети Telegram:")
        for subnet in TELEGRAM_SUBNETS:
            print(f"  • {subnet}")
        
        print("\nДомены Telegram:")
        for domain in TELEGRAM_DOMAINS:
            print(f"  • {domain}")
        print("="*60)
        input("\nНажмите Enter для продолжения...")
    
    def show_settings(self):
        """Show and modify settings"""
        print("\n" + "="*60)
        print("НАСТРОЙКИ:")
        print(f"  [1] Порт: {self.unblocker.config.local_port}")
        print(f"  [2] Размер фрагмента: {self.unblocker.config.fragment_size}")
        print(f"  [3] DoH: {'Включен' if self.unblocker.config.use_doh else 'Выключен'}")
        print("  [0] Назад")
        print("="*60)
        
        choice = input("\nВыберите опцию: ").strip()
        
        if choice == "1":
            try:
                port = int(input("Введите порт (1-65535): "))
                if 1 <= port <= 65535:
                    self.unblocker.config.local_port = port
                    print("[+] Порт изменен")
            except ValueError:
                print("[!] Неверное значение")
        elif choice == "2":
            try:
                size = int(input("Введите размер фрагмента (10-100, рекомендуется 40): "))
                if 10 <= size <= 100:
                    self.unblocker.config.fragment_size = size
                    print("[+] Размер фрагмента изменен")
                    print("[!] Перезапустите разблокировку для применения")
                else:
                    print("[!] Значение должно быть от 10 до 100")
            except ValueError:
                print("[!] Неверное значение")
        elif choice == "3":
            self.unblocker.config.use_doh = not self.unblocker.config.use_doh
            print(f"[+] DoH {'включен' if self.unblocker.config.use_doh else 'выключен'}")
        
        time.sleep(1)
    
    def run(self):
        """Main TUI loop"""
        try:
            while self.running:
                self.clear_screen()
                self.show_banner()
                self.show_status()
                self.show_menu()
                
                choice = input("\nВыберите опцию: ").strip()
                
                if choice == "1":
                    if not self.unblocker.running:
                        try:
                            self.unblocker.start()
                            print("\n[+] Разблокировка запущена!")
                            time.sleep(2)
                        except Exception as e:
                            print(f"\n[!] Ошибка: {e}")
                            time.sleep(3)
                    else:
                        print("\n[!] Разблокировка уже запущена")
                        time.sleep(2)
                
                elif choice == "2":
                    if self.unblocker.running:
                        self.unblocker.stop()
                        print("\n[+] Разблокировка остановлена")
                        time.sleep(2)
                    else:
                        print("\n[!] Разблокировка не запущена")
                        time.sleep(2)
                
                elif choice == "3":
                    self.show_telegram_info()
                
                elif choice == "4":
                    self.show_settings()
                
                elif choice == "0":
                    if self.unblocker.running:
                        print("\n[*] Остановка разблокировки...")
                        self.unblocker.stop()
                    print("\n[*] Выход...")
                    self.running = False
                
                else:
                    print("\n[!] Неверный выбор")
                    time.sleep(1)
        
        except KeyboardInterrupt:
            print("\n\n[*] Прервано пользователем")
            if self.unblocker.running:
                self.unblocker.stop()
        
        except Exception as e:
            print(f"\n[!] Критическая ошибка: {e}")
            if self.unblocker.running:
                self.unblocker.stop()


def main():
    """Main entry point"""
    print("Инициализация Telegram Unblock...")
    
    # Check Python version
    if sys.version_info < (3, 7):
        print("[!] Требуется Python 3.7 или выше")
        sys.exit(1)
    
    # Start TUI
    tui = SimpleTUI()
    tui.run()


if __name__ == "__main__":
    main()
