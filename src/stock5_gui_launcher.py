# -*- coding: utf-8 -*-
"""
stock5_gui_launcher.py - Stock5 GUI启动器（优化布局版本）
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import subprocess
import sys
import threading
import time
from pathlib import Path
import socket
import psutil
import os

import pathlib

# 使用相对路径
PROJECT_DIR = pathlib.Path(__file__).parent.absolute()

PROJECT_DIR = Path(__file__).parent.absolute()
FACTOR_RUNNER = PROJECT_DIR / "llm_factors" / "factor_runner.py"
FACTOR_PID_FILE = PROJECT_DIR / "factor_collection.pid"
FACTOR_LOG = PROJECT_DIR / "logs" / "factor_collection.log"
EM_FETCHER = PROJECT_DIR / "em_fetcher_daemon.py"
EM_PID_FILE = PROJECT_DIR / "em_fetcher.pid"
EM_LOG = PROJECT_DIR / "logs" / "em_fetcher.log"

class ModernButton(tk.Canvas):
    """现代化按钮（带圆角和渐变效果）"""
    def __init__(self, parent, text, command, bg_color="#1e3a8a", hover_color="#3b82f6", **kwargs):
        super().__init__(parent, width=120, height=35, bg=bg_color, highlightthickness=0, **kwargs)
        self.text = text
        self.command = command
        self.bg_color = bg_color
        self.hover_color = hover_color
        self.default_color = bg_color
        
        self.draw_button()
        self.bind("<Enter>", self.on_enter)
        self.bind("<Leave>", self.on_leave)
        self.bind("<Button-1>", self.on_click)
    
    def draw_button(self, color=None):
        if color is None:
            color = self.bg_color
        self.delete("all")
        self.create_rounded_rect(3, 3, 117, 32, radius=6, fill=color, outline="")
        self.create_text(60, 17, text=self.text, fill="white", font=("微软雅黑", 9, "bold"))
    
    def create_rounded_rect(self, x1, y1, x2, y2, radius=6, **kwargs):
        points = [x1+radius, y1, x2-radius, y1, x2, y1, x2, y1+radius, x2, y2-radius, x2, y2, x2-radius, y2, x1+radius, y2, x1, y2, x1, y2-radius, x1, y1+radius, x1, y1]
        return self.create_polygon(points, smooth=True, **kwargs)
    
    def on_enter(self, event):
        self.draw_button(self.hover_color)
    
    def on_leave(self, event):
        self.draw_button(self.default_color)
    
    def on_click(self, event):
        if self.command:
            self.command()

class Stock5LauncherGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Stock5 - 智能数据分析平台")
        self.root.geometry("850x700")  # 增加高度
        
        self.colors = {
            'bg_main': '#0f172a',
            'bg_secondary': '#1e293b',
            'bg_card': '#334155',
            'accent': '#3b82f6',
            'accent_hover': '#60a5fa',
            'success': '#10b981',
            'danger': '#ef4444',
            'text_primary': '#f8fafc',
            'text_secondary': '#cbd5e1',
        }
        
        # 看门狗状态
        self.watchdog_enabled = True
        self.watchdog_notified = {}  # 服务名 -> 是否已发送过"挂了"通知，避免刷屏
        self.startup_done = False    # 首次启动是否完成
        
        # EM 东方财富采集器状态
        self.em_pid = None
        self.em_running = False
        
        self.root.configure(bg=self.colors['bg_main'])
        self.setup_styles()
        self.create_widgets()
        self.check_status()
        self.auto_refresh()
    
    def setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
    
    def create_widgets(self):
        main_frame = tk.Frame(self.root, bg=self.colors['bg_main'])
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # 标题（紧凑）
        title_frame = tk.Frame(main_frame, bg=self.colors['bg_main'])
        title_frame.pack(fill=tk.X, pady=(0, 8))
        
        tk.Label(title_frame, text="⚡ Stock5", bg=self.colors['bg_main'], fg=self.colors['accent'], 
                font=("微软雅黑", 20, "bold")).pack(side=tk.LEFT)
        tk.Label(title_frame, text="智能数据分析平台", bg=self.colors['bg_main'], fg=self.colors['text_secondary'], 
                font=("微软雅黑", 11)).pack(side=tk.LEFT, padx=(8, 0), pady=(5, 0))
        
        # 分隔线（细）
        tk.Frame(main_frame, height=1, bg=self.colors['accent']).pack(fill=tk.X, pady=(0, 10))
        
        # 服务状态（紧凑）
        status_frame = tk.Frame(main_frame, bg=self.colors['bg_card'])
        status_frame.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(status_frame, text="📊 服务状态", bg=self.colors['bg_card'], fg=self.colors['accent'],
                font=("微软雅黑", 11, "bold")).pack(anchor=tk.W, padx=12, pady=(10, 6))
        
        # Web状态
        web_frame = tk.Frame(status_frame, bg=self.colors['bg_card'])
        web_frame.pack(fill=tk.X, padx=12, pady=3)
        tk.Label(web_frame, text="🌐", bg=self.colors['bg_card'], fg=self.colors['accent'], 
                font=("Segoe UI Emoji", 12)).pack(side=tk.LEFT)
        self.web_status_label = tk.Label(web_frame, text="Web服务器: 检查中...", bg=self.colors['bg_card'],
                                         fg=self.colors['text_primary'], font=("微软雅黑", 11))
        self.web_status_label.pack(side=tk.LEFT, padx=(8, 0))
        self.web_pid_label = tk.Label(web_frame, text="PID: N/A", bg=self.colors['bg_card'],
                                      fg=self.colors['text_secondary'], font=("微软雅黑", 9))
        self.web_pid_label.pack(side=tk.RIGHT)
        
        # 数据采集
        collect_frame = tk.Frame(status_frame, bg=self.colors['bg_card'])
        collect_frame.pack(fill=tk.X, padx=12, pady=3)
        tk.Label(collect_frame, text="🔄", bg=self.colors['bg_card'], fg=self.colors['accent'],
                font=("Segoe UI Emoji", 12)).pack(side=tk.LEFT)
        self.collect_status_label = tk.Label(collect_frame, text="数据采集: 检查中...", bg=self.colors['bg_card'],
                                             fg=self.colors['text_primary'], font=("微软雅黑", 11))
        self.collect_status_label.pack(side=tk.LEFT, padx=(8, 0))
        self.collect_pid_label = tk.Label(collect_frame, text="PID: N/A", bg=self.colors['bg_card'],
                                          fg=self.colors['text_secondary'], font=("微软雅黑", 9))
        self.collect_pid_label.pack(side=tk.RIGHT)
        
        # 数据库
        db_frame = tk.Frame(status_frame, bg=self.colors['bg_card'])
        db_frame.pack(fill=tk.X, padx=12, pady=3)
        tk.Label(db_frame, text="💾", bg=self.colors['bg_card'], fg=self.colors['accent'],
                font=("Segoe UI Emoji", 12)).pack(side=tk.LEFT)
        self.db_status_label = tk.Label(db_frame, text="数据库: N/A", bg=self.colors['bg_card'],
                                        fg=self.colors['text_primary'], font=("微软雅黑", 11))
        self.db_status_label.pack(side=tk.LEFT, padx=(8, 0))
        
        # 因子采集
        factor_frame = tk.Frame(status_frame, bg=self.colors['bg_card'])
        factor_frame.pack(fill=tk.X, padx=12, pady=3)
        tk.Label(factor_frame, text="📊", bg=self.colors['bg_card'], fg=self.colors['accent'],
                font=("Segoe UI Emoji", 12)).pack(side=tk.LEFT)
        self.factor_status_label = tk.Label(factor_frame, text="因子采集: 检查中...", bg=self.colors['bg_card'],
                                            fg=self.colors['text_primary'], font=("微软雅黑", 11))
        self.factor_status_label.pack(side=tk.LEFT, padx=(8, 0))
        self.factor_mode_label = tk.Label(factor_frame, text="", bg=self.colors['bg_card'],
                                          fg=self.colors['text_secondary'], font=("微软雅黑", 9))
        self.factor_mode_label.pack(side=tk.LEFT, padx=(4, 0))
        self.factor_pid_label = tk.Label(factor_frame, text="PID: N/A", bg=self.colors['bg_card'],
                                         fg=self.colors['text_secondary'], font=("微软雅黑", 9))
        self.factor_pid_label.pack(side=tk.RIGHT)
        
        # EM 东方财富采集器
        em_frame = tk.Frame(status_frame, bg=self.colors['bg_card'])
        em_frame.pack(fill=tk.X, padx=12, pady=3)
        tk.Label(em_frame, text="🏛", bg=self.colors['bg_card'], fg=self.colors['accent'],
                font=("Segoe UI Emoji", 12)).pack(side=tk.LEFT)
        self.em_status_label = tk.Label(em_frame, text="东方财富采集: 检查中...", bg=self.colors['bg_card'],
                                        fg=self.colors['text_primary'], font=("微软雅黑", 11))
        self.em_status_label.pack(side=tk.LEFT, padx=(8, 0))
        self.em_mode_label = tk.Label(em_frame, text="", bg=self.colors['bg_card'],
                                      fg=self.colors['text_secondary'], font=("微软雅黑", 9))
        self.em_mode_label.pack(side=tk.LEFT, padx=(4, 0))
        self.em_pid_label = tk.Label(em_frame, text="PID: N/A", bg=self.colors['bg_card'],
                                     fg=self.colors['text_secondary'], font=("微软雅黑", 9))
        self.em_pid_label.pack(side=tk.RIGHT)
        
        # 看门狗状态
        wd_frame = tk.Frame(main_frame, bg=self.colors['bg_card'])
        wd_frame.pack(fill=tk.X, pady=(0, 10))
        self.wd_label = tk.Label(wd_frame, text="🛡 看门狗状态: 启用", bg=self.colors['bg_card'],
                                 fg=self.colors['success'], font=("微软雅黑", 10, "bold"))
        self.wd_label.pack(side=tk.LEFT, padx=12, pady=6)
        
        # 控制按钮（紧凑）
        control_frame = tk.Frame(main_frame, bg=self.colors['bg_card'])
        control_frame.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(control_frame, text="🎮 服务控制", bg=self.colors['bg_card'], fg=self.colors['accent'],
                font=("微软雅黑", 11, "bold")).pack(anchor=tk.W, padx=12, pady=(10, 8))
        
        btn_container = tk.Frame(control_frame, bg=self.colors['bg_card'])
        btn_container.pack(fill=tk.X, padx=12, pady=(0, 10))
        
        self.start_button = ModernButton(btn_container, "▶ 启动", self.start_services, "#10b981", "#34d399")
        self.start_button.pack(side=tk.LEFT, padx=4)
        self.stop_button = ModernButton(btn_container, "⏹ 停止", self.stop_services, "#ef4444", "#f87171")
        self.stop_button.pack(side=tk.LEFT, padx=4)
        self.restart_button = ModernButton(btn_container, "🔄 重启", self.restart_services, "#3b82f6", "#60a5fa")
        self.restart_button.pack(side=tk.LEFT, padx=4)
        self.refresh_button = ModernButton(btn_container, "🔍 刷新", self.check_status, "#6b7280", "#9ca3af")
        self.refresh_button.pack(side=tk.LEFT, padx=4)
        ModernButton(btn_container, "📊 因子", self.run_factors, "#f59e0b", "#fbbf24").pack(side=tk.LEFT, padx=4)
        ModernButton(btn_container, "🏛 东财", self.run_em, "#8b5cf6", "#a78bfa").pack(side=tk.LEFT, padx=4)
        ModernButton(btn_container, "🛡 看门狗", self.toggle_watchdog, "#6366f1", "#818cf8").pack(side=tk.LEFT, padx=4)
        
        # 快速访问（紧凑）
        access_frame = tk.Frame(main_frame, bg=self.colors['bg_card'])
        access_frame.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(access_frame, text="🚀 快速访问", bg=self.colors['bg_card'], fg=self.colors['accent'],
                font=("微软雅黑", 11, "bold")).pack(anchor=tk.W, padx=12, pady=(10, 8))
        
        acc_container = tk.Frame(access_frame, bg=self.colors['bg_card'])
        acc_container.pack(fill=tk.X, padx=12, pady=(0, 10))
        
        ModernButton(acc_container, "🌐 Web", self.open_web, "#6366f1", "#818cf8").pack(side=tk.LEFT, padx=4)
        ModernButton(acc_container, "📋 日志", self.view_logs, "#6366f1", "#818cf8").pack(side=tk.LEFT, padx=4)
        ModernButton(acc_container, "💾 数据", self.view_database, "#6366f1", "#818cf8").pack(side=tk.LEFT, padx=4)
        ModernButton(acc_container, "🧪 测试", self.test_api, "#6366f1", "#818cf8").pack(side=tk.LEFT, padx=4)
        ModernButton(acc_container, "📊 因子", self.view_factors, "#f59e0b", "#fbbf24").pack(side=tk.LEFT, padx=4)
        ModernButton(acc_container, "✅ 校验", self.run_data_check, "#10b981", "#34d399").pack(side=tk.LEFT, padx=4)
        
        # 操作日志（增加高度）
        log_frame = tk.Frame(main_frame, bg=self.colors['bg_card'])
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        tk.Label(log_frame, text="📝 操作日志", bg=self.colors['bg_card'], fg=self.colors['accent'],
                font=("微软雅黑", 11, "bold")).pack(anchor=tk.W, padx=12, pady=(10, 8))
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=12, font=("Consolas", 10),
                                                  bg="#1e293b", fg="#94a3b8", insertbackground="#3b82f6",
                                                  selectbackground="#3b82f6", relief=tk.FLAT, borderwidth=0)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))
        
        # 底部（紧凑）
        footer_frame = tk.Frame(self.root, bg=self.colors['bg_secondary'], height=35)
        footer_frame.pack(fill=tk.X, side=tk.BOTTOM)
        tk.Label(footer_frame, text=f"访问: http://127.0.0.1:5005 | 日志: {PROJECT_DIR / 'logs'}",
                bg=self.colors['bg_secondary'], fg=self.colors['text_secondary'],
                font=("微软雅黑", 9)).pack(pady=6)
    
    def log(self, message):
        self.log_text.configure(state=tk.NORMAL)
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)
    
    def check_status(self):
        """检查所有服务状态 + 看门狗自动恢复"""
        try:
            # ---- 检测 ----
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            port_result = sock.connect_ex(('127.0.0.1', 5005))
            sock.close()
            web_running = (port_result == 0)
            
            web_pid_file = PROJECT_DIR / "web_server.pid"
            collect_pid_file = PROJECT_DIR / "collection.pid"
            
            web_pid = None
            collect_pid = None
            collect_running = False
            
            if web_pid_file.exists():
                try:
                    web_pid = int(web_pid_file.read_text().strip())
                    if psutil.pid_exists(web_pid):
                        proc = psutil.Process(web_pid)
                        cmdline = ' '.join(proc.cmdline() or [])
                        if 'web_server' in cmdline:
                            web_running = True
                        elif web_running:
                            # 端口有进程在监听但pid文件不匹配，清掉重查
                            web_pid = None
                        else:
                            web_running = False
                            web_pid = None
                    elif web_running:
                        # 端口有监听但pid文件过期，信任端口，清pid
                        web_pid = None
                    else:
                        web_running = False
                        web_pid = None
                except:
                    pass
            
            if collect_pid_file.exists():
                try:
                    collect_pid = int(collect_pid_file.read_text().strip())
                    collect_running = psutil.pid_exists(collect_pid)
                except:
                    pass
            
            # 因子采集
            factor_pid = None
            factor_running = False
            is_daemon = False
            if FACTOR_PID_FILE.exists():
                try:
                    factor_pid = int(FACTOR_PID_FILE.read_text().strip())
                    factor_running = psutil.pid_exists(factor_pid)
                    if factor_running:
                        cmdline = ' '.join(psutil.Process(factor_pid).cmdline() or [])
                        is_daemon = '--daemon' in cmdline
                except:
                    pass
            
            # EM 东方财富采集器
            em_pid = None
            em_running = False
            em_daemon = False
            if EM_PID_FILE.exists():
                try:
                    em_pid = int(EM_PID_FILE.read_text().strip())
                    em_running = psutil.pid_exists(em_pid)
                    if em_running:
                        cmdline = ' '.join(psutil.Process(em_pid).cmdline() or [])
                        em_daemon = '--daemon' in cmdline
                except:
                    pass
            
            # ---- 看门狗自动恢复 ----
            if self.watchdog_enabled:
                if not web_running:
                    if self.watchdog_notified.get('web') != 'dead':
                        self.log("⚠ 看门狗: Web服务器未运行，正在自动启动...")
                        self.watchdog_notified['web'] = 'dead'
                    self._ensure_process('web')
                else:
                    self.watchdog_notified['web'] = 'alive'
                
                if not collect_running:
                    if self.watchdog_notified.get('collect') != 'dead':
                        self.log("⚠ 看门狗: 数据采集未运行，正在自动启动...")
                        self.watchdog_notified['collect'] = 'dead'
                    self._ensure_process('collect')
                else:
                    self.watchdog_notified['collect'] = 'alive'
                
                if not factor_running:
                    if self.watchdog_notified.get('factor') != 'dead':
                        self.log("⚠ 看门狗: 因子采集未运行，正在自动启动...")
                        self.watchdog_notified['factor'] = 'dead'
                    self._ensure_process('factor')
                else:
                    self.watchdog_notified['factor'] = 'alive'
                
                # EM 东方财富采集器
                if not em_running:
                    if self.watchdog_notified.get('em') != 'dead':
                        self.log("⚠ 看门狗: 东方财富采集未运行，正在自动启动...")
                        self.watchdog_notified['em'] = 'dead'
                    self._ensure_process('em')
                else:
                    self.watchdog_notified['em'] = 'alive'
                
                # 更新看门狗标签
                wd_text = "🛡 看门狗状态: 启用"
                wd_color = self.colors['success']
            else:
                wd_text = "🛡 看门狗状态: 已关闭"
                wd_color = self.colors['danger']
            
            self.wd_label.config(text=wd_text, fg=wd_color)
            
            # ---- 更新UI ----
            web_status_text = "运行中 ✓" if web_running else "未运行 ❌"
            web_color = self.colors['success'] if web_running else self.colors['danger']
            self.web_status_label.config(text=f"Web服务器: {web_status_text}", fg=web_color)
            self.web_pid_label.config(text=f"PID: {web_pid or 'N/A'}")
            
            collect_status_text = "运行中 ✓" if collect_running else "未运行 ❌"
            collect_color = self.colors['success'] if collect_running else self.colors['danger']
            self.collect_status_label.config(text=f"数据采集: {collect_status_text}", fg=collect_color)
            self.collect_pid_label.config(text=f"PID: {collect_pid or 'N/A'}")
            
            try:
                import sqlite3
                db_path = str(PROJECT_DIR / "stocks.db")
                if not os.path.exists(db_path):
                    db_path = str(PROJECT_DIR / "stocks.db")
                conn = sqlite3.connect(db_path)
                count = conn.execute("SELECT COUNT(*) FROM minute_5_price").fetchone()[0]
                conn.close()
                self.db_status_label.config(text=f"数据库: {count} 条记录 ✓")
            except:
                self.db_status_label.config(text="数据库: N/A ❌", fg=self.colors['danger'])
            
            factor_status_text = "运行中 ✓" if factor_running else "未运行 ❌"
            factor_color = self.colors['success'] if factor_running else self.colors['danger']
            self.factor_status_label.config(text=f"因子采集: {factor_status_text}", fg=factor_color)
            self.factor_mode_label.config(text="[定时循环]" if is_daemon else "[一次运行]" if factor_running else "")
            self.factor_pid_label.config(text=f"PID: {factor_pid or 'N/A'}")
            
            # EM 东方财富采集器 UI
            em_status_text = "运行中 ✓" if em_running else "未运行 ❌"
            em_color = self.colors['success'] if em_running else self.colors['danger']
            self.em_status_label.config(text=f"东方财富采集: {em_status_text}", fg=em_color)
            self.em_mode_label.config(text="[定时循环]" if em_daemon else "[一次运行]" if em_running else "")
            self.em_pid_label.config(text=f"PID: {em_pid or 'N/A'}")
            self.em_running = em_running
        except Exception as e:
            self.log(f"❌ 状态检查失败: {e}")
    
    def _ensure_process(self, name):
        """确保指定进程运行（看门狗内部调用）"""
        if name == 'web' or name == 'collect':
            subprocess.Popen(
                [sys.executable, str(PROJECT_DIR / "stock5_launcher.py"), "--start"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            )
        elif name == 'factor':
            # 因子采集 — 启动守护进程（完全独立，不挂 PIPE）
            subprocess.Popen(
                [sys.executable, FACTOR_RUNNER, "--daemon"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
            )
        elif name == 'em':
            # 东方财富采集器 — 守护进程模式
            subprocess.Popen(
                [sys.executable, str(EM_FETCHER), "--daemon"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
            )
    
    def toggle_watchdog(self):
        """切换看门狗启用/禁用"""
        self.watchdog_enabled = not self.watchdog_enabled
        if self.watchdog_enabled:
            self.log("🛡 看门狗已启用")
            self.watchdog_notified.clear()
        else:
            self.log("🛡 看门狗已关闭")
    
    def start_services(self):
        self.log("🚀 正在启动服务...")
        def start_thread():
            try:
                subprocess.Popen([sys.executable, str(PROJECT_DIR / "stock5_launcher.py"), "--start"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
                self.log("✓ 服务启动完成")
                time.sleep(5)
                self.check_status()
            except Exception as e:
                self.log(f"❌ 启动失败: {e}")
        threading.Thread(target=start_thread, daemon=True).start()
    
    def stop_services(self):
        self.log("🛑 正在停止服务...")
        def stop_thread():
            try:
                subprocess.Popen([sys.executable, str(PROJECT_DIR / "stock5_launcher.py"), "--stop"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
                self.log("✓ 服务已停止")
                time.sleep(3)
                self.check_status()
            except Exception as e:
                self.log(f"❌ 停止失败: {e}")
        threading.Thread(target=stop_thread, daemon=True).start()
    
    def restart_services(self):
        self.log("🔄 正在重启服务...")
        def restart_thread():
            try:
                subprocess.Popen([sys.executable, str(PROJECT_DIR / "stock5_launcher.py"), "--restart"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
                self.log("✓ 服务重启完成")
                time.sleep(5)
                self.check_status()
            except Exception as e:
                self.log(f"❌ 重启失败: {e}")
        threading.Thread(target=restart_thread, daemon=True).start()
    
    def run_factors(self):
        """启动因子采集守护进程（定时循环模式）"""
        # 先检查是否已在运行
        if FACTOR_PID_FILE.exists():
            try:
                pid = int(FACTOR_PID_FILE.read_text().strip())
                if psutil.pid_exists(pid):
                    self.log("⚠ 因子采集已在运行")
                    return
            except:
                pass
        
        self.log("📊 正在启动因子采集守护进程...")
        def factor_thread():
            try:
                proc = subprocess.Popen(
                    [sys.executable, FACTOR_RUNNER, "--daemon"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
                )
                # runner自身会写PID文件，这里等待2秒确认
                time.sleep(1)
                pid = proc.pid
                self.log(f"📊 因子采集守护进程已启动 (PID: {pid})")
                self.log(f"   日志: {FACTOR_LOG}")
                self.log(f"   模式: 交易日 09:00-15:00 每小时整点采集")
                time.sleep(2)
                self.check_status()
            except Exception as e:
                self.log(f"❌ 因子采集启动失败: {e}")
        threading.Thread(target=factor_thread, daemon=True).start()
    
    def run_em(self):
        """启动东方财富采集器守护进程"""
        if self.em_running:
            self.log("⚠ 东方财富采集已在运行")
            return
        
        self.log("🏛 正在启动东方财富采集守护进程...")
        def em_thread():
            try:
                proc = subprocess.Popen(
                    [sys.executable, str(EM_FETCHER), "--daemon"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
                )
                time.sleep(1)
                self.log(f"🏛 东方财富采集已启动 (PID: {proc.pid})")
                self.log(f"   日志: {EM_LOG}")
                self.log(f"   模式: 交易日 09:00-15:00 每小时整点采集基本面+市���面数据")
                time.sleep(2)
                self.check_status()
            except Exception as e:
                self.log(f"❌ 东方财富采集启动失败: {e}")
        threading.Thread(target=em_thread, daemon=True).start()
    
    def stop_factor(self):
        """停止因子采集进程"""
        self.log("🛑 正在停止因子采集...")
        def s_thread():
            try:
                if FACTOR_PID_FILE.exists():
                    pid = int(FACTOR_PID_FILE.read_text().strip())
                    if psutil.pid_exists(pid):
                        proc = psutil.Process(pid)
                        proc.terminate()
                        self.log(f"✓ 因子采集已停止 (PID: {pid})")
                    FACTOR_PID_FILE.unlink(missing_ok=True)
                else:
                    self.log("⚠ 因子采集未运行")
                time.sleep(2)
                self.check_status()
            except Exception as e:
                self.log(f"❌ 停止因子采集失败: {e}")
        threading.Thread(target=s_thread, daemon=True).start()
    
    def open_web(self):
        import webbrowser
        webbrowser.open("http://127.0.0.1:5005")
        self.log("🌐 打开Web界面")
    
    def view_logs(self):
        log_window = tk.Toplevel(self.root)
        log_window.title("📋 日志查看")
        log_window.geometry("700x500")
        log_window.configure(bg=self.colors['bg_main'])
        
        tk.Label(log_window, text="📋 日志查看", bg=self.colors['bg_main'], fg=self.colors['accent'],
                font=("微软雅黑", 16, "bold")).pack(pady=15)
        
        ttk.Label(log_window, text="选择日志文件:").pack(pady=5)
        
        log_combo = ttk.Combobox(log_window, values=["web_server.log", "collection.log", "factor_collection.log", "em_fetcher.log"])
        log_combo.set("web_server.log")
        log_combo.pack(pady=5)
        
        log_content = scrolledtext.ScrolledText(log_window, font=("Consolas", 9),
                                                bg=self.colors['bg_secondary'], fg=self.colors['text_secondary'])
        log_content.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)
        
        def load_log():
            log_file = log_combo.get()
            log_path = PROJECT_DIR / "logs" / log_file
            if log_path.exists():
                try:
                    with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        lines = content.split('\n')[-500:]
                        log_content.delete(1.0, tk.END)
                        log_content.insert(tk.END, '\n'.join(lines))
                except Exception as e:
                    log_content.delete(1.0, tk.END)
                    log_content.insert(tk.END, f"读取失败: {e}")
        
        ModernButton(log_window, "🔍 加载", load_log, "#3b82f6", "#60a5fa").pack(pady=10)
        load_log()
        self.log("📋 打开日志查看")
    
    def view_database(self):
        db_window = tk.Toplevel(self.root)
        db_window.title("💾 数据库统计")
        db_window.geometry("700x600")
        db_window.configure(bg=self.colors['bg_main'])
        
        tk.Label(db_window, text="💾 数据库统计", bg=self.colors['bg_main'], fg=self.colors['accent'],
                font=("微软雅黑", 16, "bold")).pack(pady=15)
        
        try:
            import sqlite3
            conn = sqlite3.connect(str(PROJECT_DIR / "stocks.db"))
            
            stats_frame = tk.Frame(db_window, bg=self.colors['bg_card'])
            stats_frame.pack(fill=tk.X, padx=15, pady=15)
            
            total = conn.execute("SELECT COUNT(*) FROM minute_5_price").fetchone()[0]
            tk.Label(stats_frame, text=f"📊 总记录数: {total}", bg=self.colors['bg_card'],
                    fg=self.colors['text_primary'], font=("微软雅黑", 14)).pack(anchor=tk.W, padx=15, pady=10)
            
            stocks = conn.execute("SELECT COUNT(DISTINCT code) FROM minute_5_price").fetchone()[0]
            tk.Label(stats_frame, text=f"📈 股票数量: {stocks}", bg=self.colors['bg_card'],
                    fg=self.colors['text_primary'], font=("微软雅黑", 14)).pack(anchor=tk.W, padx=15, pady=10)
            
            latest = conn.execute("SELECT MAX(datetime) FROM minute_5_price").fetchone()[0]
            tk.Label(stats_frame, text=f"⏰ 最新时间: {latest}", bg=self.colors['bg_card'],
                    fg=self.colors['text_primary'], font=("微软雅黑", 14)).pack(anchor=tk.W, padx=15, pady=10)
            
            complete = conn.execute("SELECT COUNT(*) FROM minute_5_price WHERE ma5 IS NOT NULL").fetchone()[0]
            tk.Label(stats_frame, text=f"✅ 技术指标完整: {complete}/{total} ({complete/total*100:.1f}%)",
                    bg=self.colors['bg_card'], fg=self.colors['success'], font=("微软雅黑", 14)).pack(anchor=tk.W, padx=15, pady=10)
            
            data_frame = tk.Frame(db_window, bg=self.colors['bg_card'])
            data_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
            
            tk.Label(data_frame, text="📊 最新数据", bg=self.colors['bg_card'], fg=self.colors['accent'],
                    font=("微软雅黑", 13, "bold")).pack(anchor=tk.W, padx=15, pady=(15, 10))
            
            data_text = scrolledtext.ScrolledText(data_frame, font=("Consolas", 9),
                                                  bg=self.colors['bg_secondary'], fg=self.colors['text_secondary'], height=15)
            data_text.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 15))
            
            latest_data = conn.execute("""
                SELECT code, datetime, close, pct_chg, ma5, rsi6, k, d
                FROM minute_5_price
                ORDER BY datetime DESC
                LIMIT 10
            """).fetchall()
            
            header = f"{'代码':<10} {'时间':<20} {'价格':<8} {'涨幅%':<8} {'MA5':<8} {'RSI6':<8}\n"
            data_text.insert(tk.END, header)
            data_text.insert(tk.END, "-" * 80 + "\n")
            
            for row in latest_data:
                line = f"{row[0]:<10} {row[1]:<20} {row[2]:<8.2f} {row[3]:<8.2f} {row[4]:<8.2f} {row[5]:<8.2f}\n"
                data_text.insert(tk.END, line)
            
            conn.close()
        except Exception as e:
            error_frame = tk.Frame(db_window, bg=self.colors['bg_card'])
            error_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
            tk.Label(error_frame, text=f"❌ 数据库读取失败: {e}", bg=self.colors['bg_card'],
                    fg=self.colors['danger'], font=("微软雅黑", 14)).pack(pady=20)
            self.log(f"❌ 数据库读取失败: {e}")
        
        self.log("💾 打开数据库统计")
    
    def view_factors(self):
        """查看因子采集数据"""
        fw = tk.Toplevel(self.root)
        fw.title("📊 因子数据")
        fw.geometry("750x550")
        fw.configure(bg=self.colors['bg_main'])
        
        tk.Label(fw, text="📊 大盘 & 基本面因子", bg=self.colors['bg_main'], fg=self.colors['accent'],
                font=("微软雅黑", 16, "bold")).pack(pady=15)
        
        info_frame = tk.Frame(fw, bg=self.colors['bg_card'])
        info_frame.pack(fill=tk.X, padx=15, pady=5)
        self.factor_info_label = tk.Label(info_frame, text="正在查询...", bg=self.colors['bg_card'],
                                          fg=self.colors['text_primary'], font=("微软雅黑", 12))
        self.factor_info_label.pack(anchor=tk.W, padx=15, pady=10)
        
        self.factor_text = scrolledtext.ScrolledText(fw, font=("Consolas", 9),
                                                     bg=self.colors['bg_secondary'], fg=self.colors['text_secondary'])
        self.factor_text.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)
        
        self.load_factor_data()
        self.log("📊 打开因子数据查看")
    
    def load_factor_data(self):
        """加载因子数据到text框"""
        try:
            import sqlite3
            db = str(PROJECT_DIR / "stocks.db")
            conn = sqlite3.connect(db)
            cur = conn.cursor()
            
            # 查macro_factors
            cur.execute("SELECT COUNT(*) FROM macro_factors")
            mf_count = cur.fetchone()[0]
            
            # 查factor_signals
            cur.execute("SELECT COUNT(*) FROM factor_signals")
            fs_count = cur.fetchone()[0]
            
            # 最新大盘因子
            cur.execute("""SELECT date, update_time, hs300_close, hs300_pct,
                           zz500_close, zz500_pct, top_sector
                           FROM macro_factors ORDER BY id DESC LIMIT 1""")
            latest = cur.fetchone()
            
            info_text = f"macro_factors: {mf_count} 条 | factor_signals: {fs_count} 条"
            if latest:
                info_text += f"\n最新大盘: {latest[0]} {latest[1]} 沪深300={latest[2]:.0f}({latest[3]:+.2f}%) 最强板块={latest[6]}"
            self.factor_info_label.config(text=info_text)
            
            # 因子信号Top
            self.factor_text.delete(1.0, tk.END)
            header = f"{'代码':<12} {'日期':<12} {'情感分':<8} {'财务分':<8} {'资金分':<8} {'置信度':<8}\n"
            self.factor_text.insert(tk.END, header)
            self.factor_text.insert(tk.END, "-" * 60 + "\n")
            
            cur.execute("""SELECT code, date, news_score, fin_score, fund_score, llm_confidence
                           FROM factor_signals ORDER BY date DESC, code LIMIT 30""")
            for row in cur.fetchall():
                line = f"{row[0]:<12} {row[1]:<12} {row[2]:<8} {row[3]:<8} {row[4]:<8} {row[5]:<8}\n"
                self.factor_text.insert(tk.END, line)
            
            conn.close()
        except Exception as e:
            self.factor_info_label.config(text=f"查询失败: {e}", fg=self.colors['danger'])
            self.log(f"❌ 因子数据查询失败: {e}")
    
    def run_data_check(self):
        """运行数据完整性校验"""
        self.log("🧪 正在执行数据校验...")
        def check_thread():
            try:
                import subprocess, json
                result = subprocess.run(
                    [sys.executable, str(PROJECT_DIR / "check_data_integrity.py")],
                    capture_output=True, text=True, timeout=60, encoding='utf-8'
                )
                if not result.stdout:
                    raise ValueError(f"校验脚本无输出，stderr: {result.stderr[:500] if result.stderr else '无'}")
                report = json.loads(result.stdout)
                s = report['summary']
                self.log(f"✅ 校验完成: {s['passed']}通过/{s['warnings']}警告/{s['errors']}错误")
                
                # 弹窗展示详细结果
                detail = "\n".join(
                    f"  {'✅' if c['status']=='PASS' else '⚠️' if c['status']=='WARN' else '❌'} {c['name']:20s} → {c['detail']}"
                    for c in report['checks']
                )
                from tkinter import messagebox
                if s['errors'] == 0:
                    messagebox.showinfo("✅ 数据校验通过",
                        f"全部 {s['total']} 项检查通过 ✓\n{s['passed']}通过 / {s['warnings']}警告 / {s['errors']}错误\n\n{detail}")
                else:
                    messagebox.showwarning("⚠️ 数据校验有异常",
                        f"{s['errors']} 项未通过!\n{s['passed']}通过 / {s['warnings']}警告 / {s['errors']}错误\n\n{detail}")
            except Exception as e:
                self.log(f"❌ 校验执行失败: {e}")
                from tkinter import messagebox
                messagebox.showerror("❌ 校验失败", f"执行出错: {e}")
        threading.Thread(target=check_thread, daemon=True).start()
    
    def test_api(self):
        try:
            import requests
            status = requests.get("http://127.0.0.1:5005/api/status", timeout=5).json()
            messagebox.showinfo("🧪 API测试",
                f"✅ API测试成功!\n\n数据记录数: {status['minute_5_data_count']}\n系统状态: {status['status']}")
            self.log("✅ API测试成功")
        except Exception as e:
            messagebox.showerror("🧪 API测试", f"❌ API测试失败: {e}")
            self.log(f"❌ API测试失败: {e}")
    
    def auto_refresh(self):
        """定时刷新 + 看门狗"""
        if not self.startup_done:
            self.startup_done = True
        self.check_status()
        self.root.after(5000, self.auto_refresh)

def main():
    root = tk.Tk()
    app = Stock5LauncherGUI(root)
    root.mainloop()

if __name__ == '__main__':
    main()
