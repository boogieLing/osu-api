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
            # ????????????
            self.save_credentials()

    def ask_credentials_no_cmd(self, username, password):
        self.credentials["username"] = username
        self.credentials["password"] = password
        self.save_credentials()

    def load_credentials(self):
        # ??????????????????
        try:
            with open(CREDS_FILEPATH, "r") as cred_file:
                self.credentials = json.load(cred_file)
        except FileNotFoundError:
            logger.info(f"File {CREDS_FILEPATH} not found")
            # ???????????????
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
    if not folder:  # ???????????????????????????????????????????????????????????????
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
    zip_list = zip_file.namelist()  # ???????????????????????????????????????????????????????????????????????????
    for f in zip_list:
        title = f.replace(" ", "_")
        if title.lower().endswith(IMAGE_TYPE + MUSIC_TYPE):
            zip_file.extract(f, target_dir)
            origin_item = target_dir + "/" + f
            rename_item = target_dir + "/" + title
            try:
                os.rename(origin_item, rename_item)
            except Exception:
                logger.error("--remove--")
                os.remove(origin_item)
                shutil.rmtree(target_dir)
                logger.error(f"{origin_item}\n{rename_item}\n{target_dir}")
                logger.error("==remove==")
                break
            if title.lower().endswith(IMAGE_TYPE):
                kbSize = os.path.getsize(rename_item) / 1024
                if kbSize < 300.0:
                    # ??????300kb???????????????
                    os.remove(rename_item)
            if title.lower().endswith(MUSIC_TYPE):
                mbSize = os.path.getsize(rename_item) / 1024 / 1024
                if mbSize < 1.0:
                    # ??????1MB???????????????
                    os.remove(rename_item)

    zip_file.close()
    logger.success(f"Unzip {origin_file} successful")
    os.remove(origin_file)
    logger.success(f"Delete {origin_file} successful")


def get_file_duration(path):
    """
    ????????????wav????????????
    :param path: ????????????
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
    def __init__(self, limit, no_video, params, certification, no_cmd=False):
        self.beatmapsets = set()
        self.limit = limit
        self.no_video = no_video
        self.cred_helper = CredentialHelper()  # ????????????????????????
        if no_cmd:
            if certification["username"] and certification["password"]:
                self.cred_helper.ask_credentials_no_cmd(certification["username"], certification["password"])
            else:
                logger.error("When do not use cmd to download, you need to provide a username and password")
                return
        else:
            self.cred_helper.load_credentials()
        self.session = requests.Session()

        self.login()  # ????????????????????????
        self.scrape_beatmapsets(params)  # ??????top??????
        self.remove_existing_beatmapsets()  # ???????????????????????????

    def get_token(self):
        # access the osu! homepage
        homepage = self.session.get(OSU_URL)
        # ???meta????????? CSRF token
        # extract the CSRF token sitting in one of the <meta> tags
        regex = re.compile(r".*?csrf-token.*?content=\"(.*?)\">", re.DOTALL)
        match = regex.match(homepage.text)
        csrf_token = match.group(1)
        return csrf_token

    def login(self):
        # ?????????????????????????????????Token
        logger.info(" DOWNLOADER STARTED ".center(50, "#"))
        data = self.cred_helper.credentials
        data["_token"] = self.get_token()
        headers = {"referer": OSU_URL}  # referer???home???????????????
        res = self.session.post(OSU_SESSION_URL, data=data, headers=headers)  # ????????????session???????????????????????????
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
            # TODO ?????????????????????????????????....
            if cursor_string and cursor_string != "":
                params["cursor_string"] = cursor_string
            response = self.session.get(OSU_SEARCH_URL, params=params)
            data = response.json()

            if self.limit < len(data["beatmapsets"]):
                data["beatmapsets"] = data["beatmapsets"][0:self.limit]
            # ?????? beatmap, ?????????id
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
        headers = {"referer": beatmapset.url}  # ???????????????????????????
        download_url = beatmapset.url + "/download"
        if self.no_video:
            download_url += "?noVideo=1"  # ???????????????
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
            # ????????????
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


def no_cmd_download(limit: int, params: Dict[str, str], certification: Dict[str, str]):
    loader = Downloader(limit, "store_true", params, certification, True)
    loader.run()


def update_daywise():
    no_cmd_download(
        15,
        {
            "q": "Miku",
            "sort": "favourites_desc",

        },
        {
            "username": "z_fish",
            "password": "cherilee233osu"
        },
    )
    no_cmd_download(
        50,
        {
            "g": 3,  # ????????????
            "s": "any",
            "sort": "rating_desc",
        },
        {
            "username": "z_fish",
            "password": "cherilee233osu"
        },
    )
    no_cmd_download(
        10,
        {
            "g": 3,  # ????????????
            "s": "any",
            "sort": "plays_desc",
        },
        {
            "username": "z_fish",
            "password": "cherilee233osu"
        },
    )
    no_cmd_download(
        15,
        {
            "q": "??????",  # ????????????
            "s": "any",
            "sort": "rating_desc",
        },
        {
            "username": "z_fish",
            "password": "cherilee233osu"
        },
    )


if __name__ == "__main__":
    update_daywise()
