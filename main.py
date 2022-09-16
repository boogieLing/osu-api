import os
import random
from typing import Dict

import uvicorn
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from const import DOWNLOAD_RES_PATH
from utils import show_folder_files, show_beatmap

app = FastAPI()


@app.get("/random_beatmap")
async def random_beatmap():
    total_folder = show_folder_files(DOWNLOAD_RES_PATH)
    random_index = random.randint(0, len(total_folder) - 1)

    random_result = show_beatmap(total_folder[random_index])
    return {
        "name": total_folder[random_index],
        "data": random_result
    }


@app.get("/beatmap_list")
async def beatmap_list():
    return show_folder_files(DOWNLOAD_RES_PATH)


@app.get("/beatmap/{name}")
async def beatmap(name: str):
    return show_beatmap(name)


@app.get("/image/{folder}/{image_name}")
async def image(folder: str, image_name: str):
    file_stream = open(os.path.join(DOWNLOAD_RES_PATH, folder, image_name), mode="rb")
    return StreamingResponse(file_stream, media_type="image")


@app.get("/music/{folder}/{music_name}")
async def music(folder: str, music_name: str):
    file_stream = open(os.path.join(DOWNLOAD_RES_PATH, folder, music_name), mode="rb")
    return StreamingResponse(file_stream, media_type="music")


if __name__ == '__main__':
    uvicorn.run(app, port=11312, debug=True)
