import argparse
import base64
import json
import os
import re
import sys
import time
import zipfile
from typing import Dict

import requests
from InquirerPy import prompt
from loguru import logger

from const import IMAGE_TYPE, MUSIC_TYPE

DOWNLOAD_PATH = os.curdir
# Windows
if sys.platform.startswith("win32"):
    USERPROFILE = os.getenv("USERPROFILE")
# Linux or MacOS
else:
    USERPROFILE = os.getenv("HOME")
HOME_DIR = os.path.join(USERPROFILE, ".osu-beatmap-downloader")
CREDS_FILEPATH = os.path.join(HOME_DIR, "credentials.json")
LOGS_FILEPATH = os.path.join(HOME_DIR, "downloader.log")
ILLEGAL_CHARS = re.compile(r"[\<\>:\"\/\\\|\?*]")

FORMAT_TIME = "<cyan>{time:YYYY-MM-DD HH:mm:ss}</cyan>"
FORMAT_LEVEL = "<level>{level: <8}</level>"
FORMAT_MESSAGE = "<level>{message}</level>"
LOGGER_CONFIG = {
    "handlers": [
        {
            "sink": sys.stdout,
            "format": " | ".join((FORMAT_TIME, FORMAT_LEVEL, FORMAT_MESSAGE)),
        },
        {
            "sink": LOGS_FILEPATH,
            "format": " | ".join((FORMAT_TIME, FORMAT_LEVEL, FORMAT_MESSAGE)),
        },
    ]
}
logger.configure(**LOGGER_CONFIG)

OSU_URL = "https://osu.ppy.sh/home"
OSU_SESSION_URL = "https://osu.ppy.sh/session"
OSU_SEARCH_URL = "https://osu.ppy.sh/beatmapsets/search"


class CredentialHelper:
    def __init__(self):
        self.credentials = {}

    def ask_credentials(self):
        questions = [
            {
                "type": "input",
                "message": "Enter your osu! username:",
                "name": "username",
            },
            {
                "type": "password",
                "message": "Enter your osu! password:",
                "name": "password",
            },
            {
                "type": "confirm",
                "message": "Remember credentials?",
                "name": "save_creds",
            },
        ]
        answers = prompt(questions)
        self.credentials["username"] = answers["username"]
        self.credentials["password"] = answers["password"]
        if answers["save_creds"]:
            # 本地缓存
            self.save_credentials()

    def ask_credentials_no_cmd(self, username, password):
        self.credentials["username"] = username
        self.credentials["password"] = password
        self.save_credentials()

    def load_credentials(self):
        # 获取验证凭证
        try:
            with open(CREDS_FILEPATH, "r") as cred_file:
                self.credentials = json.load(cred_file)
        except FileNotFoundError:
            logger.info(f"File {CREDS_FILEPATH} not found")
            # 本地不存在
            self.ask_credentials()

    def save_credentials(self):
        try:
            with open(CREDS_FILEPATH, "w") as cred_file:
                json.dump(self.credentials, cred_file, indent=2)
        except IOError:
            logger.error(f"Error writing {CREDS_FILEPATH}")


class BeatMapSet:
    def __init__(self, data):
        self.set_id = data["id"]
        self.title = data["title"]
        self.artist = data["artist"]
        self.url = f"https://osu.ppy.sh/beatmapsets/{self.set_id}"

    def __str__(self):
        string = f"{self.set_id}-{self.artist}-{self.title}"
        return ILLEGAL_CHARS.sub("_", string)


def write_beatmapset_file(filename, data):
    target_path = DOWNLOAD_PATH + "/download"
    folder = os.path.exists(target_path)
    if not folder:  # 判断是否存在文件夹如果不存在则创建为文件夹
        os.makedirs(target_path)
    filename = filename.replace(" ", "_")
    file_path = os.path.join(target_path, f"{filename}.zip")
    logger.info(f"Writing file: {file_path}")
    with open(file_path, "wb") as outfile:
        outfile.write(data)
    logger.success("File write successful")
    unzip_beatmapset_file(file_path, os.path.join(target_path, filename))


