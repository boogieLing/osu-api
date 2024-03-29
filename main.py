import os
import random
import sys
from typing import Dict, Tuple

import uvicorn
from fastapi import FastAPI, Body
from fastapi.responses import StreamingResponse
from const import DOWNLOAD_RES_PATH, PROJECT_NAME, DESCRIPTION, VERSION, DEBUG, LOG_DIR
from constom_log import InterceptHandler, format_record
from get import osu_pic
from main_website_pic_bed import get_main_website_pic_bed_categories, get_pic_bed_by_category
from utils import show_folder_files, show_beatmap
import logging
from loguru import logger
from fastapi.middleware.cors import CORSMiddleware


def init_app():
    _app = FastAPI(title=PROJECT_NAME, version=VERSION,
                   description=DESCRIPTION, debug=DEBUG)
    return _app


app = init_app()
origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    logging.getLogger("uvicorn").handlers.clear()
    # logging.getLogger().handlers = [InterceptHandler()]
    logger.configure(
        handlers=[{
            "sink": sys.stdout,
            "level": logging.DEBUG,
            "format": format_record
        }]
    )
    logger.add(LOG_DIR, encoding="utf-8", rotation="9:46")
    logger.debug("日志系统已加载")
    logging.getLogger("uvicorn.access").handlers = [InterceptHandler()]
    logging.getLogger("uvicorn").handlers = [InterceptHandler()]
    app.logger = logger


@app.get("/random_beatmap")
async def random_beatmap():
    total_folder = show_folder_files(DOWNLOAD_RES_PATH)
    random_index = random.randint(0, len(total_folder) - 1)

    random_result = show_beatmap(total_folder[random_index])
    return {
        "name": total_folder[random_index],
        "data": random_result
    }


@app.get("/random_pic")
async def random_pic():
    return {
        "data": osu_pic.random_pic()
    }


@app.get("/beatmap_list")
async def beatmap_list():
    return show_folder_files(DOWNLOAD_RES_PATH)


@app.get("/beatmap/{name}")
async def beatmap(name: str):
    return show_beatmap(name)


@app.get("/main_website_pic/category/total")
async def main_website_pic_bed_categories():
    categories = get_main_website_pic_bed_categories()
    return {
        "data": categories
    }


@app.post("/main_website_pic/category/list")
async def get_main_website_pic_bed_by_category(
        category: str = Body(..., title='分类名', embed=True),
        marker: str = Body(None, title='marker'),
        size: int = Body(30, title='数量')
):
    print(marker, size)
    res = get_pic_bed_by_category(category, marker, size)
    return {
        "data": res
    }


@app.get("/image/{folder}/{image_name}", deprecated=True)
async def image(folder: str, image_name: str):
    file_stream = open(os.path.join(DOWNLOAD_RES_PATH, folder, image_name), mode="rb")
    return StreamingResponse(file_stream, media_type="image")


@app.get("/music/{folder}/{music_name}", deprecated=True)
async def music(folder: str, music_name: str):
    file_stream = open(os.path.join(DOWNLOAD_RES_PATH, folder, music_name), mode="rb")
    return StreamingResponse(file_stream, media_type="music")


if __name__ == '__main__':
    uvicorn.run(app, port=11312, debug=True, access_log=True, )
