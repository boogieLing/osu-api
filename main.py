import os
from typing import Dict

import uvicorn
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from const import DOWNLOAD_RES_PATH
from utils import show_folder_files, show_beatmap

app = FastAPI()


@app.get("/random_beatMap")
async def random_beatMap():
    pass


@app.get("/beatMap_list")
async def beatMap_list():
    return show_folder_files(DOWNLOAD_RES_PATH)


@app.get("/beatMap/{name}")
async def beatMap(name: str):
    return show_beatmap(name)


@app.get("/img/{name}")
async def img(name: str):
    file_like = open(os.path.join(DOWNLOAD_RES_PATH, name), mode="rb")
    return StreamingResponse(file_like, media_type="image/jpg")


if __name__ == '__main__':
    uvicorn.run(app, port=11312, debug=True)