def unzip_beatmapset_file(origin_file, target_dir):
    zip_file = zipfile.ZipFile(origin_file)
    zip_list = zip_file.namelist()  # 压缩文件清单，可以直接看到压缩包内的各个文件的明细
    for f in zip_list:
        title = f.replace(" ", "_")
        if title.lower().endswith(IMAGE_TYPE):
            zip_file.extract(f, target_dir)
            origin_pic_file = target_dir + "/" + f
            pic_file = target_dir + "/" + title
            os.rename(origin_pic_file, pic_file)
            kbSize = os.path.getsize(pic_file) / 1024
            if kbSize < 300.0:
                # 小于300kb的图片无用
                os.remove(pic_file)
        if title.lower().endswith(MUSIC_TYPE):
            zip_file.extract(f, target_dir)
            origin_music_file = target_dir + "/" + f
            music_file = target_dir + "/" + title
            os.rename(origin_music_file, music_file)
            mbSize = os.path.getsize(music_file) / 1024 / 1024
            if mbSize < 1.0:
                # 小于1MB的音频无用
                os.remove(music_file)

    zip_file.close()
    logger.success(f"Unzip {origin_file} successful")
    os.remove(origin_file)
    logger.success(f"Delete {origin_file} successful")


def get_file_duration(path):
    """
    获取单个wav文件时长
    :param path: 文件路径
    :return:
    """
    popen = os.popen('sox {file_path} -n stat 2>&1'.format(file_path=path))
    content = popen.read()
    li = re.findall('Length \(seconds\):(.*?)Scaled by:', content, re.DOTALL)
    try:
        wav_len_str = li[0].strip()
    except Exception:
        wav_len_str = popen.readlines()[1].split()[-1]
    wav_len = float(wav_len_str)
    popen.close()
    return wav_len


class Downloader:
    def __init__(self, limit, no_video, params, no_cmd=False):
        self.beatmapsets = set()
        self.limit = limit
        self.no_video = no_video
        self.cred_helper = CredentialHelper()  # 需要一个合法用户
        if no_cmd:
            if params["username"] and  params["password"]:
                self.cred_helper.ask_credentials_no_cmd(params["username"], params["password"])
            else:
                logger.error("When do not use cmd to download, you need to provide a username and password")
                return
        else:
            self.cred_helper.load_credentials()
        self.session = requests.Session()

        self.login()  # 登录，获取登录态
        self.scrape_beatmapsets(params)  # 获取top谱图
        self.remove_existing_beatmapsets()  # 已下载过的不再下载

    def get_token(self):
        # access the osu! homepage
        homepage = self.session.get(OSU_URL)
        # 从meta段提取 CSRF token
        # extract the CSRF token sitting in one of the <meta> tags
        regex = re.compile(r".*?csrf-token.*?content=\"(.*?)\">", re.DOTALL)
        match = regex.match(homepage.text)
        csrf_token = match.group(1)
        return csrf_token

    def login(self):
        # 登录信息，获取一个有效Token
        logger.info(" DOWNLOADER STARTED ".center(50, "#"))
        data = self.cred_helper.credentials
        data["_token"] = self.get_token()
        headers = {"referer": OSU_URL}  # referer从home页来的访客
        res = self.session.post(OSU_SESSION_URL, data=data, headers=headers)  # 需要一个session，模拟正常登录流程
        if res.status_code != requests.codes.ok:
            logger.error("Login failed")
            sys.exit(1)
        logger.success("Login successfully")

    def scrape_beatmapsets(self, params=None):
        if params is None:
            params = {"sort": "favourites_desc"}
        fav_count = sys.maxsize
        cursor_string = ""
        num_beatmapsets = 0
        logger.info("Scraping beatmapsets")
        while num_beatmapsets < self.limit:
            # TODO 不知道选项参数从何而来....
            if cursor_string and cursor_string != "":
                params["cursor_string"] = cursor_string
            response = self.session.get(OSU_SEARCH_URL, params=params)
            data = response.json()

            if self.limit < len(data["beatmapsets"]):
                data["beatmapsets"] = data["beatmapsets"][0:self.limit]
            # 构造 beatmap, 关键是id
            self.beatmapsets.update(
                (BeatMapSet(bmset) for bmset in data["beatmapsets"])
            )
            fav_count = data["beatmapsets"][-1]["favourite_count"]
            cur_id = data["beatmapsets"][-1]["id"]
            cursor_string_json = json.dumps({"favourite_count": fav_count, "id": cur_id})
            cursor_string = base64.b64encode(cursor_string_json.encode())
            num_beatmapsets = len(self.beatmapsets)
        logger.success(f"Scraped {num_beatmapsets} beatmapsets")

    def remove_existing_beatmapsets(self):
        filtered_set = set()
        for beatmapset in self.beatmapsets:
            name = str(beatmapset).replace(" ", "_")
            dir_path = os.path.join(DOWNLOAD_PATH + "/download", name)
            file_path = dir_path + ".zip"
            if os.path.isdir(dir_path) or os.path.isfile(file_path):
                logger.error(f"BeatMapSet already downloaded: {beatmapset}")
                continue
            filtered_set.add(beatmapset)
        self.beatmapsets = filtered_set

    def download_beatmapset_file(self, beatmapset):
        logger.info(f"Downloading beatmapset: {beatmapset}")
        headers = {"referer": beatmapset.url}  # 从谱图页进入下载页
        download_url = beatmapset.url + "/download"
        if self.no_video:
            download_url += "?noVideo=1"  # 不下载视频
        response = self.session.get(download_url, headers=headers)
        if response.status_code == requests.codes.ok:
            logger.success(f"{str(beatmapset)} - {response.status_code} - Download successful")
            write_beatmapset_file(str(beatmapset), response.content)
            return True
        else:
            logger.warning(f"{response.status_code} - Download failed")
            return False

    def run(self):
        tries = 0
        while self.beatmapsets:
            next_set = self.beatmapsets.pop()
            # 开始下载
            download_success = self.download_beatmapset_file(next_set)
            if download_success:
                tries = 0
                time.sleep(2)
            else:
                self.beatmapsets.add(next_set)
                tries += 1
                if tries > 4:
                    logger.error("Failed 5 times in a row")
                    logger.info("Website download limit reached")
                    logger.info("Try again later")
                    logger.info(" DOWNLOADER TERMINATED ".center(50, "#") + "\n")
                    sys.exit()
        logger.info(" DOWNLOADER FINISHED ".center(50, "#") + "\n")


