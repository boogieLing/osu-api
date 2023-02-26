import datetime
import random

from tencent_cloud import tencent_cos_imag_list
from loguru import logger


class OsuPic:
    def __init__(self):
        self.img_table = dict()
        self.img_list = list()
        self.last_update = datetime.datetime.now()

    def random_pic(self):
        now_time = datetime.datetime.now()
        if now_time > self.last_update + datetime.timedelta(hours=1) or len(self.img_list) < 1:
            logger.info("update OsuPic")
            self.img_table, self.img_list = tencent_cos_imag_list()
            self.last_update = now_time
        return random.choice(self.img_list)


osu_pic = OsuPic()
