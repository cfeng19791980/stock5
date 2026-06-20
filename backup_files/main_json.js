// -*- coding: utf-8 -*-
// Electron主进程 - v5.0 大盘走势权重版
// 功能：启动更新 + 30分钟定时更新 + 自动分析

const { app, BrowserWindow, ipcMain } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

let mainWindow;
let updateTimer = null;
let isUpdating = false;

const BASE_DIR = __dirname;
const PYTHON_EXE = 'C:/Users/10341/AppData/Local/Programs/Python/Python312/python.exe';
const DATA_FETCHER = path.join(BASE_DIR, 'data_fetcher.py');
const ANALYZER = path.join(BASE_DIR, 'analyzer_v4.py');
const ANALYZER_V5 = path.join(BASE_DIR, 'analyzer_v5.py');
const MARKET_FETCHER = path.join(BASE_DIR, 'market_index_fetcher.py');
const JSON_FILE = path.join(BASE_DIR, 'result.json');
const JSON_FILE_V5 = path.join(BASE_DIR, 'result_v5.json');

// 更新间隔：30分钟
const UPDATE_INTERVAL = 30 * 60 * 1000;

// 读取JSON文件
// 读取JSON文件（v4或v5）
function readJSON(version = 'v4') {
  try {
    const file = version === 'v5' ? JSON_FILE_V5 : JSON_FILE;
    if (fs.existsSync(file)) {
      return JSON.parse(fs.readFileSync(file, 'utf8'));
    }
    return null;
  } catch (e) {
    return null;
  }
}

// 读取持仓文件
function readHoldings() {
  try {
    if (fs.existsSync(HOLDINGS_FILE)) {
      return JSON.parse(fs.readFileSync(HOLDINGS_FILE, 'utf8'));
    }
    return [];
  } catch (e) {
    return [];
  }
}

// 保存持仓文件
function saveHoldings(holdings) {
  try {
    fs.writeFileSync(HOLDINGS_FILE, JSON.stringify(holdings, null, 2), 'utf8');
    return true;
  } catch (e) {
    return false;
  }
}

// 运行数据更新 + 分析（包含大盘信息更新）
function runUpdateAndAnalyze() {
  if (isUpdating) return;
  isUpdating = true;
  
  console.log('开始更新数据...');
  
  // 通知前端更新状态
  if (mainWindow) {
    mainWindow.webContents.send('update-status', '正在更新大盘信息...');
  }
  
  // Step 0: 更新大盘信息
  const marketFetcher = spawn(PYTHON_EXE, [MARKET_FETCHER], { cwd: BASE_DIR });
  
  marketFetcher.stdout.on('data', (data) => {
    console.log('大盘更新:', data.toString().trim());
  });
  
  marketFetcher.stderr.on('data', (data) => {
    console.error('大盘更新错误:', data.toString().trim());
  });
  
  marketFetcher.on('close', (code) => {
    console.log('大盘信息更新完成:', code);
    
    if (mainWindow) {
      mainWindow.webContents.send('update-status', '正在更新股票数据...');
    }
    
    // Step1: 更新股票数据
    const fetcher = spawn(PYTHON_EXE, [DATA_FETCHER], { cwd: BASE_DIR });
  
  fetcher.stdout.on('data', (data) => {
    console.log('数据更新:', data.toString().trim());
  });
  
  fetcher.stderr.on('data', (data) => {
    console.error('数据更新错误:', data.toString().trim());
  });
  
  fetcher.on('close', (code) => {
    console.log('数据更新完成:', code);
    
    if (mainWindow) {
      mainWindow.webContents.send('update-status', '正在分析数据...');
    }
    
    // Step2: 运行分析
    const analyzer = spawn(PYTHON_EXE, [ANALYZER], { cwd: BASE_DIR });
    
    analyzer.stdout.on('data', (data) => {
      console.log('分析:', data.toString().trim());
    });
    
    analyzer.stderr.on('data', (data) => {
      console.error('分析错误:', data.toString().trim());
    });
    
    analyzer.on('close', (code) => {
      console.log('分析v4完成:', code);
      
      if (mainWindow) {
        mainWindow.webContents.send('update-status', '正在分析数据（v5测试模型）...');
      }
      
      // Step3: 运行v5分析（测试模型）
      const analyzerV5 = spawn(PYTHON_EXE, [ANALYZER_V5], { cwd: BASE_DIR });
      
      analyzerV5.stdout.on('data', (data) => {
        console.log('分析v5:', data.toString().trim());
      });
      
      analyzerV5.stderr.on('data', (data) => {
        console.error('分析v5错误:', data.toString().trim());
      });
      
      analyzerV5.on('close', (code) => {
        console.log('分析v5完成:', code);
        isUpdating = false;
        
        if (mainWindow) {
          mainWindow.webContents.send('update-status', '更新完成（v4+v5双系统）');
          mainWindow.webContents.send('data-updated');
        }
      });
    });
  });
  });
}

// 启动定时更新
function startAutoUpdate() {
  // 立即执行一次
  runUpdateAndAnalyze();
  
  // 每30分钟执行
  updateTimer = setInterval(() => {
    console.log('定时更新触发...');
    runUpdateAndAnalyze();
  }, UPDATE_INTERVAL);
  
  console.log('自动更新已启动，间隔: 30分钟');
}

// 创建窗口
function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1600,
    height: 900,
    webPreferences: {
      preload: path.join(BASE_DIR, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false
    },
    title: '波段股票分析系统 v5.0 - 大盘走势权重版'
  });
  
  mainWindow.loadFile(path.join(BASE_DIR, 'index.html'));
  
  mainWindow.webContents.on('did-finish-load', () => {
    // 窗口加载完成后启动自动更新
    startAutoUpdate();
  });
}

// IPC Handlers
ipcMain.handle('get-all-stocks', () => {
  const data = readJSON();
  return data ? data.stocks : [];
});

ipcMain.handle('get-buy-stocks', () => {
  const data = readJSON();
  if (!data || !data.stocks) return [];
  return data.stocks.filter(s => s.score >= 60);
});

ipcMain.handle('get-sell-stocks', () => {
  const data = readJSON();
  if (!data || !data.stocks) return [];
  return data.stocks.filter(s => s.score < 15);
});

ipcMain.handle('get-status', () => {
  const data = readJSON();
  return data || { update_time: '未更新', stock_count: 0 };
});

ipcMain.handle('refresh-data', () => {
  runUpdateAndAnalyze();
  return { status: 'started' };
});

ipcMain.handle('save-holdings', (event, holdings) => {
  return saveHoldings(holdings);
});

ipcMain.handle('get-holdings', () => {
  return readHoldings();
});

ipcMain.handle('get-update-status', () => {
  return { isUpdating, nextUpdate: updateTimer ? UPDATE_INTERVAL : 0 };
});

// 启动应用
app.whenReady().then(() => {
  createWindow();
});

app.on('window-all-closed', () => {
  if (updateTimer) clearInterval(updateTimer);
  if (process.platform !== 'darwin') app.quit();
});