def main():
    parser = argparse.ArgumentParser("osu-beatmap-downloader")
    subparsers = parser.add_subparsers(dest="command", help="Choose a subcommand")

    parser_downloader = subparsers.add_parser(
        "download", help="Start the beatmap downloader in the current directory",
    )
    parser_downloader.add_argument(
        "-l",
        "--limit",
        type=int,
        help="Maximum number of beatmapsets to download",
        default=200,
    )
    parser_downloader.add_argument(
        "-nv",
        "--no-video",
        help="Downloads beatmaps without video files",
        action="store_true",
    )

    parser_credentials = subparsers.add_parser(
        "credentials", help="Manage your login credentials"
    )
    mutex_group = parser_credentials.add_mutually_exclusive_group(required=True)
    mutex_group.add_argument(
        "--check", help="Check if the credential file exists", action="store_true"
    )
    mutex_group.add_argument(
        "--delete", help="Delete the credential file if it exists", action="store_true"
    )

    args = parser.parse_args()
    if args.command == "download":
        loader = Downloader(args.limit, args.no_video)
        loader.run()
    elif args.command == "credentials":
        if args.check:
            if os.path.exists(CREDS_FILEPATH):
                print("Credential file exists: ", CREDS_FILEPATH)
            else:
                print("There is no credential file")
        if args.delete:
            try:
                os.remove(CREDS_FILEPATH)
                print("Credential file successfully deleted")
            except FileNotFoundError:
                print("There is no credential file to delete")


def no_cmd_download(limit: int, params: Dict[str, str]):
    loader = Downloader(limit, "store_true", params, True)
    loader.run()


if __name__ == "__main__":
    no_cmd_download(
        2,
        {
            "q": "Miku",
            "sort": "favourites_desc",
            "username": "z_fish",
            "password": "cherilee233osu"
        },
    )
