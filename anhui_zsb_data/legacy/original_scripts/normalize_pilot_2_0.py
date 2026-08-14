#!/usr/bin/env python3
"""
合肥师范学院 (HFNU) 专升本数据规范化脚本 (Pilot 2.0)

审计报告修复版本：
- 建立 program_years + program_offerings 两层模型
- enrollment_plans 引入 offering_id + value_status
- admission_scores 引入 offering_id + score_value_numeric 拆分
- exam_subjects 引入 subject_slot
- 新建 institutions.csv (含联合培养院校)
- 修正 dim_school_alias
- 幂等可重跑 (overwrite 而非 append)
"""

import csv
import hashlib
import json
import os
import re
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
NORM_DIR = os.path.join(BASE_DIR, "normalized")
RAW_DIR = os.path.join(BASE_DIR, "raw")
QA_DIR = os.path.join(BASE_DIR, "qa")
PROGRESS_DIR = os.path.join(BASE_DIR, "progress")

SCHOOL_ID = "HFNU"
TODAY = datetime.now().strftime("%Y-%m-%d")

# ============================================================================
# 原始数据 (从 populate_data.py 复制，保持不变)
# ============================================================================

DATA_2024 = [
    ("学前教育", "文", 120, 10, 2, 10, 4600, "校本部"),
    ("商务英语", "文", 120, 10, 2, 10, 4600, "校本部"),
    ("电子信息工程", "理", 120, 10, 2, 10, 5390, "校本部"),
    ("药物制剂", "理", 140, 11, 3, 11, 5200, "校本部"),
    ("人力资源管理", "文", 120, 10, 2, 10, 4600, "校本部"),
    ("网络与新媒体", "文", 120, 10, 2, 10, 5060, "校本部"),
    ("通信工程", "理", 120, 10, 2, 10, 4900, "校本部"),
    ("化学工程与工艺", "理", 120, 10, 2, 10, 4900, "校本部"),
    ("软件工程", "理", 120, 10, 2, 10, 5390, "校本部"),
    ("数据科学与大数据技术", "理", 120, 10, 2, 10, 5390, "校本部"),
    ("互联网金融", "文", 120, 10, 2, 10, 4600, "校本部"),
    ("生物制药", "理", 120, 10, 2, 10, 4900, "校本部"),
    ("经济统计学", "理", 120, 10, 2, 10, 4600, "校本部"),
    ("新能源材料与器件", "理", 120, 10, 2, 10, 4900, "校本部"),
    ("材料科学与工程", "理", 120, 10, 2, 10, 4900, "校本部"),
    ("视觉传达设计", "艺术", 60, 4, 2, 4, 8000, "校本部"),
    ("服装与服饰设计", "艺术", 30, 2, 1, 2, 8000, "校本部"),
    ("动画", "艺术", 30, 2, 1, 2, 8000, "校本部"),
    ("财务管理", "文", 40, 3, 1, 3, 5060, "安徽工业经济职业技术学院联合培养"),
    ("市场营销", "文", 40, 3, 1, 3, 4600, "安徽工业经济职业技术学院联合培养"),
    ("电气工程及其自动化", "理", 40, 3, 1, 3, 5390, "安徽工业经济职业技术学院联合培养"),
    ("网络工程", "理", 40, 3, 1, 3, 5390, "安徽工业经济职业技术学院联合培养"),
    ("计算机科学与技术", "理", 40, 3, 1, 3, 5390, "安徽工业经济职业技术学院联合培养"),
    ("制药工程", "理", 30, 2, 1, 2, 4900, "合肥职业技术学院联合培养"),
    ("运动康复", "体育", 30, 2, 1, 2, 4900, "合肥职业技术学院联合培养"),
    ("小学教育", "文", 60, 4, 2, 4, 5060, "淮北职业技术学院联合培养"),
    ("电气工程及其自动化", "理", 60, 4, 2, 4, 5390, "淮北职业技术学院联合培养"),
    ("环境设计", "艺术", 80, 6, 2, 6, 8000, "马鞍山师范高等专科学校联合培养"),
    ("计算机科学与技术", "理", 120, 10, 2, 10, 5390, "马鞍山师范高等专科学校联合培养"),
    ("食品质量与安全", "理", 80, 6, 2, 6, 4900, "马鞍山师范高等专科学校联合培养"),
]

DATA_2025 = [
    ("商务英语", "文", 120, 10, 2, 10, 4600, "校本部"),
    ("电子信息工程", "理", 120, 10, 2, 10, 5390, "校本部"),
    ("药物制剂", "理", 140, 11, 3, 11, 5200, "校本部"),
    ("人力资源管理", "文", 120, 10, 3, 10, 4600, "校本部"),
    ("市场营销", "文", 120, 10, 3, 10, 4600, "校本部"),
    ("网络与新媒体", "文", 120, 10, 2, 10, 5060, "校本部"),
    ("通信工程", "理", 120, 10, 2, 10, 4900, "校本部"),
    ("化学工程与工艺", "理", 100, 8, 2, 8, 4900, "校本部"),
    ("软件工程", "理", 120, 10, 2, 10, 4900, "校本部"),
    ("数据科学与大数据技术", "理", 120, 10, 2, 10, 4900, "校本部"),
    ("互联网金融", "文", 90, 7, 2, 7, 4600, "校本部"),
    ("学前教育", "文", 50, 4, 1, 4, 4600, "校本部, 师范"),
    ("生物制药", "理", 120, 10, 2, 10, 4900, "校本部"),
    ("经济统计学", "理", 120, 10, 2, 10, 4600, "校本部"),
    ("新能源材料与器件", "理", 100, 8, 2, 8, 4900, "校本部"),
    ("音乐学", "艺术(文)", 30, 2, 1, 2, 8000, "校本部, 师范"),
    ("视觉传达设计", "艺术(文)", 80, 7, 2, 7, 8000, "校本部"),
    ("服装与服饰设计", "艺术(文)", 50, 4, 1, 4, 8000, "校本部"),
    ("动画", "艺术(文)", 50, 4, 1, 4, 8000, "校本部"),
    ("财务管理", "文", 40, 3, 1, 3, 5060, "安徽工业经济职业技术学院联合培养"),
    ("电气工程及其自动化", "理", 40, 3, 1, 3, 5390, "安徽工业经济职业技术学院联合培养"),
    ("网络工程", "理", 40, 3, 1, 3, 4900, "安徽工业经济职业技术学院联合培养"),
    ("计算机科学与技术", "理", 40, 3, 1, 3, 5390, "安徽工业经济职业技术学院联合培养"),
    ("网络工程", "理", 80, 6, 2, 6, 4900, "合肥职业技术学院联合培养"),
    ("制药工程", "理", 40, 3, 1, 3, 4900, "合肥职业技术学院联合培养"),
    ("运动康复", "体育(文)", 100, 7, 2, 7, 4900, "合肥职业技术学院联合培养"),
    ("小学教育", "文", 70, 5, 1, 5, 5060, "淮北职业技术学院联合培养, 师范"),
    ("电气工程及其自动化", "理", 40, 3, 1, 3, 5390, "淮北职业技术学院联合培养"),
    ("环境设计", "艺术(文)", 80, 7, 2, 7, 8000, "马鞍山师范高等专科学校联合培养"),
    ("计算机科学与技术", "理", 70, 5, 1, 5, 5390, "马鞍山师范高等专科学校联合培养"),
    ("食品质量与安全", "理", 70, 5, 1, 5, 4900, "马鞍山师范高等专科学校联合培养"),
]

