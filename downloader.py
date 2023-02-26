import argparse
import base64
import json
import os
import re
import shutil
import sys
import time
import zipfile
from typing import Dict

import requests
from InquirerPy import prompt
from loguru import logger

from const import IMAGE_TYPE, MUSIC_TYPE, PROJECT_PATH
from tencent_cloud import tencent_cos_upload

DOWNLOAD_PATH = os.curdir
# Windows
if sys.platform.startswith("win32"):
    USERPROFILE = os.getenv("USERPROFILE")
# Linux or MacOS
else:
    USERPROFILE = os.getenv("HOME")
HOME_DIR = os.path.join(USERPROFILE, ".osu-beatmap-downloader")
CREDS_FILEPATH = os.path.join(HOME_DIR, "credentials.json")
LOGS_FILEPATH = os.path.join(PROJECT_PATH, "logs", f'downloader/{time.strftime("%Y-%m-%d")}.log')
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


def write_beatmapset_file(category, filename, data):
    target_path = DOWNLOAD_PATH + "/download" + "/" + category
    folder = os.path.exists(target_path)
    if not folder:  # 判断是否存在文件夹如果不存在则创建为文件夹
        os.makedirs(target_path)
    filename = filename.replace(" ", "_")
    file_path = os.path.join(target_path, f"{filename}.zip")
    logger.info(f"Writing file: {file_path}")
    with open(file_path, "wb") as outfile:
        outfile.write(data)
    logger.success("File write successful")
    target_dir = os.path.join(target_path, filename)
    total_imags_dir = os.path.join(target_path, "imgs")
    total_imags_dir_exists = os.path.exists(total_imags_dir)
    if not total_imags_dir_exists:  # 判断是否存在文件夹如果不存在则创建为文件夹
        os.makedirs(total_imags_dir)
    unzip_beatmapset_file(total_imags_dir, file_path, target_dir, filename)
    tencent_cos_upload(category, target_dir, filename)


def unzip_beatmapset_file(total_imags_dir, origin_file, target_dir, map_name):
    zip_file = zipfile.ZipFile(origin_file)
    zip_list = zip_file.namelist()  # 压缩文件清单，可以直接看到压缩包内的各个文件的明细
    for f in zip_list:
        title = f.replace(" ", "_")
        if title.lower().endswith(IMAGE_TYPE + MUSIC_TYPE):
            try:
                zip_file.extract(f, target_dir)
            except Exception as e:
                logger.error(f"[zip_file.extract] error: {target_dir}, {e}")
                continue
            origin_item = target_dir + "/" + f
            rename_item = target_dir + "/" + title
            try:
                os.rename(origin_item, rename_item)
            except Exception:
                logger.error("--remove--")
                os.remove(origin_item)
                # shutil.rmtree(target_dir)
                # 本地保存
                logger.error(f"{origin_item}\n{rename_item}\n{target_dir}")
                logger.error("==remove==")
                break
            if title.lower().endswith(IMAGE_TYPE):
                kbSize = os.path.getsize(rename_item) / 1024
                if kbSize < 400.0:
                    # 小于400kb的图片无用
                    os.remove(rename_item)
                else:
                    try:
                        shutil.copy(rename_item, total_imags_dir + "/" + map_name + "-" + title)
                    except IOError as e:
                        logger.error("Unable to copy file. %s" % e)
                    except Exception:
                        logger.error("Unexpected error:", sys.exc_info())
            if title.lower().endswith(MUSIC_TYPE):
                mbSize = os.path.getsize(rename_item) / 1024 / 1024
                if mbSize < 1.0:
                    # 小于1MB的音频无用
                    os.remove(rename_item)

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
    def __init__(self, limit, no_video, params, certification, category, no_cmd=False):
        self.beatmapsets = set()
        self.limit = limit
        self.no_video = no_video
        self.category = category
        self.cred_helper = CredentialHelper()  # 需要一个合法用户
        if no_cmd:
            if certification["username"] and certification["password"]:
                self.cred_helper.ask_credentials_no_cmd(certification["username"], certification["password"])
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
            print(params)
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
            # cursor_string = base64.b64encode(cursor_string_json.encode())
            cursor_string =  data["cursor_string"]
            num_beatmapsets = len(self.beatmapsets)
        logger.success(f"Scraped {num_beatmapsets} beatmapsets")

    def remove_existing_beatmapsets(self):
        filtered_set = set()
        for beatmapset in self.beatmapsets:
            name = str(beatmapset).replace(" ", "_")
            dir_path = os.path.join(DOWNLOAD_PATH + "/download/" + self.category, name)
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
        resp = self.session.get(download_url, headers=headers)
        if resp.status_code == requests.codes.ok:
            logger.success(f"{str(beatmapset)} - {resp.status_code} - Download successful")
            write_beatmapset_file(self.category, str(beatmapset), resp.content)
            return True
        else:
            logger.warning(f"{resp.status_code} - Download failed")
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
                    # sys.exit()
                    raise ValueError("DOWNLOADER TERMINATED")

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
        loader = Downloader(args.limit, args.no_video, None, None, "none")
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


def no_cmd_download(limit: int, category: str, params: Dict[str, str], certification: Dict[str, str]):
    loader = Downloader(limit, "store_true", params, certification, category, True)
    loader.run()


def update_daywise():
    # no_cmd_download(
    #     50,
    #     "Hatsune Miku",
    #     {
    #         "q": "Hatsune Miku",
    #     },
    #     {
    #         "username": "z_fish",
    #         "password": "cherilee233osu"
    #     },
    # )
    # time.sleep(5)
    # no_cmd_download(
    #     10,
    #     "one piece",
    #     {
    #         "q": "one piece",
    #     },
    #     {
    #         "username": "z_fish",
    #         "password": "cherilee233osu"
    #     },
    # )
    # time.sleep(5)
    # no_cmd_download(
    #     30,
    #     "Aisaka Taiga",
    #     {
    #         "q": "Aisaka Taiga",
    #     },
    #     {
    #         "username": "z_fish",
    #         "password": "cherilee233osu"
    #     },
    # )
    # no_cmd_download(
    #     50,
    #     "k-on",
    #     {
    #         "q": "k-on",
    #     },
    #     {
    #         "username": "z_fish",
    #         "password": "cherilee233osu"
    #     },
    # )
    # time.sleep(5)
    # no_cmd_download(
    #     30,
    #     "Touhou Project",
    #     {
    #         "q": "Touhou Project",
    #     },
    #     {
    #         "username": "z_fish",
    #         "password": "cherilee233osu"
    #     },
    # )
    # time.sleep(5)
    while 1:
        try:
            no_cmd_download(
                50,
                "社区喜爱-上架时间",
                {
                    "s": "loved",
                },
                {
                    "username": "z_fish",
                    "password": "cherilee233osu"
                },
            )
            break
        except ValueError as e:
            logger.error(e)
            time.sleep(60)
    while 1:
        try:
            logger.info("日语-上架时间")
            no_cmd_download(
                110,
                "日语-上架时间",
                {
                    "l": 3,
                    "s": "any",
                },
                {
                    "username": "z_fish",
                    "password": "cherilee233osu"
                },
            )

            time.sleep(5)
            break
        except ValueError as e:
            logger.error(e)
            time.sleep(60)


if __name__ == "__main__":
    update_daywise()
    # test_single()
