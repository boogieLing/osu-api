# -*- coding: utf-8 -*-
# Author： BoogieLing
# Datetime： 2022/9/15 23:19 
# IDE： PyCharm
# from bit to bilibili
import os
import time

DOWNLOAD_RES_PATH = "download"
PROJECT_PATH = os.curdir
IMAGE_TYPE = (".jpg", ".png", ".bmp", ".gif")
MUSIC_TYPE = (".wav", ".mp3", ".flac", ".ape", ".wv")
# -----------------------系统调试------------------------------------
DEBUG = True
# -----------------------日志-----------------------------------------
LOG_DIR = os.path.join(os.getcwd(), f'logs/{time.strftime("%Y-%m-%d")}.log')
LOG_FORMAT = '<level>{level: <8}</level>  <green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> - <cyan>{name}</cyan>:<cyan>{' \
             'function}</cyan> - <level>{message}</level> '

PROJECT_NAME = "osu-api"
VERSION = "v1.0.0"
DESCRIPTION = "Get some images and music!"
# -----------------------TencentCos-----------------------------------------
OSU_DIR = "osu/"
OSU_CATEGORY_LIST = [
    "Aisaka Taiga/", "Hatsune Miku/", "Touhou Project/", "k-on/", "one piece/",
    "日语-上架时间/", "社区喜爱-上架时间/"
]
OSU_IMG_DIR = "imgs/"