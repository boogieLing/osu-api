# -*- coding: utf-8 -*-
# Author： BoogieLing
# Datetime： 2022/9/15 23:19 
# IDE： PyCharm
# from bit to bilibili
import os
import time

DOWNLOAD_RES_PATH = "download"
PROJECT_PATH = os.curdir
IMAGE_TYPE = (".jpg", ".png", ".bmp")
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

COS_REGION = "ap-guangzhou"
COS_SECRET_ID = "AKIDCCxgFYeuzo20jGXjiSxGSZtWt10lFRM1"
COS_SECRET_KEY = "RedNr67ud9TZZLr7AzVnvnTv75wazA6r"
COS_TOKEN = None
COS_SCHEMA = "https"
COS_OSU_BUCKET = "r0picgo-1308801249"
COS_OSU_PATH = "/osu"