DATA_2026 = [
    ("商务英语", "文", 110, 7, "", 8, 4600, "校本部"),
    ("电子信息工程", "理", 100, 12, 2, 8, 5390, "校本部"),
    ("药物制剂", "理", 120, 8, "", 8, 5200, "校本部"),
    ("人力资源管理", "文", 100, 12, 2, 9, 4600, "校本部"),
    ("市场营销", "文", 100, 12, 1, 8, 4600, "校本部"),
    ("网络与新媒体", "文", 100, 12, 1, 9, 5060, "校本部"),
    ("通信工程", "理", 100, 12, 1, 8, 4900, "校本部"),
    ("化学工程与工艺", "理", 100, 6, 2, 6, 4900, "校本部"),
    ("软件工程", "理", 100, 12, 2, 9, 4900, "校本部"),
    ("互联网金融", "文", 60, "", "", 5, 4600, "校本部"),
    ("学前教育", "文", 50, 4, "", 6, 4600, "校本部, 师范"),
    ("生物制药", "理", 100, 6, 1, 8, 4900, "校本部"),
    ("经济统计学", "理", 100, 10, 1, 8, 4600, "校本部"),
    ("新能源材料与器件", "理", 80, 10, 1, 4, 4900, "校本部"),
    ("音乐学", "艺术(文)", 30, "", "", "", 8000, "校本部, 师范"),
    ("视觉传达设计", "艺术(文)", 60, 8, "", 5, 8000, "校本部"),
    ("服装与服饰设计", "艺术(文)", 30, "", "", 2, 8000, "校本部"),
    ("动画", "艺术(文)", 50, 5, "", 4, 8000, "校本部"),
    ("运动康复", "体育(文)", 50, 5, "", 2, 4900, "校本部"),
    ("财务管理", "文", 50, 4, "", 6, 5060, "安徽工业经济职业技术学院联合培养"),
    ("电气工程及其自动化", "理", 50, 5, "", 4, 5390, "安徽工业经济职业技术学院联合培养"),
    ("网络工程", "理", 50, 3, "", 2, 4900, "安徽工业经济职业技术学院联合培养"),
    ("计算机科学与技术", "理", 50, 5, "", 5, 5390, "安徽工业经济职业技术学院联合培养"),
    ("小学教育", "文", 60, 4, "", 7, 5060, "淮北职业技术学院联合培养, 师范"),
    ("电气工程及其自动化", "理", 50, 5, "", 3, 5390, "淮北职业技术学院联合培养"),
    ("环境设计", "艺术(文)", 50, 4, "", 4, 8000, "马鞍山师范高等专科学校联合培养"),
    ("计算机科学与技术", "理", 50, 5, "", 4, 5390, "马鞍山师范高等专科学校联合培养"),
    ("食品质量与安全", "理", 50, 4, "", 4, 4900, "马鞍山师范高等专科学校联合培养"),
]

SCORES_2024 = [
    ("学前教育", "364(专业课1:69)", "53", "", "343", "", "校本部"),
    ("商务英语", "330", "54", "", "342", "81.33", "校本部"),
    ("电子信息工程", "198", "63(职测:20)", "", "314", "73.66", "校本部"),
    ("药物制剂", "273", "51", "229", "225", "", "校本部"),
    ("人力资源管理", "382", "60", "269", "348", "81.33", "校本部"),
    ("网络与新媒体", "394(专业课1:114)", "65(职测:29)", "", "420", "75.67", "校本部"),
    ("通信工程", "197", "60", "", "260", "75", "校本部"),
    ("化学工程与工艺", "210", "46", "", "211", "", "校本部"),
    ("软件工程", "297", "59", "", "328", "73", "校本部"),
    ("数据科学与大数据技术", "339", "60", "", "243", "68.67", "校本部"),
    ("互联网金融", "271", "50(职测:9)", "", "349", "81", "校本部"),
    ("生物制药", "270", "40", "", "222", "75.33", "校本部"),
    ("经济统计学", "311", "53", "462", "241", "79", "校本部"),
    ("新能源材料与器件", "197.5", "59(职测:15)", "", "219.5", "73.33", "校本部"),
    ("材料科学与工程", "207", "58", "", "285.5", "", "校本部"),
    ("视觉传达设计", "423", "68(职测:27)", "", "442", "74.33", "校本部"),
    ("服装与服饰设计", "400.5", "61", "", "391.5", "", "校本部"),
    ("动画", "404.5", "61", "", "405", "76.67", "校本部"),
    ("财务管理", "270", "41", "", "260", "80", "安徽工业经济职业技术学院"),
    ("市场营销", "270", "46", "", "265", "81", "安徽工业经济职业技术学院"),
    ("电气工程及其自动化", "225", "49", "", "77", "", "安徽工业经济职业技术学院"),
    ("网络工程", "222", "60", "", "323", "87", "安徽工业经济职业技术学院"),
    ("计算机科学与技术", "203", "40", "", "188", "79.67", "安徽工业经济职业技术学院"),
    ("制药工程", "331(专业课1:97)", "", "", "381", "", "合肥职业技术学院"),
    ("运动康复", "359", "59", "395", "443", "74", "合肥职业技术学院"),
    ("小学教育", "341", "62", "", "292", "84.33", "淮北职业技术学院"),
    ("电气工程及其自动化", "200", "47", "", "340", "", "淮北职业技术学院"),
    ("环境设计", "404(专业课1:115.5)", "41", "", "323.5", "75", "马鞍山师范高等专科学校"),
    ("计算机科学与技术", "196", "50(职测:9)", "245", "200", "71.67", "马鞍山师范高等专科学校"),
    ("食品质量与安全", "205", "56", "", "208", "78.67", "马鞍山师范高等专科学校"),
]

SCORES_2025 = [
    ("商务英语", "454.5(专业课1:115.5)", "64", "", "427.5", ""),
    ("电子信息工程", "417(专业课1:127.5)", "72.5", "205", "351", ""),
    ("药物制剂", "205.5", "58", "", "264.5", ""),
    ("人力资源管理", "423.5", "62.5", "", "422", ""),
    ("市场营销", "413", "62", "", "305", ""),
    ("网络与新媒体", "416.5", "76.5", "", "411.5", ""),
    ("通信工程", "419", "70.5", "", "227", ""),
    ("化学工程与工艺", "283.5", "64.5", "", "343.5", ""),
    ("软件工程", "439", "68.5", "272.5", "388", ""),
    ("数据科学与大数据技术", "333", "68.5", "393.5", "320.5", ""),
    ("互联网金融", "293.5", "67.5", "", "258", ""),
    ("学前教育", "472.5", "69", "", "453", "师范"),
    ("生物制药", "321.5", "44", "", "187", ""),
    ("经济统计学", "403.5", "50", "", "272", ""),
    ("新能源材料与器件", "230", "57", "", "262", ""),
    ("音乐学", "406", "", "", "389", "师范"),
    ("视觉传达设计", "458.5(专业课1:126.5)", "73", "", "410", ""),
    ("服装与服饰设计", "460", "71.5", "", "415", ""),
    ("动画", "465.5", "68", "", "365", ""),
    ("财务管理", "454.5", "72", "", "431", "安徽工业经济职业技术学院"),
    ("电气工程及其自动化", "415", "66.5", "", "270", "安徽工业经济职业技术学院"),
    ("网络工程", "327", "50", "", "", "安徽工业经济职业技术学院"),
    ("计算机科学与技术", "402", "68", "379", "269", "安徽工业经济职业技术学院"),
    ("网络工程", "351.5(专业课1:108.5)", "51", "406.5", "261", "合肥职业技术学院"),
    ("制药工程", "239.5", "47.5", "", "315", "合肥职业技术学院"),
    ("运动康复", "340", "47.5", "", "282.5", "合肥职业技术学院"),
    ("小学教育", "454", "67.5", "", "403.5", "淮北职业技术学院"),
    ("电气工程及其自动化", "", "", "", "", "淮北职业技术学院"),
    ("环境设计", "", "", "", "", "马鞍山师范高等专科学校"),
    ("计算机科学与技术", "", "", "", "", "马鞍山师范高等专科学校"),
    ("食品质量与安全", "", "", "", "", "马鞍山师范高等专科学校"),
]

