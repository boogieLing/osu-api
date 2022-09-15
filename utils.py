# -*- coding: utf-8 -*-
# Author： BoogieLing
# Datetime： 2022/9/15 22:20 
# IDE： PyCharm
# from bit to bilibili
import os
from fastapi.responses import StreamingResponse

from const import PROJECT_PATH, DOWNLOAD_RES_PATH, IMAGE_TYPE, MUSIC_TYPE


def show_folder_files(base_path, all_files=None, recursion=False):
    """
    遍历当前目录所有文件夹
    :param base_path:
    :param all_files:
    :param recursion:是否递归
    :return:
    """
    if all_files is None:
        all_files = []
    file_list = os.listdir(base_path)
    # 准备循环判断每个元素是否是文件夹还是文件，是文件的话，把名称传入list，是文件夹的话，递归
    for file in file_list:
        # 利用os.path.join()方法取得路径全名，并存入cur_path变量，否则每次只能遍历一层目录
        # cur_path = os.path.join(base_path, file)
        cur_path = os.path.join(base_path, file)
        # 判断是否是文件夹
        if os.path.isdir(cur_path):
            if recursion:
                show_folder_files(cur_path, all_files)
            else:
                all_files.append(file)
    return all_files


def show_beatmap(name):
    """
    遍历当前目录所有文件夹
    :param name:
    :return:
    """
    res = {
        "images": [],
        "songs": []
    }
    target_folder = os.path.join(DOWNLOAD_RES_PATH, name) + ""
    if os.path.isdir(target_folder):
        file_list = os.listdir(target_folder)
        for file in file_list:
            if file.title().lower().endswith(IMAGE_TYPE):
                res["images"].append(file)
            if file.title().lower().endswith(MUSIC_TYPE):
                res["songs"].append(file)
    return res


