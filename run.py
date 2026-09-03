#!/usr/bin/env python3
"""
Главный файл запуска бэкенда.
Запускается командой: python3 run.py
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