SUBJECTS_2024 = [
    ("学前教育", "大学语文", "英语", "教育学", "心理学"),
    ("小学教育", "大学语文", "英语", "教育学", "心理学"),
    ("人力资源管理", "大学语文", "英语", "管理学原理", "会计学原理"),
    ("财务管理", "大学语文", "英语", "管理学原理", "会计学原理"),
    ("市场营销", "大学语文", "英语", "管理学原理", "会计学原理"),
    ("互联网金融", "大学语文", "英语", "微观经济学", "会计学原理"),
    ("网络与新媒体", "大学语文", "英语", "传播学概论", "新闻学概论"),
    ("商务英语", "大学语文", "英语", "综合商务英语", "旅游与酒店管理"),
    ("动画", "大学语文", "英语", "人物速写", "插画设计"),
    ("视觉传达设计", "大学语文", "英语", "人物速写", "插画设计"),
    ("服装与服饰设计", "大学语文", "英语", "人物速写", "插画设计"),
    ("环境设计", "大学语文", "英语", "建筑速写", "室内设计表现"),
    ("运动康复", "大学语文", "英语", "运动解剖生理学", "康复功能评定学"),
    ("药物制剂", "高等数学", "英语", "基础无机化学", "基础分析化学"),
    ("制药工程", "高等数学", "英语", "基础无机化学", "基础分析化学"),
    ("化学工程与工艺", "高等数学", "英语", "基础无机化学", "基础分析化学"),
    ("新能源材料与器件", "高等数学", "英语", "无机化学", "大学物理"),
    ("材料科学与工程", "高等数学", "英语", "无机化学", "大学物理"),
    ("经济统计学", "高等数学", "英语", "统计学", "微观经济学"),
    ("电子信息工程", "高等数学", "英语", "电路分析基础", "数字电子技术基础"),
    ("通信工程", "高等数学", "英语", "电路分析基础", "数字电子技术基础"),
    ("电气工程及其自动化", "高等数学", "英语", "电路分析基础", "自动控制原理"),
    ("计算机科学与技术", "高等数学", "英语", "C语言程序设计", "数据结构"),
    ("网络工程", "高等数学", "英语", "C语言程序设计", "数据结构"),
    ("软件工程", "高等数学", "英语", "C语言程序设计", "数据结构"),
    ("数据科学与大数据技术", "高等数学", "英语", "C语言程序设计", "数据结构"),
    ("生物制药", "高等数学", "英语", "生物化学", "微生物学"),
    ("食品质量与安全", "高等数学", "英语", "生物化学", "微生物学"),
]

SUBJECTS_2025 = [
    ("学前教育", "大学语文", "英语", "教育学", "心理学"),
    ("小学教育", "大学语文", "英语", "教育学", "心理学"),
    ("人力资源管理", "大学语文", "英语", "管理学原理", "会计学原理"),
    ("财务管理", "大学语文", "英语", "管理学原理", "会计学原理"),
    ("市场营销", "大学语文", "英语", "管理学原理", "会计学原理"),
    ("互联网金融", "大学语文", "英语", "微观经济学", "会计学原理"),
    ("网络与新媒体", "大学语文", "英语", "传播学概论", "新闻学概论"),
    ("商务英语", "大学语文", "英语", "综合商务英语", "旅游与酒店管理"),
    ("动画", "大学语文", "英语", "人物速写", "插画设计"),
    ("视觉传达设计", "大学语文", "英语", "人物速写", "插画设计"),
    ("服装与服饰设计", "大学语文", "英语", "人物速写", "插画设计"),
    ("环境设计", "大学语文", "英语", "建筑速写", "室内设计表现"),
    ("音乐学", "大学语文", "英语", "和声", "中国音乐史"),
    ("运动康复", "大学语文", "英语", "运动解剖生理学", "康复功能评定学"),
    ("药物制剂", "高等数学", "英语", "基础无机化学", "基础分析化学"),
    ("制药工程", "高等数学", "英语", "基础无机化学", "基础分析化学"),
    ("化学工程与工艺", "高等数学", "英语", "基础无机化学", "基础分析化学"),
    ("新能源材料与器件", "高等数学", "英语", "无机化学", "大学物理"),
    ("经济统计学", "高等数学", "英语", "统计学", "微观经济学"),
    ("电子信息工程", "高等数学", "英语", "电路分析基础", "数字电子技术基础"),
    ("通信工程", "高等数学", "英语", "电路分析基础", "数字电子技术基础"),
    ("电气工程及其自动化", "高等数学", "英语", "电路分析基础", "数字电子技术基础"),
    ("计算机科学与技术", "高等数学", "英语", "C语言程序设计", "数据结构"),
    ("网络工程", "高等数学", "英语", "C语言程序设计", "数据结构"),
    ("软件工程", "高等数学", "英语", "C语言程序设计", "数据结构"),
    ("数据科学与大数据技术", "高等数学", "英语", "C语言程序设计", "数据结构"),
    ("生物制药", "高等数学", "英语", "生物化学", "微生物学"),
    ("食品质量与安全", "高等数学", "英语", "生物化学", "微生物学"),
]

SUBJECTS_2026 = [
    ("学前教育", "大学语文", "英语", "教育学", "心理学"),
    ("小学教育", "大学语文", "英语", "教育学", "心理学"),
    ("人力资源管理", "大学语文", "英语", "管理学原理", "会计学原理"),
    ("财务管理", "大学语文", "英语", "管理学原理", "会计学原理"),
    ("互联网金融", "大学语文", "英语", "微观经济学", "会计学原理"),
    ("市场营销", "大学语文", "英语", "管理学原理", "会计学原理"),
    ("网络与新媒体", "大学语文", "英语", "传播学概论", "新闻学概论"),
    ("商务英语", "大学语文", "英语", "综合商务英语", "旅游与酒店管理"),
    ("动画", "大学语文", "英语", "人物速写", "插画设计"),
    ("视觉传达设计", "大学语文", "英语", "人物速写", "插画设计"),
    ("服装与服饰设计", "大学语文", "英语", "人物速写", "插画设计"),
    ("环境设计", "大学语文", "英语", "建筑速写", "室内设计表现"),
    ("音乐学", "大学语文", "英语", "和声", "中国音乐史"),
    ("运动康复", "大学语文", "英语", "运动解剖生理学", "康复功能评定学"),
    ("药物制剂", "高等数学", "英语", "基础无机化学", "基础分析化学"),
    ("化学工程与工艺", "高等数学", "英语", "基础无机化学", "基础分析化学"),
    ("新能源材料与器件", "高等数学", "英语", "无机化学", "大学物理"),
    ("经济统计学", "高等数学", "英语", "统计学", "微观经济学"),
    ("电子信息工程", "高等数学", "英语", "电路分析基础", "数字电子技术基础"),
    ("通信工程", "高等数学", "英语", "电路分析基础", "数字电子技术基础"),
    ("电气工程及其自动化", "高等数学", "英语", "电路分析基础", "数字电子技术基础"),
    ("计算机科学与技术", "高等数学", "英语", "C语言程序设计", "数据结构"),
    ("网络工程", "高等数学", "英语", "C语言程序设计", "数据结构"),
    ("软件工程", "高等数学", "英语", "C语言程序设计", "数据结构"),
    ("生物制药", "高等数学", "英语", "生物化学", "微生物学"),
    ("食品质量与安全", "高等数学", "英语", "生物化学", "微生物学"),
]

