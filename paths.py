"""
paths.py — ตัวช่วยหา path ให้ทำงานถูกทั้งตอนรันเป็นสคริปต์ และตอน build เป็น .exe (PyInstaller)
"""
import os
import sys


def resource_path(rel):
    """path ของไฟล์ที่อ่านอย่างเดียว (template ฯลฯ) — รองรับ PyInstaller (_MEIPASS)"""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


def data_dir():
    """โฟลเดอร์ที่ 'เขียนไฟล์ได้' (log เหรียญ) — ข้าง ๆ .exe ตอน build, ไม่งั้นข้างสคริปต์"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def data_path(rel):
    """path เต็มของไฟล์ที่เขียนได้ ใน data_dir()"""
    return os.path.join(data_dir(), rel)