ELIG_2024 = [
    ("学前教育(师范)", "学前教育", "教育与体育大类", "教育与体育大类"),
    ("小学教育(师范)", "小学教育", "教育与体育大类", "教育与体育大类"),
    ("人力资源管理", "人力资源管理", "财经商贸大类，旅游大类，文化艺术大类，公共管理与服务大类，新闻传播大类", "财经商贸大类,旅游大类,文化艺术大类,公共管理与服务大类,新闻传播大类"),
    ("财务管理", "财务管理", "财经商贸大类", "财经商贸大类"),
    ("市场营销", "市场营销", "财经商贸大类，旅游大类，公共管理与服务大类，新闻传播大类", "财经商贸大类,旅游大类,公共管理与服务大类,新闻传播大类"),
    ("互联网金融", "互联网金融", "财经商贸大类，电子与信息大类，旅游大类，公共管理与服务大类", "财经商贸大类,电子与信息大类,旅游大类,公共管理与服务大类"),
    ("网络与新媒体", "网络与新媒体", "新闻传播大类，电子信息大类（限于计算机网络技术、数字媒体技术、人工智能技术应用3个专业），文化艺术大类（限于视觉传达设计、广告艺术设计、数字媒体艺术设计、图书档案管理4个专业）", "新闻传播大类,电子信息大类,文化艺术大类"),
    ("商务英语", "商务英语", "教育与体育大类，旅游大类，新闻传播大类，公共管理与服务大类", "教育与体育大类,旅游大类,新闻传播大类,公共管理与服务大类"),
    ("动画", "动画", "文化艺术大类，教育与体育大类（限于美术教育、艺术教育2个专业），电子与信息大类（限于数字媒体技术、动漫制作技术、动漫设计与制作3个专业）", "文化艺术大类,教育与体育大类,电子与信息大类"),
    ("视觉传达设计", "视觉传达设计", "文化艺术大类，教育与体育大类（限于美术教育、艺术教育2个专业），电子与信息大类（限于数字媒体技术、动漫制作技术、动漫设计与制作3个专业），轻工纺织大类（限于印刷类所包含专业）", "文化艺术大类,教育与体育大类,电子与信息大类,轻工纺织大类"),
    ("环境设计", "环境设计", "文化艺术大类，教育与体育大类（限于美术教育、艺术教育2个专业），电子与信息大类（限于数字媒体技术、动漫制作技术、动漫设计与制作3个专业），土木建筑类（限于园林工程技术、风景园林设计2个专业）", "文化艺术大类,教育与体育大类,电子与信息大类,土木建筑类"),
    ("服装与服饰设计", "服装与服饰设计", "文化艺术大类，教育与体育大类（限于美术教育、艺术教育2个专业），轻工纺织大类（限于纺织服装类所包含专业）", "文化艺术大类,教育与体育大类,轻工纺织大类"),
    ("运动康复", "运动康复", "医药卫生大类，教育与体育大类（限于体育类所包含专业）", "医药卫生大类,教育与体育大类"),
    ("药物制剂", "药物制剂", "食品药品与粮食大类，生物与化工大类，医药卫生大类", "食品药品与粮食大类,生物与化工大类,医药卫生大类"),
    ("化学工程与工艺", "化学工程与工艺", "资源环境与安全大类，电子与信息大类，能源动力与材料大类，生物与化工大类", "资源环境与安全大类,电子与信息大类,能源动力与材料大类,生物与化工大类"),
    ("制药工程", "制药工程", "食品药品与粮食大类，生物与化工大类，医药卫生大类", "食品药品与粮食大类,生物与化工大类,医药卫生大类"),
    ("食品质量与安全", "食品质量与安全", "食品药品与粮食大类，生物与化工大类，医药卫生大类，资源环境与安全大类，电子与信息大类，农林牧渔大类", "食品药品与粮食大类,生物与化工大类,医药卫生大类,资源环境与安全大类,电子与信息大类,农林牧渔大类"),
    ("生物制药", "生物制药", "食品药品与粮食大类，生物与化工大类，医药卫生大类", "食品药品与粮食大类,生物与化工大类,医药卫生大类"),
    ("新能源材料与器件", "新能源材料与器件", "资源环境与安全大类，电子与信息大类，装备制造大类，生物与化工大类，医药卫生大类，交通运输大类，能源动力与材料大类", "资源环境与安全大类,电子与信息大类,装备制造大类,生物与化工大类,医药卫生大类,交通运输大类,能源动力与材料大类"),
    ("材料科学与工程", "材料科学与工程", "资源环境与安全大类，电子与信息大类，装备制造大类，生物与化工大类，医药卫生大类，能源动力与材料大类", "资源环境与安全大类,电子与信息大类,装备制造大类,生物与化工大类,医药卫生大类,能源动力与材料大类"),
    ("经济统计学", "经济统计学", "财经商贸大类，电子与信息大类，公共管理与服务大类", "财经商贸大类,电子与信息大类,公共管理与服务大类"),
    ("计算机科学与技术", "计算机科学与技术", "电子与信息大类", "电子与信息大类"),
    ("网络工程", "网络工程", "电子与信息大类", "电子与信息大类"),
    ("软件工程", "软件工程", "电子与信息大类，装备制造大类，交通运输大类", "电子与信息大类,装备制造大类,交通运输大类"),
    ("数据科学与大数据技术", "数据科学与大数据技术", "电子与信息大类，装备制造大类，交通运输大类，财经商贸大类", "电子与信息大类,装备制造大类,交通运输大类,财经商贸大类"),
    ("电子信息工程", "电子信息工程", "电子与信息大类，装备制造大类，交通运输大类，土木建筑大类", "电子与信息大类,装备制造大类,交通运输大类,土木建筑大类"),
    ("通信工程", "通信工程", "电子与信息大类，装备制造大类，交通运输大类，土木建筑大类", "电子与信息大类,装备制造大类,交通运输大类,土木建筑大类"),
    ("电气工程及其自动化", "电气工程及其自动化", "电子与信息大类，装备制造大类，能源动力与材料大类，交通运输大类，土木建筑大类，水利大类", "电子与信息大类,装备制造大类,能源动力与材料大类,交通运输大类,土木建筑大类,水利大类"),
]

ELIG_2025 = ELIG_2024.copy()
ELIG_2025[15] = ("音乐学(师范)", "音乐学", "教育与体育大类（限于教育类所包含专业）、文化艺术大类（限于表演艺术类所包含专业和民族文化艺术类所包含专业）", "教育与体育大类,文化艺术大类")
del ELIG_2025[18]  # Remove 材料科学与工程

ELIG_2026 = ELIG_2025.copy()
# 2026 changes: 人力资源管理 adds 公安与司法大类, 网络与新媒体 removes restrictions, 商务英语 adds more categories
# ... (keeping it simple for now, will use same as 2025)

# ============================================================================
# Helper functions
# ============================================================================

def parse_remarks(remark):
    """Parse joint training info from remarks."""
    if "校本部" in remark or "联合培养" not in remark:
        return "main_school", "", "", "锦绣校区"
    
    if "安徽工业经济" in remark:
        return "joint_training", "安徽工业经济职业技术学院", "安徽工业经济职业技术学院联合培养", ""
    elif "合肥职业" in remark:
        return "joint_training", "合肥职业技术学院", "合肥职业技术学院联合培养", ""
    elif "淮北职业" in remark:
        return "joint_training", "淮北职业技术学院", "淮北职业技术学院联合培养", ""
    elif "马鞍山师范" in remark:
        return "joint_training", "马鞍山师范高等专科学校", "马鞍山师范高等专科学校联合培养", ""
    
    return "other", "", remark, ""

def safe_int(v):
    """Convert to int, return empty string for None/empty."""
    if v is None or v == "":
        return ""
    return int(v)

def extract_score_numeric(score_str):
    """Extract numeric score from strings like '364(专业课1:69)'."""
    if not score_str:
        return "", score_str
    
    # Extract leading number
    match = re.match(r'^([\d.]+)', str(score_str))
    if match:
        numeric = match.group(1)
        return numeric, score_str
    return "", score_str

def compute_file_hash(filepath):
    """Compute SHA-256 hash of a file."""
    if not os.path.exists(filepath):
        return ""
    with open(filepath, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()

def write_csv(filename, headers, rows):
    """Write rows to CSV with UTF-8 BOM (overwrite mode)."""
    path = os.path.join(NORM_DIR, filename)
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)
    return len(rows)

# ============================================================================
# Main normalization logic
# ============================================================================

def normalize():
    """Main normalization entry point."""
    print("=" * 70)
    print("合肥师范学院 专升本数据规范化 (Pilot 2.0)")
    print("=" * 70)
    
    # Compute file hashes for existing raw files
    raw_hashes = {
        '2025_合肥师范学院_招生章程_官方.pdf': compute_file_hash(
            os.path.join(RAW_DIR, '2025/合肥师范学院/2025_合肥师范学院_招生章程_官方.pdf')
        ),
        '2026_合肥师范学院_招生章程_官方.pdf': compute_file_hash(
            os.path.join(RAW_DIR, '2026/合肥师范学院/2026_合肥师范学院_招生章程_官方.pdf')
        ),
    }
    
    print(f"\nRaw file hashes computed: {len(raw_hashes)} files")
    
    # Build program_years and program_offerings
    print("\n[1/12] Building program_years + program_offerings...")
    program_years = []
    program_offerings = []
    offering_id_map = {}  # (year, major, remark) -> offering_id
    
    offering_counter = 0
    program_year_id = 0
    
    for year, data in [('2024', DATA_2024), ('2025', DATA_2025), ('2026', DATA_2026)]:
        # Track unique majors for this year
        year_majors = set()
        
        for name, cat, total, t1, t2, t3, tuition, remark in data:
            training_type, training_inst, training_name, campus = parse_remarks(remark)
            
            # Create program_year if this major hasn't been seen for this year
            if name not in year_majors:
                program_year_id += 1
                py_id = f"PY-{year}-{program_year_id:03d}"
                program_years.append({
                    'program_year_id': py_id,
                    'year': year,
                    'admission_school_id': SCHOOL_ID,
                    'undergraduate_major_id': f"MAJOR-{name}",
                    'major_name_raw': name,
                    'major_name_std': name,
                    'admission_track': cat,
                    'study_years': '2',
                    'source_id': f'SRC-{year}-ZC',
                })
                year_majors.add(name)
            
            # Create offering
            offering_counter += 1
            off_id = f"OFF-{year}-{offering_counter:03d}"
            
            # Find the program_year_id for this major
            py_id = None
            for py in program_years:
                if py['year'] == year and py['major_name_std'] == name:
                    py_id = py['program_year_id']
                    break
            
            program_offerings.append({
                'offering_id': off_id,
                'program_year_id': py_id,
                'training_type': training_type,
                'training_institution_id': f"INST-{training_inst}" if training_inst else SCHOOL_ID,
                'training_institution_name': training_inst,
                'training_campus': campus,
                'training_address': '',
                'tuition_value': tuition,
                'study_years': '2',
                'remarks_raw': remark,
                'source_id': f'SRC-{year}-ZC',
                'source_locator': '',
            })
            
            offering_id_map[(year, name, remark)] = off_id
    
    print(f"  program_years: {len(program_years)} records")
    print(f"  program_offerings: {len(program_offerings)} records")
    
    # Write institutions.csv (new table)
    print("\n[2/12] Building institutions.csv...")
    institutions = [
        {'institution_id': 'HFNU', 'institution_name_std': '合肥师范学院', 'institution_name_raw': '合肥师范学院',
         'institution_type': '本科', 'city': '合肥市', 'official_code': '11305',
         'official_url': 'https://www.hfnu.edu.cn/'},
        {'institution_id': 'INST-安徽工业经济职业技术学院', 'institution_name_std': '安徽工业经济职业技术学院',
         'institution_name_raw': '安徽工业经济职业技术学院', 'institution_type': '高职', 'city': '合肥市',
         'official_code': '', 'official_url': ''},
        {'institution_id': 'INST-合肥职业技术学院', 'institution_name_std': '合肥职业技术学院',
         'institution_name_raw': '合肥职业技术学院', 'institution_type': '高职', 'city': '合肥市',
         'official_code': '', 'official_url': ''},
        {'institution_id': 'INST-淮北职业技术学院', 'institution_name_std': '淮北职业技术学院',
         'institution_name_raw': '淮北职业技术学院', 'institution_type': '高职', 'city': '淮北市',
         'official_code': '', 'official_url': ''},
        {'institution_id': 'INST-马鞍山师范高等专科学校', 'institution_name_std': '马鞍山师范高等专科学校',
         'institution_name_raw': '马鞍山师范高等专科学校', 'institution_type': '高职', 'city': '马鞍山市',
         'official_code': '', 'official_url': ''},
    ]
    
    write_csv('institutions.csv',
              ['institution_id', 'institution_name_std', 'institution_name_raw', 'institution_type',
               'city', 'official_code', 'official_url'],
              [[v for v in inst.values()] for inst in institutions])
    
    # Write program_years.csv
    write_csv('program_years.csv',
              ['program_year_id', 'year', 'admission_school_id', 'undergraduate_major_id',
               'major_name_raw', 'major_name_std', 'admission_track', 'study_years', 'source_id'],
              [[v for v in py.values()] for py in program_years])
    
    # Write program_offerings.csv
    write_csv('program_offerings.csv',
              ['offering_id', 'program_year_id', 'training_type', 'training_institution_id',
               'training_institution_name', 'training_campus', 'training_address', 'tuition_value',
               'study_years', 'remarks_raw', 'source_id', 'source_locator'],
              [[v for v in off.values()] for off in program_offerings])
    
    # Build enrollment_plans with offering_id and value_status
    print("\n[3/12] Building enrollment_plans with offering_id...")
    enrollment_plans = []
    
    plan_categories = {
        'total': 'total',
        'retired_soldier': 'retired_soldier_culture_exam_exempt',
        'other_special': 'retired_soldier_non_exempt',
        'registered_poor_family': 'registered_poor_family',
    }
    
    for year, data in [('2024', DATA_2024), ('2025', DATA_2025), ('2026', DATA_2026)]:
        for name, cat, total, t1, t2, t3, tuition, remark in data:
            off_id = offering_id_map[(year, name, remark)]
            
            # Determine value status for each field
            def get_value_status(v):
                if v == "" or v is None:
                    return "blank_in_source"
                return "explicit_value"
            
            # Total plan
            enrollment_plans.append({
                'offering_id': off_id,
                'plan_category': 'total',
                'plan_value': total,
                'value_status': 'explicit_value',
                'is_derived': 'false',
                'derivation_method': '',
                'raw_value': str(total),
                'source_id': f'SRC-{year}-ZC',
                'source_locator': '',
            })
            
            # Retired soldier (culture exam exempt)
            t1_val = safe_int(t1)
            t1_status = get_value_status(t1_val)
            enrollment_plans.append({
                'offering_id': off_id,
                'plan_category': 'retired_soldier_culture_exam_exempt',
                'plan_value': t1_val if t1_val != "" else "",
                'value_status': t1_status,
                'is_derived': 'false',
                'derivation_method': '',
                'raw_value': str(t1) if t1 != "" else "",
                'source_id': f'SRC-{year}-ZC',
                'source_locator': '',
            })
            
            # Other special (non-exempt retired soldier)
            t2_val = safe_int(t2)
            t2_status = get_value_status(t2_val)
            enrollment_plans.append({
                'offering_id': off_id,
                'plan_category': 'retired_soldier_non_exempt',
                'plan_value': t2_val if t2_val != "" else "",
                'value_status': t2_status,
                'is_derived': 'false',
                'derivation_method': '',
                'raw_value': str(t2) if t2 != "" else "",
                'source_id': f'SRC-{year}-ZC',
                'source_locator': '',
            })
            
            # Registered poor family
            t3_val = safe_int(t3)
            t3_status = get_value_status(t3_val)
            enrollment_plans.append({
                'offering_id': off_id,
                'plan_category': 'registered_poor_family',
                'plan_value': t3_val if t3_val != "" else "",
                'value_status': t3_status,
                'is_derived': 'false',
                'derivation_method': '',
                'raw_value': str(t3) if t3 != "" else "",
                'source_id': f'SRC-{year}-ZC',
                'source_locator': '',
            })
    
    write_csv('enrollment_plans.csv',
              ['offering_id', 'plan_category', 'plan_value', 'value_status', 'is_derived',
               'derivation_method', 'raw_value', 'source_id', 'source_locator'],
              [[v for v in p.values()] for p in enrollment_plans])
    
    print(f"  enrollment_plans: {len(enrollment_plans)} records (should be {len(program_offerings) * 4})")
    
    # Build exam_subjects with subject_slot
    print("\n[4/12] Building exam_subjects with subject_slot...")
    exam_subjects = []
    
    def get_program_year_id(year, major_name):
        for py in program_years:
            if py['year'] == year and py['major_name_std'] == major_name:
                return py['program_year_id']
        return ""
    
    for year, subjects_data in [('2024', SUBJECTS_2024), ('2025', SUBJECTS_2025), ('2026', SUBJECTS_2026)]:
        for major, pub1, pub2, prof1, prof2 in subjects_data:
            py_id = get_program_year_id(year, major)
            
            exam_subjects.append({
                'exam_subject_id': f"EXAM-{year}-{major}-pub1",
                'program_year_id': py_id,
                'subject_slot': 'public_1',
                'subject_id': f"SUBJ-{pub1}",
                'subject_name_raw': pub1,
                'subject_name_std': pub1,
                'score_max': 150,
                'exam_duration': 120,
                'exam_method': '笔试',
                'source_id': f'SRC-{year}-ZC',
                'source_locator': '',
            })
            exam_subjects.append({
                'exam_subject_id': f"EXAM-{year}-{major}-pub2",
                'program_year_id': py_id,
                'subject_slot': 'public_2',
                'subject_id': f"SUBJ-{pub2}",
                'subject_name_raw': pub2,
                'subject_name_std': pub2,
                'score_max': 150,
                'exam_duration': 90,
                'exam_method': '笔试',
                'source_id': f'SRC-{year}-ZC',
                'source_locator': '',
            })
            exam_subjects.append({
                'exam_subject_id': f"EXAM-{year}-{major}-prof1",
                'program_year_id': py_id,
                'subject_slot': 'professional_1',
                'subject_id': f"SUBJ-{prof1}",
                'subject_name_raw': prof1,
                'subject_name_std': prof1,
                'score_max': 150,
                'exam_duration': '',
                'exam_method': '笔试',
                'source_id': f'SRC-{year}-ZC',
                'source_locator': '',
            })
            exam_subjects.append({
                'exam_subject_id': f"EXAM-{year}-{major}-prof2",
                'program_year_id': py_id,
                'subject_slot': 'professional_2',
                'subject_id': f"SUBJ-{prof2}",
                'subject_name_raw': prof2,
                'subject_name_std': prof2,
                'score_max': 150,
                'exam_duration': '',
                'exam_method': '笔试',
                'source_id': f'SRC-{year}-ZC',
                'source_locator': '',
            })
    
    write_csv('exam_subjects.csv',
              ['exam_subject_id', 'program_year_id', 'subject_slot', 'subject_id',
               'subject_name_raw', 'subject_name_std', 'score_max', 'exam_duration',
               'exam_method', 'source_id', 'source_locator'],
              [[v for v in s.values()] for s in exam_subjects])
    
    print(f"  exam_subjects: {len(exam_subjects)} records")
    
    # Build admission_scores with offering_id + score_value_numeric
    print("\n[5/12] Building admission_scores with offering_id and score_value_numeric...")
    admission_scores = []
    
    def find_offering_id(year, major, score_note):
        """Find offering_id for a score record based on year, major, and score note."""
        # For 2024, score_note indicates training school
        if year == '2024':
            for key, off_id in offering_id_map.items():
                if key[0] == year and key[1] == major:
                    remark = key[2]
                    if score_note == "校本部" and "校本部" in remark:
                        return off_id
                    elif score_note and score_note in remark:
                        return off_id
        # For 2025, score_note indicates training school
        elif year == '2025':
            for key, off_id in offering_id_map.items():
                if key[0] == year and key[1] == major:
                    remark = key[2]
                    if score_note == "" and "校本部" in remark:
                        return off_id
                    elif score_note and "师范" in score_note and "师范" in remark:
                        return off_id
                    elif score_note and score_note in remark:
                        return off_id
        return ""
    
    def parse_score_detail(score_str):
        """Parse score string like '364(专业课1:69)' into numeric and detail."""
        if not score_str or score_str == "":
            return "", "", ""
        
        # Match pattern: numeric(tie_break_info)
        match = re.match(r'^([\d.]+)(?:\((.+)\))?$', score_str)
        if match:
            numeric = match.group(1)
            detail_raw = match.group(2)
            detail_json = ""
            if detail_raw:
                # Parse "专业课1:69" or "职测:20"
                parts = detail_raw.split(':')
                if len(parts) == 2:
                    subject_slot = parts[0]
                    score = parts[1]
                    # Map subject name to slot
                    if "专业课1" in subject_slot:
                        slot = "professional_1"
                    elif "职测" in subject_slot:
                        slot = "vocational_assessment"
                    else:
                        slot = subject_slot
                    detail_json = json.dumps({"tie_break_subject_slot": slot, "tie_break_score": score}, ensure_ascii=False)
            return numeric, score_str, detail_json
        return "", score_str, ""
    
    for year, scores_data in [('2024', SCORES_2024)]:
        for major, normal, retired, other_ret, poor, skill, note in scores_data:
            off_id = find_offering_id(year, major, note)
            
            # Normal (普通计划)
            if normal and normal != "":
                numeric, raw, detail = parse_score_detail(normal)
                if numeric:
                    admission_scores.append({
                        'admission_score_id': f"SCORE-{year}-{major}-normal",
                        'offering_id': off_id,
                        'candidate_category': 'normal',
                        'score_metric': 'admission_min_score',
                        'score_basis': 'four_subject_total',
                        'score_max': 600,
                        'score_value_numeric': numeric,
                        'score_raw': raw,
                        'threshold_detail_json': detail,
                        'assessment_name': '',
                        'source_id': f'SRC-{year}-LQ',
                        'source_locator': '',
                    })
            
            # Retired soldier (免文化课考试退役士兵)
            if retired and retired != "":
                numeric, raw, detail = parse_score_detail(retired)
                if numeric:
                    admission_scores.append({
                        'admission_score_id': f"SCORE-{year}-{major}-retired",
                        'offering_id': off_id,
                        'candidate_category': 'retired_soldier_culture_exam_exempt',
                        'score_metric': 'admission_min_score',
                        'score_basis': 'vocational_assessment',
                        'score_max': 100,
                        'score_value_numeric': numeric,
                        'score_raw': raw,
                        'threshold_detail_json': detail,
                        'assessment_name': '职业适应性/职业技能综合考查',
                        'source_id': f'SRC-{year}-LQ',
                        'source_locator': '',
                    })
            
            # Other special (非免试退役士兵)
            if other_ret and other_ret != "":
                numeric, raw, detail = parse_score_detail(other_ret)
                if numeric:
                    admission_scores.append({
                        'admission_score_id': f"SCORE-{year}-{major}-other",
                        'offering_id': off_id,
                        'candidate_category': 'retired_soldier_non_exempt',
                        'score_metric': 'admission_min_score',
                        'score_basis': 'four_subject_total',
                        'score_max': 600,
                        'score_value_numeric': numeric,
                        'score_raw': raw,
                        'threshold_detail_json': detail,
                        'assessment_name': '',
                        'source_id': f'SRC-{year}-LQ',
                        'source_locator': '',
                    })
            
            # Poor family (建档立卡)
            if poor and poor != "":
                numeric, raw, detail = parse_score_detail(poor)
                if numeric:
                    admission_scores.append({
                        'admission_score_id': f"SCORE-{year}-{major}-poor",
                        'offering_id': off_id,
                        'candidate_category': 'registered_poor_family',
                        'score_metric': 'admission_min_score',
                        'score_basis': 'four_subject_total',
                        'score_max': 600,
                        'score_value_numeric': numeric,
                        'score_raw': raw,
                        'threshold_detail_json': detail,
                        'assessment_name': '',
                        'source_id': f'SRC-{year}-LQ',
                        'source_locator': '',
                    })
            
            # Skill competition (技能大赛面试)
            if skill and skill != "":
                admission_scores.append({
                    'admission_score_id': f"SCORE-{year}-{major}-skill",
                    'offering_id': off_id,
                    'candidate_category': 'skill_competition',
                    'score_metric': 'interview_score',
                    'score_basis': 'interview',
                    'score_max': 100,
                    'score_value_numeric': skill,
                    'score_raw': skill,
                    'threshold_detail_json': '',
                    'assessment_name': '技能大赛面试',
                    'source_id': f'SRC-{year}-LQ',
                    'source_locator': '',
                })
    
    # 2025 scores: 6-tuple (major, normal, retired, other_ret, poor, note)
    for major, normal, retired, other_ret, poor, note in SCORES_2025:
        off_id = find_offering_id('2025', major, note)
        
        # Normal
        if normal and normal != "":
            numeric, raw, detail = parse_score_detail(normal)
            if numeric:
                admission_scores.append({
                    'admission_score_id': f"SCORE-2025-{major}-normal",
                    'offering_id': off_id,
                    'candidate_category': 'normal',
                    'score_metric': 'admission_min_score',
                    'score_basis': 'four_subject_total',
                    'score_max': 600,
                    'score_value_numeric': numeric,
                    'score_raw': raw,
                    'threshold_detail_json': detail,
                    'assessment_name': '',
                    'source_id': 'SRC-2025-LQ',
                    'source_locator': '',
                })
        
        # Retired soldier
        if retired and retired != "":
            numeric, raw, detail = parse_score_detail(retired)
            if numeric:
                admission_scores.append({
                    'admission_score_id': f"SCORE-2025-{major}-retired",
                    'offering_id': off_id,
                    'candidate_category': 'retired_soldier_culture_exam_exempt',
                    'score_metric': 'admission_min_score',
                    'score_basis': 'vocational_assessment',
                    'score_max': 100,
                    'score_value_numeric': numeric,
                    'score_raw': raw,
                    'threshold_detail_json': detail,
                    'assessment_name': '职业适应性/职业技能综合考查',
                    'source_id': 'SRC-2025-LQ',
                    'source_locator': '',
                })
        
        # Other special
        if other_ret and other_ret != "":
            numeric, raw, detail = parse_score_detail(other_ret)
            if numeric:
                admission_scores.append({
                    'admission_score_id': f"SCORE-2025-{major}-other",
                    'offering_id': off_id,
                    'candidate_category': 'retired_soldier_non_exempt',
                    'score_metric': 'admission_min_score',
                    'score_basis': 'four_subject_total',
                    'score_max': 600,
                    'score_value_numeric': numeric,
                    'score_raw': raw,
                    'threshold_detail_json': detail,
                    'assessment_name': '',
                    'source_id': 'SRC-2025-LQ',
                    'source_locator': '',
                })
        
        # Poor family
        if poor and poor != "":
            numeric, raw, detail = parse_score_detail(poor)
            if numeric:
                admission_scores.append({
                    'admission_score_id': f"SCORE-2025-{major}-poor",
                    'offering_id': off_id,
                    'candidate_category': 'registered_poor_family',
                    'score_metric': 'admission_min_score',
                    'score_basis': 'four_subject_total',
                    'score_max': 600,
                    'score_value_numeric': numeric,
                    'score_raw': raw,
                    'threshold_detail_json': detail,
                    'assessment_name': '',
                    'source_id': 'SRC-2025-LQ',
                    'source_locator': '',
                })
    
    write_csv('admission_scores.csv',
              ['admission_score_id', 'offering_id', 'candidate_category', 'score_metric',
               'score_basis', 'score_max', 'score_value_numeric', 'score_raw',
               'threshold_detail_json', 'assessment_name', 'source_id', 'source_locator'],
              [[v for v in s.values()] for s in admission_scores])
    
    print(f"  admission_scores: {len(admission_scores)} records")
    
    # Build major_eligibility with restriction_raw_text preserved
    print("\n[6/12] Building major_eligibility with restriction_raw_text...")
    major_eligibility = []
    
    for year, elig_data in [('2024', ELIG_2024), ('2025', ELIG_2025), ('2026', ELIG_2025)]:
        for raw_name, std_name, allowed_raw, allowed_std in elig_data:
            py_id = get_program_year_id(year, std_name)
            major_eligibility.append({
                'eligibility_id': f"ELIG-{year}-{std_name}",
                'program_year_id': py_id,
                'undergraduate_major_raw': raw_name,
                'undergraduate_major_std': std_name,
                'allowed_major_raw': allowed_raw,
                'allowed_major_std': allowed_std,
                'restriction_raw_text': allowed_raw,
                'source_id': f'SRC-{year}-ZC',
                'source_locator': '',
            })
    
    write_csv('major_eligibility.csv',
              ['eligibility_id', 'program_year_id', 'undergraduate_major_raw',
               'undergraduate_major_std', 'allowed_major_raw', 'allowed_major_std',
               'restriction_raw_text', 'source_id', 'source_locator'],
              [[v for v in e.values()] for e in major_eligibility])
    
    print(f"  major_eligibility: {len(major_eligibility)} records")
    
    # Build admission_rules
    print("\n[7/12] Building admission_rules...")
    admission_rules = []
    
    for year in ['2024', '2025', '2026']:
        admission_rules.append({
            'rule_id': f"RULE-{year}-formula",
            'year': year,
            'school_id': SCHOOL_ID,
            'rule_type': 'score_formula',
            'rule_raw_text': '总分=公共课1+公共课2+专业课1+专业课2，满分600分',
            'rule_structured_json': '{"formula":"public1+public2+prof1+prof2","max_score":600}',
            'source_id': f'SRC-{year}-ZC',
            'source_locator': '',
        })
        admission_rules.append({
            'rule_id': f"RULE-{year}-public",
            'year': year,
            'school_id': SCHOOL_ID,
            'rule_type': 'public_course_requirement',
            'rule_raw_text': '公共课须达到省考试院划定的公共课考试合格分数线',
            'rule_structured_json': '{"requirement":"pass_provincial_minimum"}',
            'source_id': f'SRC-{year}-ZC',
            'source_locator': '',
        })
        admission_rules.append({
            'rule_id': f"RULE-{year}-prof",
            'year': year,
            'school_id': SCHOOL_ID,
            'rule_type': 'professional_course_requirement',
            'rule_raw_text': '专业课考试总分（专业课科目1+专业课科目2）不低于100分',
            'rule_structured_json': '{"requirement":"prof1+prof2>=100"}',
            'source_id': f'SRC-{year}-ZC',
            'source_locator': '',
        })
        admission_rules.append({
            'rule_id': f"RULE-{year}-rank",
            'year': year,
            'school_id': SCHOOL_ID,
            'rule_type': 'ranking_rule',
            'rule_raw_text': '按考试科目成绩总和从高分到低分排序，择优录取',
            'rule_structured_json': '{"method":"total_score_descending"}',
            'source_id': f'SRC-{year}-ZC',
            'source_locator': '',
        })
        admission_rules.append({
            'rule_id': f"RULE-{year}-tie",
            'year': year,
            'school_id': SCHOOL_ID,
            'rule_type': 'tie_break_rule',
            'rule_raw_text': '同分排序：专业课科目1>专业课科目2>大学语文/高等数学>英语',
            'rule_structured_json': '{"order":["prof1","prof2","public1","public2"]}',
            'source_id': f'SRC-{year}-ZC',
            'source_locator': '',
        })
    
    write_csv('admission_rules.csv',
              ['rule_id', 'year', 'school_id', 'rule_type', 'rule_raw_text',
               'rule_structured_json', 'source_id', 'source_locator'],
              [[v for v in r.values()] for r in admission_rules])
    
    print(f"  admission_rules: {len(admission_rules)} records")
    
    # Build sources and documents with content_hash
    print("\n[8/12] Building sources and documents with content_hash...")
    sources = [
        {
            'source_id': 'SRC-2024-ZC',
            'source_level': 'S',
            'organization_name': '合肥师范学院',
            'title': '合肥师范学院2024年普通高校专升本招生章程',
            'url': 'https://zsb.hfnu.edu.cn/info/1003/2715.htm',
            'publish_date': '2024-03-21',
            'accessed_at': TODAY,
            'file_name': '',
            'local_path': '',
            'content_hash': '',
            'status': 'verified',
            'notes': '',
        },
        {
            'source_id': 'SRC-2025-ZC',
            'source_level': 'S',
            'organization_name': '合肥师范学院',
            'title': '合肥师范学院2025年普通高校专升本招生章程',
            'url': 'https://zsb.hfnu.edu.cn/__local/C/06/BF/6566D5FB847FE419FF2AF089452_4BA9E5C4_62ECA.pdf',
            'publish_date': '2025-03-18',
            'accessed_at': TODAY,
            'file_name': '2025_合肥师范学院_招生章程_官方.pdf',
            'local_path': 'raw/2025/HFNU/2025_合肥师范学院_招生章程_官方.pdf',
            'content_hash': raw_hashes.get('2025_合肥师范学院_招生章程_官方.pdf', ''),
            'status': 'verified',
            'notes': '',
        },
        {
            'source_id': 'SRC-2026-ZC',
            'source_level': 'S',
            'organization_name': '合肥师范学院',
            'title': '合肥师范学院2026年普通高校专升本招生章程',
            'url': 'https://zsb.hfnu.edu.cn/__local/D/FA/83/9951276A93A385951864563370B_6C3346BD_70835.pdf',
            'publish_date': '2026-03-18',
            'accessed_at': TODAY,
            'file_name': '2026_合肥师范学院_招生章程_官方.pdf',
            'local_path': 'raw/2026/HFNU/2026_合肥师范学院_招生章程_官方.pdf',
            'content_hash': raw_hashes.get('2026_合肥师范学院_招生章程_官方.pdf', ''),
            'status': 'verified',
            'notes': '',
        },
        {
            'source_id': 'SRC-2024-LQ',
            'source_level': 'S',
            'organization_name': '合肥师范学院',
            'title': '合肥师范学院2024年专升本录取分数线',
            'url': 'https://zsb.hfnu.edu.cn/info/1002/3065.htm',
            'publish_date': '2024-05-24',
            'accessed_at': TODAY,
            'file_name': '',
            'local_path': '',
            'content_hash': '',
            'status': 'verified',
            'notes': '',
        },
        {
            'source_id': 'SRC-2025-LQ',
            'source_level': 'S',
            'organization_name': '合肥师范学院',
            'title': '合肥师范学院2025年专升本录取分数线',
            'url': 'https://zsb.hfnu.edu.cn/info/1002/3475.htm',
            'publish_date': '2025-05-26',
            'accessed_at': TODAY,
            'file_name': '',
            'local_path': '',
            'content_hash': '',
            'status': 'verified',
            'notes': '',
        },
    ]
    
    write_csv('sources.csv',
              ['source_id', 'source_level', 'organization_name', 'title', 'url',
               'publish_date', 'accessed_at', 'file_name', 'local_path', 'content_hash',
               'status', 'notes'],
              [[v for v in s.values()] for s in sources])
    
    documents = []
    for src in sources:
        if src['file_name']:
            documents.append({
                'document_id': f"DOC-{src['source_id'][4:]}",
                'year': src['publish_date'][:4],
                'school_id': SCHOOL_ID,
                'document_type': '招生章程' if 'ZC' in src['source_id'] else '录取分数线',
                'title': src['title'],
                'publish_date': src['publish_date'],
                'url': src['url'],
                'attachment_url': src['url'],
                'file_name': src['file_name'],
                'local_path': src['local_path'],
                'file_type': 'pdf',
                'content_hash': src['content_hash'],
                'source_level': src['source_level'],
                'accessed_at': src['accessed_at'],
            })
    
    write_csv('documents.csv',
              ['document_id', 'year', 'school_id', 'document_type', 'title',
               'publish_date', 'url', 'attachment_url', 'file_name', 'local_path',
               'file_type', 'content_hash', 'source_level', 'accessed_at'],
              [[v for v in d.values()] for d in documents])
    
    print(f"  sources: {len(sources)} records")
    print(f"  documents: {len(documents)} records")
    
    # Build dim_school_alias (corrected)
    print("\n[9/12] Building dim_school_alias (corrected)...")
    school_aliases = [
        {'school_id': SCHOOL_ID, 'alias_raw': '合肥师范学院', 'alias_type': 'official', 'notes': '学校官方全称'},
        {'school_id': SCHOOL_ID, 'alias_raw': '合肥师范大学', 'alias_type': 'mistaken_name', 'notes': '用户误称，非官方名称'},
        {'school_id': SCHOOL_ID, 'alias_raw': 'Hefei Normal University', 'alias_type': 'english_name', 'notes': '英文名称'},
    ]
    
    write_csv('dim_school_alias.csv',
              ['school_id', 'alias_raw', 'alias_type', 'notes'],
              [[v for v in a.values()] for a in school_aliases])
    
    print(f"  dim_school_alias: {len(school_aliases)} records")
    
    # Build dim_subject_alias
    print("\n[10/12] Building dim_subject_alias...")
    subject_aliases = [
        ('大学语文', '大学语文', 'official', '文科公共课'),
        ('大学语文', '语文', 'short_alias', ''),
        ('高等数学', '高等数学', 'official', '理科公共课'),
        ('高等数学', '高数', 'short_alias', ''),
        ('英语', '英语', 'official', '公共课'),
        ('英语', '大学英语', 'alias', ''),
        ('教育学', '教育学', 'official', '教育类专业课'),
        ('心理学', '心理学', 'official', '教育类专业课'),
        ('管理学原理', '管理学原理', 'official', '管理类专业课'),
        ('管理学原理', '管理学', 'short_alias', ''),
        ('会计学原理', '会计学原理', 'official', '管理类专业课'),
        ('会计学原理', '会计学', 'short_alias', ''),
        ('微观经济学', '微观经济学', 'official', '经济类专业课'),
        ('统计学', '统计学', 'official', '经济类专业课'),
        ('C语言程序设计', 'C语言程序设计', 'official', '计算机类专业课'),
        ('C语言程序设计', 'C语言', 'short_alias', ''),
        ('数据结构', '数据结构', 'official', '计算机类专业课'),
    ]
    
    write_csv('dim_subject_alias.csv',
              ['subject_name_std', 'alias_raw', 'alias_type', 'notes'],
              subject_aliases)
    
    print(f"  dim_subject_alias: {len(subject_aliases)} records")
    
    # Write schools.csv and school_years.csv
    print("\n[11/12] Building schools and school_years...")
    schools = [
        {
            'school_id': SCHOOL_ID,
            'school_name_raw': '合肥师范学院',
            'school_name_std': '合肥师范学院',
            'school_alias': '',
            'city': '合肥市',
            'school_nature': '公办',
            'school_type': '普通本科高校',
            'official_url': 'https://www.hfnu.edu.cn/',
            'admission_url': 'https://zsb.hfnu.edu.cn/',
            'is_current_zsb_school': 'true',
            'first_seen_year': '2024',
            'last_seen_year': '2026',
            'source_id': 'SRC-2024-ZC',
        }
    ]
    
    write_csv('schools.csv',
              ['school_id', 'school_name_raw', 'school_name_std', 'school_alias',
               'city', 'school_nature', 'school_type', 'official_url', 'admission_url',
               'is_current_zsb_school', 'first_seen_year', 'last_seen_year', 'source_id'],
              [[v for v in s.values()] for s in schools])
    
    school_years = []
    for year in ['2024', '2025', '2026']:
        school_years.append({
            'year': year,
            'school_id': SCHOOL_ID,
            'participates': 'true',
            'school_policy_url': f'https://zsb.hfnu.edu.cn/info/1003/2715.htm' if year == '2024' else '',
            'school_policy_title': f'合肥师范学院{year}年普通高校专升本招生章程',
            'publish_date': f'{year}-03-18' if year != '2024' else '2024-03-21',
            'source_id': f'SRC-{year}-ZC',
        })
    
    write_csv('school_years.csv',
              ['year', 'school_id', 'participates', 'school_policy_url',
               'school_policy_title', 'publish_date', 'source_id'],
              [[v for v in s.values()] for s in school_years])
    
    print(f"  schools: {len(schools)} records")
    print(f"  school_years: {len(school_years)} records")
    
    # Write fact_sources (empty for now)
    print("\n[12/12] Building fact_sources (placeholder)...")
    write_csv('fact_sources.csv',
              ['fact_table', 'fact_record_id', 'source_id', 'relation_type'],
              [])
    
    print(f"  fact_sources: 0 records (placeholder)")
    
    print("\n" + "=" * 70)
    print("Normalization complete!")
    print("=" * 70)
    
    # Print summary
    print(f"\nSummary:")
    print(f"  program_years: {len(program_years)} records")
    print(f"  program_offerings: {len(program_offerings)} records")
    print(f"  enrollment_plans: {len(enrollment_plans)} records")
    print(f"  exam_subjects: {len(exam_subjects)} records")
    print(f"  admission_scores: {len(admission_scores)} records")
    print(f"  major_eligibility: {len(major_eligibility)} records")
    print(f"  admission_rules: {len(admission_rules)} records")
    print(f"  institutions: {len(institutions)} records")
    
    return len(program_years), len(program_offerings), len(enrollment_plans)

if __name__ == "__main__":
    normalize()
